"""Engine core: causal enqueue and the concurrency/loop/budget/kill guards
(§5.2).

Guard functions are pure (state docs / config in, verdict out) so dispatch
logic (Task 13) can compose them without re-reading the state store.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from engine.commands import parse_decision, parse_queue_command
from engine.config import Config
from engine.models import (
    Event,
    GateDecision,
    GateStatus,
    Handoff,
    RunState,
    TaskRun,
    compute_handoff_run_id,
    compute_run_id,
)
from engine.registry import build_adapter
from engine.state import GitJsonStateStore, Txn, _add_minutes, _now_iso

# A RUNNING run whose named workflow has vanished is only treated as lost once
# this grace window past its attempt start has elapsed (D1: killed runs retry
# from scratch, but a workflow that has merely not registered yet must not be
# swept prematurely).
RUNNER_LOST_GRACE_MIN = 10
NON_TERMINAL = {"QUEUED", "RUNNING", "WAITING_GATE"}
# Ports whose concrete adapter a run records at prepare time.
BINDABLE_PORTS = ("tracker", "agent-session", "messaging")

# States that make a ticket exclusive for dispatch (and count towards the
# global in-flight cap): a QUEUED run merely waits its turn -- counting it
# would let a batch of already-queued tickets starve every future dispatch
# once the cap is reached (mirrors `state._EXCLUSIVE_STATES` in `claim_run`).
EXCLUSIVE_STATES = {"RUNNING", "WAITING_GATE"}
# The engine-owned lifecycle labels: exactly one is applied at a time, so the
# issue list answers "where is this ticket" without reading the state branch.
# WAITING_GATE is a *run* state rather than a ticket status, but it is the one
# a human needs to act on, so it surfaces here alongside the ticket statuses.
# This map is the ONLY set `set_status_label` may remove -- every other
# `hq:`-prefixed label (`hq:intake`, `hq:public-safe`, `hq:executor=...`) is
# owned by config or a human and must survive a transition.
STATUS_LABELS = {
    "ACTIVE": "hq:active",
    "WAITING_GATE": "hq:waiting-gate",
    "AWAITING_MERGE": "hq:awaiting-merge",
    "BLOCKED": "hq:blocked",
    "DONE": "hq:done",
}
_OWNED_LABELS = frozenset(STATUS_LABELS.values())


def queue_positions(runs: list[dict]) -> dict[str, int]:
    """Effective queue position per run_id.

    `queue_seq` where the run carries one, else the run's array index -- which
    is exactly the ordering dispatch used before `queue_seq` existed, so a
    ticket written by an older engine keeps its order with no state migration.
    """
    return {r["run_id"]: r.get("queue_seq", i) for i, r in enumerate(runs)}


def resolve_input_source(runs: list[dict], run: dict) -> str | None:
    """The run whose recorded artifacts `run` consumes.

    The nearest SUCCEEDED run ahead of it in the queue, else the run that
    enqueued it (`parent_run_id`). NOT `parent_run_id` on its own: one run may
    declare several queue entries at once, so whoever enqueued `review` (say
    `spec`) need not be who produced what `review` reads (`implement`).

    Resolved at dispatch/claim rather than stored when the queue is declared,
    because `attempt` is part of a run id -- any pointer baked at declaration
    time goes stale the moment a predecessor retries.
    """
    positions = queue_positions(runs)
    mine = positions.get(run["run_id"], 0)
    earlier = [
        r for r in runs if positions[r["run_id"]] < mine and r["state"] == RunState.SUCCEEDED.value
    ]
    if earlier:
        return max(earlier, key=lambda r: positions[r["run_id"]])["run_id"]
    if run.get("parent_run_id"):
        return run["parent_run_id"]
    # A ROOT run has no declared predecessor -- intake's first run, or a comment
    # inserted at the head of the queue. It is an interjection rather than a
    # step, so queue position tells us nothing: fall back to the ticket's most
    # recent SUCCEEDED run anywhere. Without this a comment-sourced run sees no
    # ledger artifacts at all, which is fatal for a task whose job is to read
    # what happened and re-plan.
    produced = [
        r for r in runs if r["state"] == RunState.SUCCEEDED.value and r["run_id"] != run["run_id"]
    ]
    if produced:
        return max(produced, key=lambda r: positions[r["run_id"]])["run_id"]
    return None


def _next_queue_seq(txn: Txn, ticket_id: str) -> int:
    """One past the ticket's highest occupied position. Read from the
    in-transaction doc, so a batch inserting several runs in one write sees
    each preceding insert and assigns increasing positions."""
    runs = txn.ticket_doc(ticket_id).get("runs", [])
    return max(queue_positions(runs).values(), default=-1) + 1


def _insert_at_queue_head(txn: Txn, ticket_id: str) -> int:
    """Free the front of the queue and return the position freed.

    Every QUEUED run at or after the current front is bumped by one, so an
    inserted entry runs BEFORE work already planned while that work keeps its
    relative order. Bumping rather than using `front - 1` keeps positions
    non-negative (the schema's minimum) and needs no renumbering scheme.

    Only QUEUED runs move: a terminal run's position is history, and a new entry
    sharing a position with one is harmless -- terminal runs are not dispatch
    candidates and the sort is stable.
    """
    runs = txn.ticket_doc(ticket_id).get("runs", [])
    positions = queue_positions(runs)
    pending = [r for r in runs if r["state"] == RunState.QUEUED.value]
    if not pending:
        return _next_queue_seq(txn, ticket_id)
    front = min(positions[r["run_id"]] for r in pending)
    for r in pending:
        txn.update_run(ticket_id, r["run_id"], queue_seq=positions[r["run_id"]] + 1)
    return front


def _put_queued_run(
    txn: Txn,
    run_id: str,
    *,
    ticket_id: str,
    task_id: str,
    task_version: int,
    bindings: dict[str, str],
    queue_seq: int | None = None,
    **fields,
) -> bool:
    """Insert a QUEUED run (idempotent by run_id) plus its run.queued event.
    Returns True if newly inserted, False if it already existed (no-op) --
    shared by every run-creation path (`enqueue`, `apply_queue`,
    `reenqueue_same`'s handoff branch) so identity/idempotency is enforced
    in exactly one place.

    `queue_seq` is appended to the end of the ticket's queue unless the caller
    passes one. A retry passes the position of the attempt it replaces: a
    failed run's retry has to resume that run's place in the queue, not move
    behind everything enqueued after it.
    """
    if txn.get_run(ticket_id, run_id) is not None:
        return False
    if queue_seq is None:
        queue_seq = _next_queue_seq(txn, ticket_id)
    fields["queue_seq"] = queue_seq
    run = TaskRun(
        run_id=run_id,
        task_id=task_id,
        task_version=task_version,
        ticket_id=ticket_id,
        state=RunState.QUEUED,
        bindings=bindings,
        cost_usd=None,
        tokens=None,
        usage_known=False,
        artifacts=[],
        **fields,
    )
    txn.put_run(ticket_id, run.to_dict())
    txn.append_event(
        ticket_id,
        Event(
            event_id=f"{run_id}:queued",
            kind="run.queued",
            ticket_id=ticket_id,
            run_id=run_id,
            task_id=task_id,
            task_version=task_version,
            state=RunState.QUEUED,
            bindings=bindings,
        ).to_dict(),
    )
    return True


def enqueue(
    store: GitJsonStateStore,
    *,
    ticket_id: str,
    parent_run: dict | None = None,
    source_event_id: str | None = None,
    enqueue_index: int = 0,
    task_id: str,
    task_version: int,
    attempt: int = 0,
    bindings: dict[str, str],
    chain_depth: int,
    queue_seq: int | None = None,
) -> str:
    """Enqueue a QUEUED run for `task_id`, idempotent by run_id.

    run_id is derived from the causal parent (a parent run's run_id, or a
    source event key for a root enqueue) plus enqueue_index/task_id/attempt,
    so a duplicate call with the same inputs is a no-op rather than a second
    run record. Used for the intake root run only -- a handoff-spawned run
    uses `compute_handoff_run_id` via `apply_queue`/`reenqueue_same`.
    """
    parent_or_source = parent_run["run_id"] if parent_run is not None else source_event_id
    if parent_or_source is None:
        raise ValueError("enqueue needs parent_run or source_event_id (causal identity)")
    run_id = compute_run_id(parent_or_source, enqueue_index, task_id, attempt)

    def fn(txn: Txn) -> None:
        _put_queued_run(
            txn,
            run_id,
            ticket_id=ticket_id,
            task_id=task_id,
            task_version=task_version,
            bindings=bindings,
            attempt=attempt,
            chain_depth=chain_depth,
            parent_run_id=parent_run["run_id"] if parent_run is not None else None,
            source_event_id=source_event_id,
            enqueue_index=enqueue_index,
            queue_seq=queue_seq,
        )

    store.write(fn)
    return run_id


def check_concurrency(
    state_docs: dict[str, dict],
    ticket_id: str,
    run_id: str | None = None,
    parallel_ok: bool = False,
    in_flight_cap: int = 3,
) -> bool:
    """ADVISORY pre-filter only -- cheap and tolerant of stale/scoped state,
    used by `dispatch` to skip an obviously-blocked run before even
    attempting a claim. The real enforcement (the compare-and-swap that
    can't be raced) is `GitJsonStateStore.claim_run`; do not rely on this
    function for correctness.

    True if the run `run_id` (or a hypothetical new run) may start on
    `ticket_id`.

    Refused when the ticket has another run in an EXCLUSIVE state
    (RUNNING/WAITING_GATE — a QUEUED sibling just waits, and the run under
    evaluation never blocks itself), unless parallel_ok; or when the number
    of OTHER tickets with a RUNNING/WAITING_GATE run has already reached the
    global cap (QUEUED-only tickets never count, matching `claim_run` -- else
    cap+1 queued tickets would starve every unscoped dispatch pass forever).
    """

    def has_exclusive(doc: dict) -> bool:
        return any(
            r["state"] in EXCLUSIVE_STATES and r["run_id"] != run_id for r in doc.get("runs", [])
        )

    if not parallel_ok and has_exclusive(state_docs.get(ticket_id, {})):
        return False

    other_active = sum(
        1
        for tid, doc in state_docs.items()
        if tid != ticket_id and any(r["state"] in EXCLUSIVE_STATES for r in doc.get("runs", []))
    )
    return other_active < in_flight_cap


def check_claim_active(ticket_doc: dict | None, run_id: str) -> bool:
    """True if `run_id` is still the ticket's live, currently-claimed run --
    the ticket is `ACTIVE` and this run is `RUNNING`.

    False means a stale/zombie claim: the ticket was blocked by a concurrent
    path since this run started, or the run itself was superseded (e.g. the
    dispatcher's lost-run sweep already retried it under a new run_id). This
    is the narrowed close-fencing predicate (Task 13) collect's `_collect_
    success` revalidates twice: read-only, immediately before any external
    side effect (branch push/PR-open/gate-request), and, authoritatively,
    re-read fresh inside the FINAL write transaction right before commit --
    so a zombie's late land never sets a ticket-wide `branch_conflict` and
    never records a result, even if a race let its push/PR slip through the
    early check. Pure (a state doc in, a verdict out) like the other guards
    above, so it needs no state-store read of its own.
    """
    if ticket_doc is None or ticket_doc.get("status") != "ACTIVE":
        return False
    run = next((r for r in ticket_doc.get("runs", []) if r["run_id"] == run_id), None)
    return run is not None and run["state"] == "RUNNING"


def check_loop_guard(state_doc: dict, max_runs: int = 25) -> tuple[bool, list[dict] | None]:
    """True (ok, None) unless the ticket has too many runs, in which case
    (False, trace) with trace being every run's run_id/task_id/parent_run_id
    for the BLOCKED reason.

    CANCELLED runs are excluded from the count: they never executed and spent
    nothing, so a route revised a few times must not exhaust the ticket's run
    ceiling with work that never happened. They stay in `runs` as audit.

    There is no depth ceiling. `chain_depth` is still recorded as provenance,
    but it stopped measuring anything a runaway could exhaust: a pre-declared
    queue puts every entry at the declaring run's depth + 1, so a ten-step
    route is depth 1. Even before that it was redundant -- measured on the
    pilot's own tickets, depth was `max_runs` minus retries (the same axis),
    and `budget.retries` already caps retries per task."""
    runs = [r for r in state_doc.get("runs", []) if r.get("state") != RunState.CANCELLED.value]
    # Guard runs BEFORE an enqueue, so `<` makes max_runs the true ceiling.
    if len(runs) < max_runs:
        return True, None
    trace = [
        {"run_id": r["run_id"], "task_id": r["task_id"], "parent_run_id": r.get("parent_run_id")}
        for r in runs
    ]
    return False, trace


def check_budget(state_doc: dict, budget: dict, ticket_cap_usd: float) -> dict:
    """Budget verdict for the ticket: spend so far, cap booleans, and the
    unknown-usage block flag.

    ticket_spend only sums runs with usage_known True -- a run whose actual
    cost is unknown must never silently count as $0, so it also never counts
    towards the cap; instead a FAILED run with usage_known False sets
    unknown_usage_block, which callers treat as BLOCK (never retry), since
    the real spend for that attempt is unknown and could already exceed cap.
    """
    runs = state_doc.get("runs", [])
    ticket_spend = sum(
        r["cost_usd"] for r in runs if r.get("usage_known") and r.get("cost_usd") is not None
    )
    remaining = ticket_cap_usd - ticket_spend
    unknown_usage_block = any(
        r["state"] == "FAILED" and not r.get("usage_known", False) for r in runs
    )
    return {
        "ticket_spend": ticket_spend,
        "over_ticket_cap": ticket_spend >= ticket_cap_usd,
        # Not "this run exceeded its cap": the ticket lacks headroom for one
        # more run at the task's max_cost_usd.
        "insufficient_headroom": remaining < budget["max_cost_usd"],
        "unknown_usage_block": unknown_usage_block,
    }


def kill_switch_active() -> bool:
    """True when the repo-variable-derived AGENT_HQ_KILL_SWITCH env is set."""
    return os.environ.get("AGENT_HQ_KILL_SWITCH") == "1"


# --------------------------------------------------------------------------
# Adapter construction and shared enqueue/failure/notify helpers used by both
# the dispatcher (sweep) and the three-phase runner (collect). One root-cause
# implementation of the retry policy lives in `_handle_failure`.
# --------------------------------------------------------------------------

# A build_adapter_fn(port, adapter_name, *, repo=None) -> adapter. Both dispatch
# and run_task accept one so tests inject fakes without monkeypatching importlib.
AdapterFn = Callable[..., object]


def build_port_adapter(config: Config, port: str, adapter_name: str, repo: str | None = None):
    """Assemble a port's settings from components.yml (+ approvers/issue_repo
    for gate, + the resolved repo) and construct the adapter via the
    registry. `issue_repo` is always the engine repo, for the issue-comment
    gate; `pr-review` simply ignores the extra key."""
    comp = config.components.get(port, {}) if isinstance(config.components, dict) else {}
    settings = dict(comp.get("settings", {}))
    if repo:
        settings["repo"] = repo
    if port == "gate":
        settings["approvers"] = config.approvers
        settings["issue_repo"] = intake_repo(config)
    return build_adapter(port, adapter_name, settings)


def _default_adapter_fn(config: Config) -> AdapterFn:
    def fn(port: str, adapter_name: str, repo: str | None = None):
        return build_port_adapter(config, port, adapter_name, repo)

    return fn


def intake_repo(config: Config) -> str | None:
    """The repo whose issue tracker intake, pinned comments, and escalations
    read/write -- the engine's own repo, distinct from the work repos a
    ticket's code lands in (see `resolve_target_repo`)."""
    return config.projects.get("engine_repo")


def resolve_setup(config: Config, repo: str | None, task_id: str) -> str | None:
    """The shell command that prepares `repo`'s worktree for `task_id`, from
    `repos.yml`'s `setup` map: the task's own entry, else `default`, else
    None. Config, so a different project configures a different command
    without touching engine code or a prompt -- and so setup that is the same
    every run costs no agent requests to perform."""
    meta = (config.repos or {}).get(repo or "", {})
    setup = meta.get("setup") or {}
    return setup.get(task_id) or setup.get("default")


def resolve_format(config: Config, repo: str | None, task_id: str) -> str | None:
    """The shell command that formats `repo`'s worktree for `task_id` after a
    successful agent run, from `repos.yml`'s `format` map: the task's own
    entry, else `default`, else None. Same shape and resolution as setup;
    execute runs it only when the task `writes_code`, before the work patch
    is materialized, so CI formatters do not reject the PR for style the
    agent left unformatted."""
    meta = (config.repos or {}).get(repo or "", {})
    fmt = meta.get("format") or {}
    return fmt.get(task_id) or fmt.get("default")


def resolve_target_repo(config: Config, details) -> str | None:
    """Match a repos.yml product_area against the ticket's labels/title/body.
    Returns None when nothing matches (intake treats that as ineligible;
    prepare/collect fall back to the first repo)."""
    haystack = " ".join([details.title, details.body, *details.labels]).lower()
    for repo, meta in config.repos.items():
        if meta["product_area"].lower() in haystack:
            return repo
    return None


_INJECTION_PATTERNS = ("ignore previous instructions", "disregard your")


def eligibility_reasons(config: Config, details) -> list[str]:
    """Why intake (or comment-driven re-admit) would refuse this ticket.

    Shared by `intake_ticket` and the intake-block recovery path in
    `poll_comments` so the two cannot drift.
    """
    intake_cfg = config.projects.get("intake", {})
    reasons: list[str] = []
    min_words = intake_cfg.get("min_body_words", 0)
    if len(details.body.split()) < min_words:
        reasons.append(f"description too short (needs >= {min_words} words)")
    for label in intake_cfg.get("excluded_labels", []):
        if label in details.labels:
            reasons.append(f"excluded label '{label}'")
    if resolve_target_repo(config, details) is None:
        reasons.append("no product area matches a configured repo")
    public_safe_label = config.projects.get("public_safe_label")
    if config.projects.get("public") and public_safe_label not in details.labels:
        reasons.append(f"missing required label '{public_safe_label}' (public deployment)")
    return reasons


def has_injection(details) -> bool:
    text = f"{details.title} {details.body}".lower()
    return any(pattern in text for pattern in _INJECTION_PATTERNS)


def subst(template: str, ticket_id: str) -> str:
    return template.replace("{ticket}", ticket_id)


def set_status_label(config, adapter_fn, ticket_id: str, status: str) -> None:
    """Put the ticket issue's lifecycle label in sync with `status`, so where a
    ticket stands is findable by label instead of by reading the state branch.
    Idempotent -- the tracker no-ops when the label set already matches.

    Always a POST-write side effect: the label is a *view* of state, never the
    source of it. A label that lags a crash is corrected by the next
    transition; a label trusted as state would be a second, forkable copy.

    Reads the issue's current labels and re-sends them: `set_status_labels`
    replaces the WHOLE `hq:`-prefixed set, so anything else the issue carries
    (`hq:intake`, `hq:public-safe`, `hq:executor=...`) has to be passed back
    through or it gets stripped. Only `STATUS_LABELS` values are dropped --
    filtering on the `hq:` prefix instead would strip config's own labels."""
    tracker = adapter_fn(
        "tracker", config.components["tracker"]["adapter"], repo=intake_repo(config)
    )
    keep = [name for name in tracker.fetch_ticket(ticket_id).labels if name not in _OWNED_LABELS]
    label = STATUS_LABELS.get(status)
    tracker.set_status_labels(ticket_id, status, keep + ([label] if label else []))


def notify_ticket(
    config, adapter_fn, ticket_id, message: str, event_id: str, mentions=None
) -> None:
    """Post one plain comment to the ticket thread, idempotent by `event_id`
    (the messaging adapter dedupes on its `<!--hq:evt:...-->` marker). The
    single primitive for engine-authored ticket-thread comments -- escalation
    and the review-park findings notice both go through here."""
    messaging = adapter_fn(
        "messaging", config.components["messaging"]["adapter"], repo=intake_repo(config)
    )
    messaging.notify({"ticket_id": ticket_id, "mentions": mentions or []}, message, [], event_id)


def post_pr_comment(config, adapter_fn, pr_ref: str, message: str, event_id: str) -> None:
    """Post one comment on a work-repo PR (`pr_ref` = 'org/repo#N'), idempotent
    by `event_id`. Reuses the `messaging` adapter bound to the work repo (a PR
    is an issue). Only the credentialed collect phase calls this -- the
    read-only review agent holds no push credential (PD-5), so review findings
    reach the PR from the engine, never from the agent child."""
    repo, number = pr_ref.split("#", 1)
    messaging = adapter_fn("messaging", config.components["messaging"]["adapter"], repo=repo)
    messaging.notify({"ticket_id": number}, message, [], event_id)


def _escalate(store, config, adapter_fn, ticket_id, run_id, message: str) -> None:
    members = config.approvers.get("groups", {}).get("escalation", {}).get("members", [])
    notify_ticket(config, adapter_fn, ticket_id, message, f"{run_id}:escalation", mentions=members)


def _block_ticket(
    store,
    config,
    adapter_fn,
    ticket_id,
    run_id,
    reason: str,
    *,
    actor: str | None = None,
    source: str | None = None,
    block_source: str = "engine",
) -> None:
    """Block the ticket, recording WHY in state -- not only in the event.

    `set_block` rather than a bare `set_ticket(status=...)`: this is the path
    every engine-side block takes (gate rejected/expired, retries exhausted,
    unknown spend, handoff-apply failure, PR feedback over budget), and it used
    to drop the `reason` it was handed on the floor, leaving `block_reason`
    null for all of them. The dashboard and `hq-ticket` then rendered "BLOCKED"
    with no reason, and the only copy of it was prose in an event `detail`.

    `block_source` defaults to `engine`. Callers that refuse while the ticket
    is still an intake block pass `block_source="intake"` so a later bare
    retry still hits intake recovery instead of burning triage.
    `source` is the event's provenance field (comment id, etc.), not the
    lifecycle sticker.
    """

    def fn(txn: Txn) -> None:
        txn.set_block(ticket_id, reason=reason, source=block_source, interrupted_run=run_id)
        txn.append_event(
            ticket_id,
            Event(
                event_id=f"{run_id}:blocked",
                kind="ticket.blocked",
                ticket_id=ticket_id,
                run_id=run_id,
                detail=reason,
                actor=actor,
                source=source,
            ).to_dict(),
        )

    store.write(fn)
    set_status_label(config, adapter_fn, ticket_id, "BLOCKED")


def reenqueue_same(store, run: dict, taskdef: dict, attempt: int) -> str:
    """Re-enqueue the same task at a new attempt.

    A handoff-spawned run (has `handoff_key`) retries via
    `compute_handoff_run_id`, preserving `handoff_key`/`repo`/
    `input_artifacts` -- a retry must run against the same repo with the
    same inputs. Anything else (the intake root run) retries via the
    original causal (`source_event_id`/`enqueue_index`) identity.

    Either way the retry inherits the replaced attempt's `queue_seq`, so it
    resumes that run's place in the queue instead of moving behind everything
    enqueued after it. A run written before `queue_seq` existed has none to
    inherit, so its retry appends -- exactly what happened before.
    """
    if run.get("handoff_key"):
        run_id = compute_handoff_run_id(run["parent_run_id"], run["handoff_key"], attempt)
        store.write(
            lambda txn: _put_queued_run(
                txn,
                run_id,
                ticket_id=run["ticket_id"],
                task_id=run["task_id"],
                task_version=taskdef["version"],
                bindings=run.get("bindings", {}),
                attempt=attempt,
                chain_depth=run["chain_depth"],
                parent_run_id=run.get("parent_run_id"),
                handoff_key=run["handoff_key"],
                repo=run.get("repo"),
                input_artifacts=list(run.get("input_artifacts") or []),
                queue_seq=run.get("queue_seq"),
            )
        )
        return run_id

    parent = {"run_id": run["parent_run_id"]} if run.get("parent_run_id") else None
    return enqueue(
        store,
        ticket_id=run["ticket_id"],
        parent_run=parent,
        source_event_id=run.get("source_event_id"),
        enqueue_index=run.get("enqueue_index") or 0,
        task_id=run["task_id"],
        task_version=taskdef["version"],
        attempt=attempt,
        bindings=run.get("bindings", {}),
        chain_depth=run["chain_depth"],
        queue_seq=run.get("queue_seq"),
    )


def _resolve_cancellations(
    ticket_doc: dict, cancel_keys: list[str], cancel_pending: bool
) -> tuple[list[dict], str | None]:
    """The QUEUED runs a declaration removes, or a rejection reason.

    `cancel_pending` takes every QUEUED run on the ticket. Named keys match on
    `handoff_key`; a key matching nothing is ignored (the entry already ran, or
    a re-delivery already cancelled it -- both are the intended end state), but
    a key matching MORE than one QUEUED run is an error, because keys are only
    unique per source run and which was meant is unknowable.

    Only QUEUED runs are cancellable. A run that reached RUNNING between this
    run's collect and this write landing survives -- `store.write` replays the
    transaction against fresh state on a push rejection, so the check
    re-evaluates rather than acting on a stale read.
    """
    queued = [r for r in ticket_doc.get("runs", []) if r["state"] == RunState.QUEUED.value]
    if cancel_pending:
        return queued, None
    doomed: list[dict] = []
    for key in cancel_keys:
        matches = [r for r in queued if r.get("handoff_key") == key]
        if len(matches) > 1:
            return [], (
                f"cancel key '{key}' matches {len(matches)} queued entries; "
                "keys are unique per source run, so this is ambiguous"
            )
        doomed.extend(matches)
    return doomed, None


def apply_queue(
    txn: Txn,
    config: Config,
    taskdefs: dict,
    ticket_id: str,
    source_run: dict,
    accepted: list[Handoff],
    attempt: int = 0,
    cancel_keys: list[str] | None = None,
    cancel_pending: bool = False,
) -> tuple[list[str], str | None]:
    """Apply a run's queue declaration: cancel what it names, then append
    `accepted` as QUEUED runs in declared order, idempotent by derived id
    (`compute_handoff_run_id`).

    Enforces the state-dependent guards the pure validator
    (`engine.handoff.validate_queue`) can't see -- each artifact's ledger entry
    actually exists, cancellations resolve unambiguously, and loop/budget still
    hold. Any guard failure rejects the WHOLE declaration (nothing cancelled and
    nothing appended), the same all-or-nothing contract as `validate_queue`.
    Must run inside the caller's own `store.write` transaction alongside the
    source run's own terminal-state update, so a crash between "succeeded" and
    "queue updated" cannot happen.

    Cancellation runs BEFORE insertion, and only over pre-existing QUEUED runs,
    so a declaration that both clears the plan and states a new one never
    cancels its own entries.
    """
    for h in accepted:
        for rel_path in h.artifacts or []:
            if not txn.has_artifact(ticket_id, source_run["run_id"], rel_path):
                return [], f"artifact '{rel_path}' missing from {source_run['run_id']}'s ledger"

    ticket_doc = txn.ticket_doc(ticket_id)
    doomed, cancel_reason = _resolve_cancellations(ticket_doc, cancel_keys or [], cancel_pending)
    if cancel_reason is not None:
        return [], cancel_reason

    loop_cfg = config.budgets["loop_guard"]
    # Prospective: account for the WHOLE batch about to be inserted (not just
    # the current, pre-insertion state) -- a two-handoff batch checked only
    # once against the current run count could otherwise land both runs even
    # though the second one pushes the ticket past max_runs. Same for depth:
    # every accepted handoff in this batch lands at the SAME child depth
    # (source_run's chain_depth + 1), which the current runs' own recorded
    # depths don't yet reflect.
    existing_runs = [
        r for r in ticket_doc.get("runs", []) if r.get("state") != RunState.CANCELLED.value
    ]
    projected_runs = len(existing_runs) + len(accepted)
    if projected_runs > loop_cfg["max_runs"]:
        return [], "loop guard would trip applying this queue declaration"
    for h in accepted:
        budget = taskdefs[h.target_task]["budget"]
        verdict = check_budget(ticket_doc, budget, config.budgets["ticket_cap_usd"])
        if verdict["over_ticket_cap"] or verdict["insufficient_headroom"]:
            return [], f"ticket budget exhausted for handoff target '{h.target_task}'"

    for victim in doomed:
        txn.update_run(ticket_id, victim["run_id"], state=RunState.CANCELLED.value)
        txn.append_event(
            ticket_id,
            Event(
                event_id=f"{victim['run_id']}:cancelled",
                kind="run.cancelled",
                ticket_id=ticket_id,
                run_id=victim["run_id"],
                task_id=victim.get("task_id"),
                state=RunState.CANCELLED,
                detail=(
                    f"cancelled by {source_run['run_id']}"
                    + (" (cancel_pending)" if cancel_pending else "")
                ),
                source=source_run["run_id"],
            ).to_dict(),
        )

    applied: list[str] = []
    for h in accepted:
        target = taskdefs[h.target_task]
        run_id = compute_handoff_run_id(source_run["run_id"], h.key, attempt)
        _put_queued_run(
            txn,
            run_id,
            ticket_id=ticket_id,
            task_id=target["id"],
            task_version=target["version"],
            bindings=source_run.get("bindings", {}),
            attempt=attempt,
            chain_depth=source_run["chain_depth"] + 1,
            parent_run_id=source_run["run_id"],
            handoff_key=h.key,
            repo=h.repo or source_run.get("repo"),
            input_artifacts=list(h.artifacts or []),
        )
        applied.append(run_id)
        txn.append_event(
            ticket_id,
            Event(
                event_id=f"{source_run['run_id']}:{h.key}:accepted",
                kind="handoff.accepted",
                ticket_id=ticket_id,
                run_id=source_run["run_id"],
                detail=h.reason,
            ).to_dict(),
        )
    return applied, None


def _predecessor_rejection(store, ticket_id: str, run_id: str) -> tuple[str, str] | None:
    """`(source_suffix, detail)` for a collect-time rejection of `run_id`.

    Looks for the most recent `handoff.rejected` or `run.artifact_rejected`
    on the failed attempt -- callers write those events before invoking
    `_handle_failure`. Returns None for ordinary failures (runner-lost,
    execute outcome=failure) that have nothing useful to tell the retry.
    """
    for event in reversed(store.read_events(ticket_id)):
        if event.get("run_id") != run_id:
            continue
        kind = event.get("kind")
        if kind == "handoff.rejected":
            return "handoff_rejected", event.get("detail") or "control output rejected"
        if kind == "run.artifact_rejected":
            return "artifact_rejected", event.get("detail") or "artifact rejected"
    return None


def _handle_failure(
    store,
    config,
    taskdefs,
    taskdef,
    ticket_id,
    run: dict,
    adapter_fn,
    *,
    block_on_unknown_usage: bool,
) -> None:
    """Retry policy for a run already marked FAILED (root-cause shared by the
    runner's collect-failure path and the dispatcher's runner-lost sweep).

    - collect path (block_on_unknown_usage=True): an attempt that ran but
      reported unknown usage BLOCKS the ticket and never retries (real spend
      is unknown).
    - runner-lost/timeout sweep (block_on_unknown_usage=False): the attempt
      never collected, so retry from scratch (D1) up to budget.retries.

    When a retry is queued after `handoff.rejected` / `run.artifact_rejected`,
    a `run.rework` event on the NEW run carries the predecessor's rejection
    into prepare's `## Requested changes` channel -- otherwise attempt N+1
    repeats the same schema/artifact mistake blind.
    """
    run_id = run["run_id"]
    if block_on_unknown_usage and run.get("usage_known") is False:
        _block_ticket(
            store, config, adapter_fn, ticket_id, run_id, "attempt failed with unknown spend"
        )
        _escalate(
            store,
            config,
            adapter_fn,
            ticket_id,
            run_id,
            "Run failed with unknown spend; blocked pending human review.",
        )
        return
    if run["attempt"] < taskdef["budget"]["retries"]:
        new_run_id = reenqueue_same(store, run, taskdef, run["attempt"] + 1)
        pred = _predecessor_rejection(store, ticket_id, run_id)
        if pred is not None:
            suffix, detail = pred
            # Cap detail length: rejection text is agent-/schema-authored and
            # lands in the next prompt; keep it concise and secret-safe-ish.
            concise = " ".join(str(detail).split())
            if len(concise) > 500:
                concise = concise[:497] + "..."
            store.write(
                lambda txn: txn.append_event(
                    ticket_id,
                    Event(
                        event_id=f"{new_run_id}:rework",
                        kind="run.rework",
                        ticket_id=ticket_id,
                        run_id=new_run_id,
                        detail=f"Previous attempt rejected: {concise}",
                        actor="engine",
                        source=f"{run_id}:{suffix}",
                    ).to_dict(),
                )
            )
        return
    _block_ticket(store, config, adapter_fn, ticket_id, run_id, "retries exhausted")
    # Escalate, exactly like the unknown-spend block above. Retries-exhausted
    # is the failure mode that most needs a human -- the ticket stops dead and
    # only a manual re-enqueue restarts it -- and it was the one that told
    # nobody: the block landed on the state branch while the issue still read
    # "work has been queued". When the last attempt was an artifact rejection
    # (e.g. dishonest qa-report), surface that detail so the issue is not only
    # "retries exhausted".
    escalate_msg = (
        f"`{taskdef['id']}` failed {run['attempt'] + 1} time(s) and exhausted its retry budget; "
        "the ticket is blocked pending human review."
    )
    pred = _predecessor_rejection(store, ticket_id, run_id)
    if pred is not None and pred[0] == "artifact_rejected":
        concise = " ".join(str(pred[1]).split())
        if len(concise) > 500:
            concise = concise[:497] + "..."
        escalate_msg = f"{escalate_msg} Rejected: {concise}"
    _escalate(
        store,
        config,
        adapter_fn,
        ticket_id,
        run_id,
        escalate_msg,
    )


# --------------------------------------------------------------------------
# Sweep: reconcile in-flight runs before the trigger stage.
# --------------------------------------------------------------------------


def _mark_failed(store, ticket_id, run_id, kind: str, event_suffix: str) -> None:
    def fn(txn: Txn) -> None:
        txn.update_run(ticket_id, run_id, state="FAILED")
        txn.append_event(
            ticket_id,
            Event(
                event_id=f"{run_id}:{event_suffix}",
                kind=kind,
                ticket_id=ticket_id,
                run_id=run_id,
                state=RunState.FAILED,
            ).to_dict(),
        )

    store.write(fn)


def sweep(
    config,
    taskdefs,
    store,
    workflow_api,
    now_iso: str,
    adapter_fn: AdapterFn,
    ticket_ids: list[str] | None = None,
) -> None:
    """Reconcile in-flight runs: fail lost/timed-out RUNNING runs (then retry
    per policy) and resolve WAITING_GATE runs against the gate adapter. Runs
    before the trigger stage so freed capacity is visible.

    `ticket_ids`, when given, narrows the sweep to just those tickets (the
    dispatcher's issue-scoped fast path); a full, unscoped sweep still scans
    every ticket, so gate timeouts and lost-run detection never depend
    solely on a scoped call landing.
    """

    def handle_running(taskdef, ticket_id, run) -> None:
        run_id = run["run_id"]
        lost = not workflow_api.active_workflow(f"agent-hq/{run_id}")
        past_deadline = bool(run.get("deadline")) and now_iso > run["deadline"]
        grace_expired = bool(run.get("attempt_started_at")) and now_iso > _add_minutes(
            run["attempt_started_at"], RUNNER_LOST_GRACE_MIN
        )
        if not (past_deadline or (lost and grace_expired)):
            return
        if lost and not past_deadline:
            _mark_failed(store, ticket_id, run_id, "run.runner_lost", "runner_lost")
        else:
            _mark_failed(store, ticket_id, run_id, "run.failed", "failed")
        failed = {**run, "state": "FAILED"}
        _handle_failure(
            store,
            config,
            taskdefs,
            taskdef,
            ticket_id,
            failed,
            adapter_fn,
            block_on_unknown_usage=False,
        )

    def handle_gate(taskdef, ticket_id, run) -> None:
        run_id = run["run_id"]
        gate_entry = (taskdef.get("gates", {}).get("post") or [{}])[0]
        if gate_entry.get("auto_approve"):
            # Same decision as the collect-time path, for a run that was
            # already parked when the flag went on: turning auto_approve on
            # drains the gates already waiting, rather than stranding them
            # behind a flag that says they need no human. No gate adapter and
            # no repo lookup -- there is nothing to ask.
            decision = GateDecision(
                GateStatus.APPROVED,
                f"auto-approved by task config (would have asked {gate_entry.get('approvers')})",
            )
            # This run's request comment is already in the thread asking for a
            # decision that will now never come, so say so under it. (A run
            # auto-approved at collect time needs no such notice -- its comment
            # never asked.) Idempotent by event id.
            notify_ticket(
                config,
                adapter_fn,
                ticket_id,
                f"Gate `{taskdef['id']}` was auto-approved by task config after the request "
                f"above was posted — `auto_approve` was turned on while this run was waiting. "
                f"No decision is needed.",
                f"{run_id}:auto_approval",
            )
        else:
            timeout = gate_entry.get("timeout_working_hours")
            repo = (
                run.get("repo")
                or _target_repo(config, adapter_fn, ticket_id)
                or next(iter(config.repos))
            )
            gate = adapter_fn("gate", run.get("bindings", {}).get("gate", "pr-review"), repo=repo)
            decision = gate.status(
                {
                    **run,
                    "timeout_working_hours": timeout,
                    "approver_group": gate_entry.get("approvers"),
                }
            )
        status = decision.status.value if hasattr(decision.status, "value") else decision.status

        if status != "PENDING":
            # Back to ACTIVE on "a decision exists", before the branches below
            # -- several of them return early, and `hq:waiting-gate` means "a
            # human is holding this up", which stopped being true the moment
            # the decision landed. A branch that then blocks the ticket
            # overwrites this with `hq:blocked` via `_block_ticket`.
            set_status_label(config, adapter_fn, ticket_id, "ACTIVE")

        if status == "APPROVED":
            pending = [Handoff.from_dict(h) for h in (run.get("pending_handoffs") or [])]
            result: dict = {}

            def approve(txn: Txn) -> None:
                applied_ids, apply_reason = apply_queue(
                    txn, config, taskdefs, ticket_id, run, pending
                )
                result["applied_ids"] = applied_ids
                result["apply_reason"] = apply_reason
                if apply_reason is not None:
                    return
                txn.update_run(ticket_id, run_id, state="SUCCEEDED", pending_handoffs=[])
                txn.append_event(
                    ticket_id,
                    Event(
                        event_id=f"{run_id}:succeeded",
                        kind="run.succeeded",
                        ticket_id=ticket_id,
                        run_id=run_id,
                        state=RunState.SUCCEEDED,
                    ).to_dict(),
                )
                if decision.comment_id is not None:
                    txn.append_event(
                        ticket_id,
                        Event(
                            event_id=f"{decision.comment_id}:approval",
                            kind="gate.decided",
                            ticket_id=ticket_id,
                            run_id=run_id,
                            detail=f"approved by {decision.actor} at {decision.decided_at}",
                            actor=decision.actor,
                            source=str(decision.comment_id),
                        ).to_dict(),
                    )
                elif gate_entry.get("auto_approve"):
                    txn.append_event(
                        ticket_id,
                        Event(
                            event_id=f"{run_id}:auto_approval",
                            kind="gate.decided",
                            ticket_id=ticket_id,
                            run_id=run_id,
                            detail=decision.comments,
                            # No human decided this one; that is the audit fact,
                            # so it is stated rather than left absent.
                            actor="engine",
                        ).to_dict(),
                    )

            store.write(approve)
            if result["apply_reason"] is not None:
                _mark_gate_terminal(store, ticket_id, run, "run.failed", "handoff_apply_failed")
                _block_ticket(store, config, adapter_fn, ticket_id, run_id, result["apply_reason"])
                return
            _complete_if_queue_empty(
                store, config, adapter_fn, ticket_id, {**run, "state": "SUCCEEDED"}
            )
        elif status == "CHANGES_REQUESTED":
            src = str(decision.comment_id) if decision.comment_id is not None else None
            if run["attempt"] >= 2:
                _mark_gate_terminal(
                    store,
                    ticket_id,
                    run,
                    "run.rework",
                    "rework_final",
                    actor=decision.actor,
                    source=src,
                )
                _block_ticket(
                    store,
                    config,
                    adapter_fn,
                    ticket_id,
                    run_id,
                    "max rework cycles reached",
                    actor=decision.actor,
                    source=src,
                )
                return
            _mark_gate_terminal(
                store,
                ticket_id,
                run,
                "run.changes_requested",
                "changes_requested",
                actor=decision.actor,
                source=src,
            )
            new_run_id = reenqueue_same(store, run, taskdef, run["attempt"] + 1)
            store.write(
                lambda txn: txn.append_event(
                    ticket_id,
                    Event(
                        event_id=f"{new_run_id}:rework",
                        kind="run.rework",
                        ticket_id=ticket_id,
                        run_id=new_run_id,
                        detail=decision.comments,
                        actor=decision.actor,
                        source=src,
                    ).to_dict(),
                )
            )
        elif status == "REJECTED":
            src = str(decision.comment_id) if decision.comment_id is not None else None
            _mark_gate_terminal(
                store,
                ticket_id,
                run,
                "run.rejected",
                "rejected",
                actor=decision.actor,
                source=src,
            )
            _block_ticket(
                store,
                config,
                adapter_fn,
                ticket_id,
                run_id,
                decision.comments or "gate rejected",
                actor=decision.actor,
                source=src,
            )
        elif status == "EXPIRED":
            # Nobody decided -- the clock did. `actor="engine"` states that
            # rather than leaving a reader to wonder who rejected it.
            _mark_gate_terminal(
                store,
                ticket_id,
                run,
                "run.gate_expired",
                "gate_expired",
                actor="engine",
            )
            _block_ticket(
                store,
                config,
                adapter_fn,
                ticket_id,
                run_id,
                "gate timed out",
                actor="engine",
            )
            _escalate(
                store,
                config,
                adapter_fn,
                ticket_id,
                run_id,
                "Review gate expired without a decision; blocked pending escalation.",
            )
        # PENDING: leave the run WAITING_GATE.

    for ticket_id in ticket_ids if ticket_ids is not None else store.list_tickets():
        state = store.read_state(ticket_id)
        if state is None:
            continue
        # Deferred only while a run is genuinely WORKING (RUNNING/WAITING_GATE),
        # not while one merely sits QUEUED. A run enqueued mid-flight would race
        # the run already working the same branch -- that is the hazard, and a
        # queued sibling is not it: per-ticket exclusivity (`claim_run`) means
        # two runs never execute at once, so a queued sibling just waits its
        # turn. Nothing is lost by deferring -- the watermark only advances on a
        # pass that actually polls, so the comment is still there next sweep.
        #
        # Counting QUEUED here used to make two things impossible: polling a
        # BLOCKED ticket that still had work queued behind it (dispatch skips
        # BLOCKED tickets, so that run is going nowhere and would have vetoed
        # the poll that releases it, forever), and inserting a comment at the
        # FRONT of a non-empty queue -- which is the whole point of a comment
        # being an interjection.
        working = any(r["state"] in EXCLUSIVE_STATES for r in state.get("runs", []))
        if state.get("status") in ("ACTIVE", "AWAITING_MERGE", "BLOCKED") and not working:
            poll_comments(store, config, taskdefs, adapter_fn, ticket_id, state)
            state = store.read_state(ticket_id) or state
        if state.get("status") == "AWAITING_MERGE":
            # Every run on an AWAITING_MERGE ticket is terminal by
            # construction, so the run loop below finds nothing to do here.
            resolve_awaiting_merge(store, config, adapter_fn, ticket_id, state)
            continue
        for run in list(state.get("runs", [])):
            taskdef = taskdefs.get(run["task_id"])
            if taskdef is None:
                continue
            if run["state"] == "RUNNING":
                handle_running(taskdef, ticket_id, run)
            elif run["state"] == "WAITING_GATE":
                handle_gate(taskdef, ticket_id, run)


def _mark_gate_terminal(
    store,
    ticket_id,
    run: dict,
    kind: str,
    event_suffix: str,
    *,
    actor: str | None = None,
    source: str | None = None,
) -> None:
    """Terminalize a WAITING_GATE run FAILED, clearing any `pending_handoffs`
    and emitting `handoff.rejected` (each carrying that handoff's own
    `reason`) for every one of them, all in the SAME write -- else
    completion's "no pending handoffs" check never passes.

    `actor`/`source` land on the terminalizing event only: the per-handoff
    `handoff.rejected` events are mechanical consequences, so leaving their
    actor absent is the honest reading."""
    run_id = run["run_id"]
    pending = run.get("pending_handoffs") or []

    def fn(txn: Txn) -> None:
        txn.update_run(ticket_id, run_id, state="FAILED", pending_handoffs=[])
        txn.append_event(
            ticket_id,
            Event(
                event_id=f"{run_id}:{event_suffix}",
                kind=kind,
                ticket_id=ticket_id,
                run_id=run_id,
                state=RunState.FAILED,
                actor=actor,
                source=source,
            ).to_dict(),
        )
        for h in pending:
            txn.append_event(
                ticket_id,
                Event(
                    event_id=f"{run_id}:{h['key']}:rejected",
                    kind="handoff.rejected",
                    ticket_id=ticket_id,
                    run_id=run_id,
                    detail=h.get("reason"),
                ).to_dict(),
            )

    store.write(fn)


def _complete_if_queue_empty(store, config, adapter_fn, ticket_id, terminal_run: dict) -> None:
    """After a terminal SUCCEEDED with nothing else in flight and no pending
    entries anywhere on the ticket: post the closing summary and mark every
    recorded work PR ready -- but only if the terminal run IS the route's
    designed end, meaning its task is `projects.final_task`. A queue that ran
    dry anywhere else stopped early, which is a human's problem, so the ticket
    BLOCKs with that reason instead of pinning a note nobody is paged for.

    `final_task` is config, not a filename. This used to key off whether the
    terminal run produced `specs/{ticket}/summary.md` -- a filename convention
    the engine had to know, sitting oddly beside "the engine special-cases no
    task name". Naming the task in `config/projects.yml` is the same shape as
    `initial_task` and `feedback_task` already are, and it makes "the route
    finished" and "someone wrote a file with the right name" stop being the
    same question.

    The engine's work being finished is NOT the ticket being finished. With a
    work PR recorded, this stops at `AWAITING_MERGE` and leaves the issue
    OPEN: whether a human merges is the answer to "is this done", and closing
    at ready-time told the tracker "done" while the code was still unreviewed
    -- and left a reviewer arriving later commenting on a closed ticket.
    `resolve_awaiting_merge` (the sweep) takes it from here. With no PR
    anywhere (a ticket that changed no code) there is nothing to wait on, so
    it completes to DONE exactly as before.

    ponytail: idempotency keyed off the status each phase transitions OUT of
    -- this one requires `ACTIVE`, its sweep counterpart requires
    `AWAITING_MERGE`, so neither can re-fire -- plus the tracker methods' own
    event-marker dedup, rather than a separate `{ticket}:{run}:done` record.
    """
    state = store.read_state(ticket_id)
    if state is None or state.get("status") != "ACTIVE":
        return
    runs = state.get("runs", [])
    if any(r["state"] in NON_TERMINAL for r in runs):
        return
    if any(r.get("pending_handoffs") for r in runs):
        return

    tracker = adapter_fn(
        "tracker", config.components["tracker"]["adapter"], repo=intake_repo(config)
    )
    done_key = f"{ticket_id}:{terminal_run['run_id']}:done"
    final_task = config.projects.get("final_task")
    if not final_task or terminal_run.get("task_id") != final_task:
        # The queue drained somewhere other than the route's end. BLOCKED
        # rather than a pinned note: this is the state that means "a human must
        # act", it labels the issue `hq:blocked`, it escalates, and it is
        # exitable -- where `hq:active` with nothing running told an operator
        # the engine was still working.
        reason = (
            f"queue ran dry after `{terminal_run.get('task_id')}` without reaching "
            f"`{final_task or '<no final_task configured>'}`"
        )
        _block_ticket(store, config, adapter_fn, ticket_id, terminal_run["run_id"], reason)
        _escalate(
            store,
            config,
            adapter_fn,
            ticket_id,
            terminal_run["run_id"],
            f"{reason}; the ticket is blocked pending human review.",
        )
        return

    summary_path = subst("specs/{ticket}/summary.md", ticket_id)
    summary = store.read_artifact_text(ticket_id, terminal_run["run_id"], summary_path) or ""
    tracker.post_closing_summary(ticket_id, summary, f"{done_key}:closing-summary")
    watched = [wr for wr in state.get("work_repos", []) if wr.get("pr_ref")]
    for work_repo in watched:
        agent = adapter_fn(
            "agent-session",
            config.components["agent-session"]["adapter"],
            repo=work_repo["repo"],
        )
        agent.mark_pr_ready(work_repo["pr_ref"])

    if not watched:
        tracker.close_issue(ticket_id)
        store.write(lambda txn: txn.set_ticket(ticket_id, status="DONE"))
        set_status_label(config, adapter_fn, ticket_id, "DONE")
        return

    store.write(lambda txn: txn.set_ticket(ticket_id, status="AWAITING_MERGE"))
    set_status_label(config, adapter_fn, ticket_id, "AWAITING_MERGE")
    notify_ticket(
        config,
        adapter_fn,
        ticket_id,
        "Engine work is complete and "
        + ", ".join(wr["pr_ref"] for wr in watched)
        + " is ready for review. This issue stays open until the PR is merged or "
        "closed; comment `/agent-hq request-changes <reason>` on the PR to send work "
        "back.",
        f"{done_key}:awaiting-merge",
    )


# Every comment the engine authors carries an `<!--hq:...-->` marker: the
# messaging adapter's event-id dedupe marker, or the pinned-comment marker. That
# makes the marker a reliable "this is ours" signal without the engine having to
# know its own tracker identity.
_HQ_COMMENT_MARKER = "<!--hq:"

# What the poller leaves on a comment it read, so a human can tell "acted on"
# from "not looked at yet" without waiting to see whether a run appears.
# Reactions rather than replies because they are idempotent at the API -- the
# watermark is inclusive at the boundary second, so a comment can be re-read,
# and a reply would duplicate where a reaction cannot.
REACTION_QUEUED = "rocket"  # this comment produced a run
REACTION_IGNORED = "eyes"  # read, understood to ask for nothing, no run


def _comment_intent(
    body: str, *, feedback_task: str | None, default_task: str | None
) -> tuple[str, str] | None:
    """Which task a comment asks for, as `(task_id, reason)`, or None.

    Three forms, most specific first:
    - `/agent-hq request-changes <reason>` -> `projects.feedback_task`
    - `/agent-hq do <task> [reason]`       -> that task
    - anything else                        -> `default_task` if the caller
      passes one (only the engine issue does), else nothing

    The task id is returned unvalidated; the caller checks it against the loaded
    library, because an unknown task deserves a reply rather than silence.
    """
    parsed = parse_decision(body, "")
    if parsed is not None and parsed[0] == "request-changes":
        return (feedback_task, parsed[1]) if feedback_task else None
    queued = parse_queue_command(body)
    if queued is not None:
        return queued
    if default_task:
        return default_task, body.strip()
    return None


def _is_bare_default_intent(body: str, *, default_task: str | None) -> bool:
    """True when the comment maps to `default_task` only because no command
    was given -- not an explicit `/agent-hq do <default_task>` or
    `request-changes`. Intake-block recovery applies only to this case; an
    explicit command still steers mid-route even while intake-blocked.
    """
    if not default_task:
        return False
    parsed = parse_decision(body, "")
    if parsed is not None and parsed[0] == "request-changes":
        return False
    return parse_queue_command(body) is None


def _comment_run_count(doc: dict, prefixes: tuple[str, ...]) -> int:
    return sum(
        1 for r in doc.get("runs", []) if str(r.get("source_event_id") or "").startswith(prefixes)
    )


_COMMENT_SOURCE_PREFIXES = ("issue-comment:", "pr-comment:")


def poll_comments(store, config, taskdefs, adapter_fn, ticket_id: str, state: dict) -> None:
    """Turn authorized comments into queued work, on the engine issue and on
    every recorded work PR.

    The engine issue is the ticket-level control surface: it is where intake,
    gate requests, pinned status and escalations are already posted, so it was
    the one place the engine talked without listening. A work PR stays a
    subject too, but a narrower one -- see `_poll_comment_subject`.

    Polled from `sweep` rather than driven by events, for the same reason
    `resolve_awaiting_merge` is: the engine repository cannot observe
    product-repo events at all.
    """
    feedback_task = config.projects.get("feedback_task")
    default_task = config.projects.get("comment_default_task")
    group = config.projects.get("feedback_approvers")
    if not group:
        return
    members = set(config.approvers.get("groups", {}).get(group, {}).get("members", []))
    if not members:
        return

    # The engine issue: ticket-level watermark, and the only subject where a
    # bare approver comment (no command) may act, because it is a narrower
    # audience than a work PR.
    if feedback_task or default_task:
        _poll_comment_subject(
            store,
            config,
            taskdefs,
            adapter_fn,
            ticket_id,
            repo=intake_repo(config),
            number=ticket_id,
            source_prefix="issue-comment",
            watermark=state.get("comments_polled_at"),
            save_watermark=lambda txn, w: txn.set_ticket(ticket_id, comments_polled_at=w),
            members=members,
            feedback_task=feedback_task,
            default_task=default_task,
            ack=lambda message, event_id: notify_ticket(
                config, adapter_fn, ticket_id, message, event_id
            ),
        )

    for work_repo in list(state.get("work_repos", [])):
        pr_ref = work_repo.get("pr_ref")
        if not pr_ref:
            continue
        repo, _, number = pr_ref.rpartition("#")
        _poll_comment_subject(
            store,
            config,
            taskdefs,
            adapter_fn,
            ticket_id,
            repo=repo,
            number=number,
            source_prefix="pr-comment",
            watermark=work_repo.get("comments_polled_at"),
            save_watermark=lambda txn, w, r=repo: txn.upsert_work_repo(
                ticket_id, r, comments_polled_at=w
            ),
            members=members,
            feedback_task=feedback_task,
            # A PR is a wider, lower-trust audience than the engine issue, so an
            # explicit command is still required there -- "an approver said
            # something" never spends budget from a PR thread.
            default_task=None,
            run_repo=repo,
            ack=lambda message, event_id, pr=pr_ref: post_pr_comment(
                config, adapter_fn, pr, message, event_id
            ),
        )


def _acknowledge(messaging, considered: list[dict], queued_ids: set) -> None:
    """React to every comment the poller read, saying what became of it.

    Best-effort and last: a reaction is feedback, never state, so a tracker that
    rejects one must not fail a poll that already landed its run.
    """
    for comment in considered:
        content = REACTION_QUEUED if comment["id"] in queued_ids else REACTION_IGNORED
        try:
            messaging.react(comment["id"], content)
        except Exception:  # noqa: BLE001,S110 -- feedback, not state; see docstring
            pass


def _intake_comment_readmit(
    store,
    config,
    taskdefs,
    adapter_fn,
    ticket_id: str,
    *,
    messaging,
    considered,
    qualifying_ids,
    latest_read,
    save_watermark,
    ack,
    source_event_id: str,
    rework_detail: str,
    rework_actor: str,
) -> None:
    """Re-admit an intake-blocked ticket from a bare approver comment.

    Mirrors `intake_ticket`'s eligibility + root enqueue: if the ticket now
    matches a product area (etc.), clear the intake block and queue
    `initial_task` with the resolved repo. If still ineligible, ack the
    reasons and queue nothing -- burning triage here was how tickets 4/8
    spent retries on a ticket that never started.
    """
    tracker = adapter_fn(
        "tracker", config.components["tracker"]["adapter"], repo=intake_repo(config)
    )
    details = tracker.fetch_ticket(ticket_id)
    reasons = list(eligibility_reasons(config, details))
    if has_injection(details):
        reasons.append("prompt-injection pattern detected in ticket text")

    if reasons:
        store.write(lambda txn, w=latest_read: save_watermark(txn, w))
        body = "Still not eligible for intake:\n" + "\n".join(f"- {r}" for r in reasons)
        ack(body, f"{source_event_id}:intake-still-ineligible")
        _acknowledge(messaging, considered, set())
        return

    initial_task_id = config.projects["initial_task"]
    if initial_task_id not in taskdefs:
        store.write(lambda txn, w=latest_read: save_watermark(txn, w))
        ack(
            f"`{initial_task_id}` is not a task in this deployment, so nothing was queued.",
            f"{source_event_id}:unknown-task",
        )
        _acknowledge(messaging, considered, set())
        return

    taskdef = taskdefs[initial_task_id]
    repo = resolve_target_repo(config, details)
    run_id = compute_run_id(source_event_id, 0, initial_task_id, 0)
    result: dict = {}

    def apply(txn: Txn) -> None:
        result.clear()
        save_watermark(txn, latest_read)
        doc = txn.ticket_doc(ticket_id)
        if doc.get("block_source") != "intake":
            # Another writer cleared the intake block between our read and
            # this write; do not invent a second root run.
            return
        cap = config.budgets.get("max_comment_runs_per_ticket")
        if cap is not None and _comment_run_count(doc, _COMMENT_SOURCE_PREFIXES) >= cap:
            result["refused"] = f"this ticket has already spent its {cap} comment-triggered runs"
            return
        ok, _trace = check_loop_guard(doc, max_runs=config.budgets["loop_guard"]["max_runs"])
        verdict = check_budget(doc, taskdef["budget"], config.budgets["ticket_cap_usd"])
        if not ok or verdict["over_ticket_cap"] or verdict["insufficient_headroom"]:
            result["refused"] = "comment would exceed this ticket's run/budget ceiling"
            return
        seq = _insert_at_queue_head(txn, ticket_id)
        if not _put_queued_run(
            txn,
            run_id,
            ticket_id=ticket_id,
            task_id=initial_task_id,
            task_version=taskdef["version"],
            bindings={},
            attempt=0,
            chain_depth=0,
            source_event_id=source_event_id,
            enqueue_index=0,
            repo=repo,
            queue_seq=seq,
        ):
            return
        # Same channel as the normal comment path: prepare inlines this under
        # "## Requested changes" so the new root run sees the human's retry note.
        detail = rework_detail
        if doc.get("block_reason"):
            detail = f"{detail}\n\n(ticket was blocked: {doc['block_reason']})".lstrip()
        txn.append_event(
            ticket_id,
            Event(
                event_id=f"{run_id}:rework",
                kind="run.rework",
                ticket_id=ticket_id,
                run_id=run_id,
                detail=detail,
                actor=rework_actor,
                source=source_event_id,
            ).to_dict(),
        )
        txn.set_ticket(
            ticket_id,
            status="ACTIVE",
            block_reason=None,
            block_source=None,
            interrupted_run_id=None,
        )
        result["enqueued"] = run_id

    store.write(apply)

    if result.get("refused"):
        # Keep block_source=intake so a later bare retry still hits this path
        # instead of falling through to comment_default_task (triage).
        _acknowledge(messaging, considered, set())
        _block_ticket(
            store,
            config,
            adapter_fn,
            ticket_id,
            run_id,
            result["refused"],
            block_source="intake",
        )
        _escalate(store, config, adapter_fn, ticket_id, run_id, result["refused"])
        return
    if result.get("enqueued"):
        _acknowledge(messaging, considered, qualifying_ids)
        set_status_label(config, adapter_fn, ticket_id, "ACTIVE")
        ack(
            f"Re-admitted after intake block; queued `{initial_task_id}`.",
            f"{run_id}:ack",
        )
    else:
        # Race / enqueue no-op: nothing was queued -- eyes, not rocket.
        _acknowledge(messaging, considered, set())


def _poll_comment_subject(
    store,
    config,
    taskdefs,
    adapter_fn,
    ticket_id: str,
    *,
    repo: str,
    number: str,
    source_prefix: str,
    watermark: str | None,
    save_watermark,
    members: set[str],
    feedback_task: str | None,
    default_task: str | None,
    ack,
    run_repo: str | None = None,
) -> None:
    """Poll one comment thread and queue at most one run from it.

    Idempotency is the derived run id (`<source_prefix>:<latest comment id>`), so
    re-polling the same comment resolves to the same run and enqueues nothing.
    The watermark only keeps the read small -- it is not the dedupe. The two
    subjects use DIFFERENT prefixes: comment ids are unique per repository, not
    globally, and reusing one prefix would let an issue comment and a PR comment
    collide onto a single run.
    """
    messaging = adapter_fn("messaging", config.components["messaging"]["adapter"], repo=repo)
    comments = messaging.list_comments(number, watermark)
    if not comments:
        return

    requests = []
    considered = []
    for comment in comments:
        # Ordered cheapest-and-safest first. The marker check is what stops
        # `block -> _escalate posts a comment -> run -> block` from being an
        # unbounded spend loop: escalations, pins and gate requests all land on
        # the engine issue, so the moment it became a polled subject the engine
        # could answer itself. Membership alone would usually catch it (the
        # engine's identity is not an approver), but that depends on config
        # hygiene and this does not.
        if _HQ_COMMENT_MARKER in (comment.get("body") or ""):
            # The engine's own comment. Not acknowledged either -- reacting to
            # itself would be noise, and it is the one thing that definitely
            # was not waiting for an answer.
            continue
        # Everything past here gets an outcome reaction, INCLUDING comments from
        # non-approvers. "Read, not authorized" is exactly the signal that is
        # otherwise invisible: without it a non-approver's comment and an
        # unpolled thread look identical from the issue.
        considered.append(comment)
        if comment["author"] not in members:
            continue
        intent = _comment_intent(
            comment["body"], feedback_task=feedback_task, default_task=default_task
        )
        if intent is None:
            continue
        requests.append((comment, intent))

    # Advance past everything read, qualifying or not -- a thread of ordinary
    # conversation must not be re-read every sweep forever.
    latest_read = max(c["created_at"] for c in comments)

    if not requests:
        store.write(lambda txn, w=latest_read: save_watermark(txn, w))
        _acknowledge(messaging, considered, set())
        return

    # One run for the whole window: three comments asking for three things are
    # one piece of work, not three runs racing for the same branch. The LAST
    # qualifying comment picks the task and owns the run's identity; every
    # comment's text goes into the reason.
    latest_comment, (task_id, _) = requests[-1]
    reason = "\n\n".join(f"@{c['author']}: {text}" for c, (_, text) in requests if text)
    source_event_id = f"{source_prefix}:{latest_comment['id']}"

    qualifying_ids = {c["id"] for c, _ in requests}

    if task_id not in taskdefs:
        # A typo deserves an answer. Idempotent by comment id, so at most one
        # reply per comment however often the sweep re-reads it.
        store.write(lambda txn, w=latest_read: save_watermark(txn, w))
        ack(
            f"`{task_id}` is not a task in this deployment, so nothing was queued.",
            f"{source_event_id}:unknown-task",
        )
        # Named a task, so it was not ignored -- but nothing ran. The reply
        # above carries the detail; the reaction just keeps every read comment
        # accounted for.
        _acknowledge(messaging, considered, set())
        return

    # Intake-blocked + bare "retry" comment: re-check eligibility instead of
    # burning comment_default_task (triage) on a ticket that never started.
    # Explicit `/agent-hq do …` still steers mid-route as usual.
    ticket_state = store.read_state(ticket_id) or {}
    if (
        ticket_state.get("block_source") == "intake"
        and default_task
        and task_id == default_task
        and _is_bare_default_intent(latest_comment["body"], default_task=default_task)
    ):
        _intake_comment_readmit(
            store,
            config,
            taskdefs,
            adapter_fn,
            ticket_id,
            messaging=messaging,
            considered=considered,
            qualifying_ids=qualifying_ids,
            latest_read=latest_read,
            save_watermark=save_watermark,
            ack=ack,
            source_event_id=source_event_id,
            rework_detail=reason,
            rework_actor=latest_comment["author"],
        )
        return

    taskdef = taskdefs[task_id]
    run_id = compute_run_id(source_event_id, 0, task_id, 0)
    result: dict = {}

    def apply(txn: Txn) -> None:
        # Cleared per attempt, like `claim_run`'s own flag: a write that loses
        # the push race re-runs this against fresh state, and only the attempt
        # that actually lands may decide the outcome.
        result.clear()
        save_watermark(txn, latest_read)
        doc = txn.ticket_doc(ticket_id)

        # A separate ceiling from `loop_guard.max_runs`: a chatty thread would
        # otherwise exhaust the ticket's run budget, block it, and then have the
        # next comment unblock it -- a slow oscillation that spends real money.
        cap = config.budgets.get("max_comment_runs_per_ticket")
        if cap is not None and _comment_run_count(doc, _COMMENT_SOURCE_PREFIXES) >= cap:
            result["refused"] = f"this ticket has already spent its {cap} comment-triggered runs"
            return
        ok, _trace = check_loop_guard(doc, max_runs=config.budgets["loop_guard"]["max_runs"])
        verdict = check_budget(doc, taskdef["budget"], config.budgets["ticket_cap_usd"])
        if not ok or verdict["over_ticket_cap"] or verdict["insufficient_headroom"]:
            result["refused"] = "comment would exceed this ticket's run/budget ceiling"
            return

        # At the FRONT of the queue: a comment is an interjection, so it runs
        # before work already planned rather than behind it. Nothing else about
        # the queue is disturbed.
        seq = _insert_at_queue_head(txn, ticket_id)
        if not _put_queued_run(
            txn,
            run_id,
            ticket_id=ticket_id,
            task_id=task_id,
            task_version=taskdef["version"],
            bindings={},
            attempt=0,
            chain_depth=0,
            source_event_id=source_event_id,
            enqueue_index=0,
            repo=run_repo,
            queue_seq=seq,
        ):
            return  # already applied on an earlier pass
        # `_rework_comments` reads this back at prepare and inlines it under
        # "## Requested changes" -- the same channel the gate's own
        # CHANGES_REQUESTED path uses. A blocked ticket's reason rides along, so
        # a task asked to re-plan can see why the ticket stopped.
        detail = reason
        if doc.get("block_reason"):
            detail = f"{detail}\n\n(ticket was blocked: {doc['block_reason']})".lstrip()
        txn.append_event(
            ticket_id,
            Event(
                event_id=f"{run_id}:rework",
                kind="run.rework",
                ticket_id=ticket_id,
                run_id=run_id,
                detail=detail,
                actor=latest_comment["author"],
                source=source_event_id,
            ).to_dict(),
        )
        # A comment is the exit from both waiting states. BLOCKED especially:
        # nothing else in the engine clears it, so before this the only routes
        # out were a full restart via re-label or hand-editing the state branch.
        if doc.get("status") in ("AWAITING_MERGE", "BLOCKED"):
            txn.set_ticket(
                ticket_id,
                status="ACTIVE",
                block_reason=None,
                block_source=None,
                interrupted_run_id=None,
            )
        result["enqueued"] = run_id

    store.write(apply)

    if result.get("refused"):
        # Refused loudly: the ticket blocks and escalates, so the reaction says
        # "no run" rather than pretending this was queued.
        _acknowledge(messaging, considered, set())
        _block_ticket(store, config, adapter_fn, ticket_id, run_id, result["refused"])
        _escalate(store, config, adapter_fn, ticket_id, run_id, result["refused"])
        return
    _acknowledge(messaging, considered, qualifying_ids)
    if result.get("enqueued"):
        set_status_label(config, adapter_fn, ticket_id, "ACTIVE")
        ack(f"Queued `{task_id}`.", f"{run_id}:ack")


def resolve_awaiting_merge(store, config, adapter_fn, ticket_id: str, state: dict) -> None:
    """Second half of completion: watch an `AWAITING_MERGE` ticket's recorded
    work PRs and finish the ticket when they resolve.

    Polled from `sweep` rather than driven by a `pull_request` event: the
    engine repository's workflows cannot observe product-repo events at all
    (no cross-repo forwarder exists -- `docs/roadmap.md`), and the sweep
    already visits every ticket, so a read per watched PR costs nothing new.

    - every PR merged -> the work landed: close the issue, ticket `DONE`
    - any PR closed unmerged -> a human declined the work. That needs a
      person, not a silent completion, so the ticket `BLOCKED`s and
      escalates. Checked FIRST: one abandoned PR outweighs merged siblings.
    - anything still open -> leave it for the next sweep

    Keyed off `status == "AWAITING_MERGE"` by its caller, the status
    `_complete_if_queue_empty` transitions INTO -- so the two halves cannot
    re-fire each other.
    """
    watched = [wr for wr in state.get("work_repos", []) if wr.get("pr_ref")]
    if not watched:
        # Defensive: phase A only parks here with a PR to watch, so this is
        # unreachable rather than a state to model -- but stranding a ticket
        # forever is the one outcome worth a guard.
        return

    pr_states = {}
    for work_repo in watched:
        agent = adapter_fn(
            "agent-session",
            config.components["agent-session"]["adapter"],
            repo=work_repo["repo"],
        )
        pr_states[work_repo["pr_ref"]] = agent.pr_state(work_repo["pr_ref"])

    # The run whose completion parked the ticket here -- gives the block and
    # escalation events a real causal id instead of a synthetic one.
    runs = state.get("runs", [])
    run_id = runs[-1]["run_id"] if runs else ""

    abandoned = [
        ref for ref, pr in pr_states.items() if pr["state"] == "closed" and not pr["merged"]
    ]
    if abandoned:
        reason = "work PR closed unmerged: " + ", ".join(sorted(abandoned))
        _block_ticket(store, config, adapter_fn, ticket_id, run_id, reason)
        _escalate(
            store,
            config,
            adapter_fn,
            ticket_id,
            run_id,
            f"{reason}. The engine finished its work, but the PR was closed without "
            "merging, so the ticket is blocked pending human review.",
        )
        return

    if not all(pr["merged"] for pr in pr_states.values()):
        return

    tracker = adapter_fn(
        "tracker", config.components["tracker"]["adapter"], repo=intake_repo(config)
    )
    notify_ticket(
        config,
        adapter_fn,
        ticket_id,
        "Merged: " + ", ".join(sorted(pr_states)) + ". Closing the ticket.",
        f"{ticket_id}:merged",
    )
    tracker.close_issue(ticket_id)
    store.write(lambda txn: txn.set_ticket(ticket_id, status="DONE"))
    set_status_label(config, adapter_fn, ticket_id, "DONE")


def _target_repo(config, adapter_fn, ticket_id) -> str | None:
    """Resolve a ticket's product repo by fetching it and matching product
    area. ponytail: one tracker fetch per gate sweep; cheap at pilot scale
    (<=3 in-flight), memoize if the sweep hot-loops."""
    tracker = adapter_fn(
        "tracker", config.components["tracker"]["adapter"], repo=intake_repo(config)
    )
    details = tracker.fetch_ticket(ticket_id)
    return resolve_target_repo(config, details)


def _inputs_ready(taskdef, run, state) -> bool:
    """TE-3: a task declaring input artifacts may only start once the run it
    reads from has recorded (a superset of) those artifacts. State-level check
    -- artifacts are recorded on that run's collect, so no git access needed.

    Gates on `resolve_input_source`, not `parent_run_id`: with a queue, `spec`
    can declare `implement` and `review` at once, and `review`'s inputs come
    from `implement`. Keyed on the enqueuer this would gate `review` on `spec`'s
    outputs -- passing vacuously, or never at all."""
    declared = taskdef.get("inputs", {}).get("artifacts", [])
    if not declared:
        return True
    source_id = resolve_input_source(state.get("runs", []), run)
    if not source_id:
        return True
    source = next((r for r in state["runs"] if r["run_id"] == source_id), None)
    if source is None:
        return False
    produced = set(source.get("artifacts", []))
    return all(subst(a, run["ticket_id"]) in produced for a in declared)


def dispatch(
    config,
    taskdefs,
    store,
    workflow_api,
    now_iso: str | None = None,
    adapter_fn: AdapterFn | None = None,
    issue: str | None = None,
) -> list[str]:
    """Two stages: sweep in-flight runs first, then trigger eligible QUEUED
    runs. `issue`, when given, is the dispatcher's fast path -- a wake-up
    producer that already knows which ticket changed narrows both stages to
    just that ticket; a scheduled/unscoped call still scans every active
    ticket, so nothing depends solely on a scoped call landing. Returns the
    run ids triggered this pass."""
    now_iso = now_iso or _now_iso()
    adapter_fn = adapter_fn or _default_adapter_fn(config)
    scope = [issue] if issue else None

    sweep(config, taskdefs, store, workflow_api, now_iso, adapter_fn, ticket_ids=scope)

    triggered: list[str] = []
    if kill_switch_active():
        return triggered

    budgets = config.budgets
    ticket_ids = scope if scope is not None else store.list_tickets()
    all_states = {tid: store.read_state(tid) for tid in ticket_ids}
    for ticket_id in ticket_ids:
        state = all_states[ticket_id]
        if state is None:
            continue
        if state.get("status") == "BLOCKED":
            continue
        # Queue order, not array order: a retry inherits the position of the
        # attempt it replaces, so it can sit earlier in the queue than runs
        # appended after that attempt failed. Stable, so equal positions keep
        # insertion order.
        positions = queue_positions(state.get("runs", []))
        for run in sorted(state.get("runs", []), key=lambda r: positions[r["run_id"]]):
            if run["state"] != "QUEUED":
                continue
            taskdef = taskdefs.get(run["task_id"])
            if taskdef is None:
                continue
            run_id = run["run_id"]

            # Current-state check, not the prospective (pre-insertion) one
            # `check_loop_guard` implements: this run was already accepted
            # onto the ticket (possibly exactly AT max_runs), so
            # only reject dispatch if the ticket is ALREADY beyond the
            # configured limit -- reusing the enqueue-time "<" ceiling here
            # would block a legitimately-queued boundary run before it ever
            # executes.
            runs = [r for r in state.get("runs", []) if r.get("state") != RunState.CANCELLED.value]
            if len(runs) > budgets["loop_guard"]["max_runs"]:
                _block_ticket(store, config, adapter_fn, ticket_id, run_id, "loop guard tripped")
                break

            verdict = check_budget(state, taskdef["budget"], budgets["ticket_cap_usd"])
            if verdict["over_ticket_cap"] or verdict["insufficient_headroom"]:
                _block_ticket(
                    store, config, adapter_fn, ticket_id, run_id, "ticket budget exhausted"
                )
                break

            if not check_concurrency(
                all_states, ticket_id, run_id=run_id, in_flight_cap=budgets["in_flight_cap"]
            ):
                continue
            if not _inputs_ready(taskdef, run, state):
                continue
            if workflow_api.active_workflow(f"agent-hq/{run_id}"):
                continue

            workflow_api.trigger_run(run_id)
            triggered.append(run_id)
    return triggered
