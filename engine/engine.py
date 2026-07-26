"""Engine core: causal enqueue and the concurrency/loop/budget/kill guards
(§5.2).

Guard functions are pure (state docs / config in, verdict out) so dispatch
logic (Task 13) can compose them without re-reading the state store.
"""

from __future__ import annotations

import os
from collections.abc import Callable

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
# The one engine-owned issue label that tracks run state (see set_gate_label).
GATE_LABEL = "hq:waiting-gate"


def _put_queued_run(txn: Txn, run_id: str, *, ticket_id: str, task_id: str, task_version: int,
                    bindings: dict[str, str], **fields) -> bool:
    """Insert a QUEUED run (idempotent by run_id) plus its run.queued event.
    Returns True if newly inserted, False if it already existed (no-op) --
    shared by every run-creation path (`enqueue`, `apply_handoffs`,
    `reenqueue_same`'s handoff branch) so identity/idempotency is enforced
    in exactly one place."""
    if txn.get_run(ticket_id, run_id) is not None:
        return False
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
) -> str:
    """Enqueue a QUEUED run for `task_id`, idempotent by run_id.

    run_id is derived from the causal parent (a parent run's run_id, or a
    source event key for a root enqueue) plus enqueue_index/task_id/attempt,
    so a duplicate call with the same inputs is a no-op rather than a second
    run record. Used for the intake root run only -- a handoff-spawned run
    uses `compute_handoff_run_id` via `apply_handoffs`/`reenqueue_same`.
    """
    parent_or_source = parent_run["run_id"] if parent_run is not None else source_event_id
    if parent_or_source is None:
        raise ValueError("enqueue needs parent_run or source_event_id (causal identity)")
    run_id = compute_run_id(parent_or_source, enqueue_index, task_id, attempt)

    def fn(txn: Txn) -> None:
        _put_queued_run(
            txn, run_id, ticket_id=ticket_id, task_id=task_id, task_version=task_version,
            bindings=bindings, attempt=attempt, chain_depth=chain_depth,
            parent_run_id=parent_run["run_id"] if parent_run is not None else None,
            source_event_id=source_event_id, enqueue_index=enqueue_index,
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
            r["state"] in EXCLUSIVE_STATES and r["run_id"] != run_id
            for r in doc.get("runs", [])
        )

    if not parallel_ok and has_exclusive(state_docs.get(ticket_id, {})):
        return False

    other_active = sum(
        1 for tid, doc in state_docs.items()
        if tid != ticket_id
        and any(r["state"] in EXCLUSIVE_STATES for r in doc.get("runs", []))
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


def check_loop_guard(
    state_doc: dict, max_runs: int = 25, max_depth: int = 12
) -> tuple[bool, list[dict] | None]:
    """True (ok, None) unless the ticket has too many runs or too deep a
    causal chain, in which case (False, trace) with trace being every run's
    run_id/task_id/parent_run_id for the BLOCKED reason."""
    runs = state_doc.get("runs", [])
    max_chain_depth = max((r.get("chain_depth", 0) for r in runs), default=0)
    # Guard runs BEFORE an enqueue, so `<` makes max_runs the true ceiling.
    if len(runs) < max_runs and max_chain_depth < max_depth:
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


def resolve_target_repo(config: Config, details) -> str | None:
    """Match a repos.yml product_area against the ticket's labels/title/body.
    Returns None when nothing matches (intake treats that as ineligible;
    prepare/collect fall back to the first repo)."""
    haystack = " ".join([details.title, details.body, *details.labels]).lower()
    for repo, meta in config.repos.items():
        if meta["product_area"].lower() in haystack:
            return repo
    return None


def subst(template: str, ticket_id: str) -> str:
    return template.replace("{ticket}", ticket_id)


def set_gate_label(config, adapter_fn, ticket_id: str, waiting: bool) -> None:
    """Flag/unflag the ticket issue as blocked on a human gate, so the tickets
    a human is holding up are findable by label instead of by reading the
    state branch. Idempotent -- the tracker no-ops when the label set already
    matches.

    Reads the issue's current labels and re-sends them: `set_status_labels`
    replaces the WHOLE `hq:`-prefixed set, so anything else the issue carries
    (`hq:intake`) has to be passed back through or it gets stripped."""
    tracker = adapter_fn("tracker", config.components["tracker"]["adapter"], repo=intake_repo(config))
    keep = [name for name in tracker.fetch_ticket(ticket_id).labels if name != GATE_LABEL]
    tracker.set_status_labels(
        ticket_id,
        "WAITING_GATE" if waiting else "ACTIVE",
        keep + ([GATE_LABEL] if waiting else []),
    )


def notify_ticket(config, adapter_fn, ticket_id, message: str, event_id: str, mentions=None) -> None:
    """Post one plain comment to the ticket thread, idempotent by `event_id`
    (the messaging adapter dedupes on its `<!--hq:evt:...-->` marker). The
    single primitive for engine-authored ticket-thread comments -- escalation
    and the review-park findings notice both go through here."""
    messaging = adapter_fn(
        "messaging", config.components["messaging"]["adapter"], repo=intake_repo(config)
    )
    messaging.notify(
        {"ticket_id": ticket_id, "mentions": mentions or []}, message, [], event_id
    )


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


def _block_ticket(store, ticket_id, run_id, reason: str) -> None:
    def fn(txn: Txn) -> None:
        txn.set_ticket(ticket_id, status="BLOCKED")
        txn.append_event(
            ticket_id,
            Event(
                event_id=f"{run_id}:blocked",
                kind="ticket.blocked",
                ticket_id=ticket_id,
                run_id=run_id,
                detail=reason,
            ).to_dict(),
        )

    store.write(fn)


def reenqueue_same(store, run: dict, taskdef: dict, attempt: int) -> str:
    """Re-enqueue the same task at a new attempt.

    A handoff-spawned run (has `handoff_key`) retries via
    `compute_handoff_run_id`, preserving `handoff_key`/`repo`/
    `input_artifacts` -- a retry must run against the same repo with the
    same inputs. Anything else (the intake root run) retries via the
    original causal (`source_event_id`/`enqueue_index`) identity.
    """
    if run.get("handoff_key"):
        run_id = compute_handoff_run_id(run["parent_run_id"], run["handoff_key"], attempt)
        store.write(
            lambda txn: _put_queued_run(
                txn, run_id, ticket_id=run["ticket_id"], task_id=run["task_id"],
                task_version=taskdef["version"], bindings=run.get("bindings", {}),
                attempt=attempt, chain_depth=run["chain_depth"],
                parent_run_id=run.get("parent_run_id"), handoff_key=run["handoff_key"],
                repo=run.get("repo"), input_artifacts=list(run.get("input_artifacts") or []),
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
    )


def apply_handoffs(
    txn: Txn, config: Config, taskdefs: dict, ticket_id: str, source_run: dict,
    accepted: list[Handoff], attempt: int = 0,
) -> tuple[list[str], str | None]:
    """Enforce the state-dependent guards the pure validator
    (`engine.handoff.validate_handoffs`) can't see -- each artifact's ledger
    entry actually exists, and loop/budget/depth still hold -- then append
    `accepted` as QUEUED runs in emitted order, idempotent by derived id
    (`compute_handoff_run_id`). Any guard failure rejects the WHOLE set
    (nothing is appended), the same all-or-nothing contract as
    `validate_handoffs`. Must run inside the caller's own `store.write`
    transaction alongside the source run's own terminal-state update, so a
    crash between "succeeded" and "children queued" cannot happen.
    """
    for h in accepted:
        for rel_path in h.artifacts or []:
            if not txn.has_artifact(ticket_id, source_run["run_id"], rel_path):
                return [], f"artifact '{rel_path}' missing from {source_run['run_id']}'s ledger"

    ticket_doc = txn.ticket_doc(ticket_id)
    loop_cfg = config.budgets["loop_guard"]
    # Prospective: account for the WHOLE batch about to be inserted (not just
    # the current, pre-insertion state) -- a two-handoff batch checked only
    # once against the current run count could otherwise land both runs even
    # though the second one pushes the ticket past max_runs. Same for depth:
    # every accepted handoff in this batch lands at the SAME child depth
    # (source_run's chain_depth + 1), which the current runs' own recorded
    # depths don't yet reflect.
    existing_runs = ticket_doc.get("runs", [])
    existing_max_depth = max((r.get("chain_depth", 0) for r in existing_runs), default=0)
    projected_runs = len(existing_runs) + len(accepted)
    projected_depth = max(existing_max_depth, source_run["chain_depth"] + 1)
    if projected_runs > loop_cfg["max_runs"] or projected_depth > loop_cfg["max_depth"]:
        return [], "loop guard would trip applying this handoff set"
    for h in accepted:
        budget = taskdefs[h.target_task]["budget"]
        verdict = check_budget(ticket_doc, budget, config.budgets["ticket_cap_usd"])
        if verdict["over_ticket_cap"] or verdict["insufficient_headroom"]:
            return [], f"ticket budget exhausted for handoff target '{h.target_task}'"

    applied: list[str] = []
    for h in accepted:
        target = taskdefs[h.target_task]
        run_id = compute_handoff_run_id(source_run["run_id"], h.key, attempt)
        _put_queued_run(
            txn, run_id, ticket_id=ticket_id, task_id=target["id"], task_version=target["version"],
            bindings=source_run.get("bindings", {}), attempt=attempt,
            chain_depth=source_run["chain_depth"] + 1, parent_run_id=source_run["run_id"],
            handoff_key=h.key, repo=h.repo or source_run.get("repo"),
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
    """
    run_id = run["run_id"]
    if block_on_unknown_usage and run.get("usage_known") is False:
        _block_ticket(store, ticket_id, run_id, "attempt failed with unknown spend")
        _escalate(
            store, config, adapter_fn, ticket_id, run_id,
            "Run failed with unknown spend; blocked pending human review.",
        )
        return
    if run["attempt"] < taskdef["budget"]["retries"]:
        reenqueue_same(store, run, taskdef, run["attempt"] + 1)
        return
    _block_ticket(store, ticket_id, run_id, "retries exhausted")


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
            store, config, taskdefs, taskdef, ticket_id, failed, adapter_fn,
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
        else:
            timeout = gate_entry.get("timeout_working_hours")
            repo = (
                run.get("repo") or _target_repo(config, adapter_fn, ticket_id)
                or next(iter(config.repos))
            )
            gate = adapter_fn("gate", run.get("bindings", {}).get("gate", "pr-review"), repo=repo)
            decision = gate.status(
                {**run, "timeout_working_hours": timeout,
                 "approver_group": gate_entry.get("approvers")}
            )
        status = decision.status.value if hasattr(decision.status, "value") else decision.status

        if status != "PENDING":
            # Cleared on "a decision exists", before the branches below --
            # several of them return early, and the label means "a human is
            # holding this up", which stopped being true the moment the
            # decision landed.
            set_gate_label(config, adapter_fn, ticket_id, waiting=False)

        if status == "APPROVED":
            pending = [Handoff.from_dict(h) for h in (run.get("pending_handoffs") or [])]
            result: dict = {}

            def approve(txn: Txn) -> None:
                applied_ids, apply_reason = apply_handoffs(
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
                        event_id=f"{run_id}:succeeded", kind="run.succeeded", ticket_id=ticket_id,
                        run_id=run_id, state=RunState.SUCCEEDED,
                    ).to_dict(),
                )
                if decision.comment_id is not None:
                    txn.append_event(
                        ticket_id,
                        Event(
                            event_id=f"{decision.comment_id}:approval", kind="gate.decided",
                            ticket_id=ticket_id, run_id=run_id,
                            detail=f"approved by {decision.actor} at {decision.decided_at}",
                        ).to_dict(),
                    )
                elif gate_entry.get("auto_approve"):
                    txn.append_event(
                        ticket_id,
                        Event(
                            event_id=f"{run_id}:auto_approval", kind="gate.decided",
                            ticket_id=ticket_id, run_id=run_id, detail=decision.comments,
                        ).to_dict(),
                    )

            store.write(approve)
            if result["apply_reason"] is not None:
                _mark_gate_terminal(store, ticket_id, run, "run.failed", "handoff_apply_failed")
                _block_ticket(store, ticket_id, run_id, result["apply_reason"])
                return
            _complete_if_queue_empty(store, config, adapter_fn, ticket_id, {**run, "state": "SUCCEEDED"})
        elif status == "CHANGES_REQUESTED":
            if run["attempt"] >= 2:
                _mark_gate_terminal(store, ticket_id, run, "run.rework", "rework_final")
                _block_ticket(store, ticket_id, run_id, "max rework cycles reached")
                return
            _mark_gate_terminal(store, ticket_id, run, "run.changes_requested", "changes_requested")
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
                    ).to_dict(),
                )
            )
        elif status == "REJECTED":
            _mark_gate_terminal(store, ticket_id, run, "run.rejected", "rejected")
            _block_ticket(store, ticket_id, run_id, decision.comments or "gate rejected")
        elif status == "EXPIRED":
            _mark_gate_terminal(store, ticket_id, run, "run.gate_expired", "gate_expired")
            _block_ticket(store, ticket_id, run_id, "gate timed out")
            _escalate(
                store, config, adapter_fn, ticket_id, run_id,
                "Review gate expired without a decision; blocked pending escalation.",
            )
        # PENDING: leave the run WAITING_GATE.

    for ticket_id in (ticket_ids if ticket_ids is not None else store.list_tickets()):
        state = store.read_state(ticket_id)
        if state is None:
            continue
        for run in list(state.get("runs", [])):
            taskdef = taskdefs.get(run["task_id"])
            if taskdef is None:
                continue
            if run["state"] == "RUNNING":
                handle_running(taskdef, ticket_id, run)
            elif run["state"] == "WAITING_GATE":
                handle_gate(taskdef, ticket_id, run)


def _mark_gate_terminal(store, ticket_id, run: dict, kind: str, event_suffix: str) -> None:
    """Terminalize a WAITING_GATE run FAILED, clearing any `pending_handoffs`
    and emitting `handoff.rejected` (each carrying that handoff's own
    `reason`) for every one of them, all in the SAME write -- else
    completion's "no pending handoffs" check never passes."""
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
    handoffs anywhere on the ticket: DONE only if the TERMINAL run's own
    recorded artifacts include the declared closing summary (so a reopened
    ticket can't complete off a prior lifecycle's stale summary) -- read
    that ledger copy, post the closing summary, mark every recorded work PR
    ready, close the issue, and mark the ticket DONE; else pin "awaiting
    human input". ponytail: idempotency keyed off `status == "ACTIVE"` (once
    DONE this never re-fires) plus the tracker methods' own event-marker
    dedup on the closing side effects, rather than a separate
    `{ticket}:{run}:done` record.
    """
    state = store.read_state(ticket_id)
    if state is None or state.get("status") != "ACTIVE":
        return
    runs = state.get("runs", [])
    if any(r["state"] in NON_TERMINAL for r in runs):
        return
    if any(r.get("pending_handoffs") for r in runs):
        return

    tracker = adapter_fn("tracker", config.components["tracker"]["adapter"], repo=intake_repo(config))
    summary_path = subst("specs/{ticket}/summary.md", ticket_id)
    done_key = f"{ticket_id}:{terminal_run['run_id']}:done"
    if summary_path not in (terminal_run.get("artifacts") or []):
        # A terminal run that parks with a review.md (the review-park
        # endpoint: rounds exhausted, no handoff) surfaces its accumulated
        # findings to the thread before pinning awaiting-human -- the PR is
        # deliberately left in draft. review.md is a filename convention,
        # same as summary.md above; the engine special-cases no task name.
        review_path = subst("specs/{ticket}/review.md", ticket_id)
        if review_path in (terminal_run.get("artifacts") or []):
            findings = store.read_artifact(ticket_id, terminal_run["run_id"], review_path) or ""
            notify_ticket(
                config, adapter_fn, ticket_id,
                "Review rounds exhausted with unresolved findings; the PR is left in "
                "draft for human review.\n\n" + findings,
                f"{done_key}:review-findings",
            )
        tracker.upsert_pinned_comment(
            ticket_id, "Queue is empty; awaiting human input.", f"{done_key}:awaiting"
        )
        return

    summary = store.read_artifact(ticket_id, terminal_run["run_id"], summary_path) or ""
    tracker.post_closing_summary(ticket_id, summary, f"{done_key}:closing-summary")
    for work_repo in state.get("work_repos", []):
        if work_repo.get("pr_ref"):
            agent = adapter_fn(
                "agent-session", config.components["agent-session"]["adapter"],
                repo=work_repo["repo"],
            )
            agent.mark_pr_ready(work_repo["pr_ref"])
    tracker.close_issue(ticket_id)
    store.write(lambda txn: txn.set_ticket(ticket_id, status="DONE"))


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
    """TE-3: a task declaring input artifacts may only start once its parent
    run has recorded (a superset of) those artifacts. State-level check --
    artifacts are recorded on the parent's collect, so no git access needed."""
    declared = taskdef.get("inputs", {}).get("artifacts", [])
    if not declared or not run.get("parent_run_id"):
        return True
    parent = next((r for r in state["runs"] if r["run_id"] == run["parent_run_id"]), None)
    if parent is None:
        return False
    produced = set(parent.get("artifacts", []))
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
        for run in state.get("runs", []):
            if run["state"] != "QUEUED":
                continue
            taskdef = taskdefs.get(run["task_id"])
            if taskdef is None:
                continue
            run_id = run["run_id"]

            # Current-state check, not the prospective (pre-insertion) one
            # `check_loop_guard` implements: this run was already accepted
            # onto the ticket (possibly exactly AT max_runs/max_depth), so
            # only reject dispatch if the ticket is ALREADY beyond the
            # configured limit -- reusing the enqueue-time "<" ceiling here
            # would block a legitimately-queued boundary run before it ever
            # executes.
            runs = state.get("runs", [])
            max_chain_depth = max((r.get("chain_depth", 0) for r in runs), default=0)
            if (
                len(runs) > budgets["loop_guard"]["max_runs"]
                or max_chain_depth > budgets["loop_guard"]["max_depth"]
            ):
                _block_ticket(store, ticket_id, run_id, "loop guard tripped")
                break

            verdict = check_budget(state, taskdef["budget"], budgets["ticket_cap_usd"])
            if verdict["over_ticket_cap"] or verdict["insufficient_headroom"]:
                _block_ticket(store, ticket_id, run_id, "ticket budget exhausted")
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
