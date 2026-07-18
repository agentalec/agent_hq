"""Engine core: causal enqueue and the concurrency/loop/budget/kill guards
(§5.2).

Guard functions are pure (state docs / config in, verdict out) so dispatch
logic (Task 13) can compose them without re-reading the state store.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from engine.config import Config
from engine.models import Event, RunState, TaskRun, compute_run_id
from engine.predicates import PredicateError, evaluate
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

# In-flight (pipeline-occupying) states, used for the global ticket cap.
ACTIVE_STATES = {"QUEUED", "RUNNING", "WAITING_GATE"}
# States that make a ticket exclusive for dispatch: a QUEUED sibling merely
# waits its turn and must not block dispatching the run under evaluation.
EXCLUSIVE_STATES = {"RUNNING", "WAITING_GATE"}


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
    run record.
    """
    parent_or_source = parent_run["run_id"] if parent_run is not None else source_event_id
    if parent_or_source is None:
        raise ValueError("enqueue needs parent_run or source_event_id (causal identity)")
    run_id = compute_run_id(parent_or_source, enqueue_index, task_id, attempt)

    def fn(txn: Txn) -> None:
        if txn.get_run(ticket_id, run_id) is not None:
            return
        run = TaskRun(
            run_id=run_id,
            task_id=task_id,
            task_version=task_version,
            ticket_id=ticket_id,
            state=RunState.QUEUED,
            attempt=attempt,
            bindings=bindings,
            cost_usd=None,
            tokens=None,
            usage_known=False,
            artifacts=[],
            chain_depth=chain_depth,
            parent_run_id=parent_run["run_id"] if parent_run is not None else None,
            source_event_id=source_event_id,
            enqueue_index=enqueue_index,
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

    store.write(fn)
    return run_id


def check_concurrency(
    state_docs: dict[str, dict],
    ticket_id: str,
    run_id: str | None = None,
    parallel_ok: bool = False,
    in_flight_cap: int = 3,
) -> bool:
    """True if the run `run_id` (or a hypothetical new run) may start on
    `ticket_id`.

    Refused when the ticket has another run in an EXCLUSIVE state
    (RUNNING/WAITING_GATE — a QUEUED sibling just waits, and the run under
    evaluation never blocks itself), unless parallel_ok; or when the number
    of OTHER tickets with any in-flight run has already reached the global
    cap (the run's own ticket occupies one slot by definition).
    """

    def has_exclusive(doc: dict) -> bool:
        return any(
            r["state"] in EXCLUSIVE_STATES and r["run_id"] != run_id
            for r in doc.get("runs", [])
        )

    def has_active(doc: dict) -> bool:
        return any(r["state"] in ACTIVE_STATES for r in doc.get("runs", []))

    if not parallel_ok and has_exclusive(state_docs.get(ticket_id, {})):
        return False

    other_active = sum(
        1 for tid, doc in state_docs.items() if tid != ticket_id and has_active(doc)
    )
    return other_active < in_flight_cap


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
    """Assemble a port's settings from components.yml (+ approvers for gate,
    + the resolved repo) and construct the adapter via the registry."""
    comp = config.components.get(port, {}) if isinstance(config.components, dict) else {}
    settings = dict(comp.get("settings", {}))
    if repo:
        settings["repo"] = repo
    if port == "gate":
        settings["approvers"] = config.approvers
    return build_adapter(port, adapter_name, settings)


def _default_adapter_fn(config: Config) -> AdapterFn:
    def fn(port: str, adapter_name: str, repo: str | None = None):
        return build_port_adapter(config, port, adapter_name, repo)

    return fn


def intake_repo(config: Config) -> str | None:
    """The repo whose issue tracker intake reads/writes. Pilot assumption: the
    first configured project repo. ponytail: single intake repo for the pilot;
    per-repo routing lands with multi-tenant intake."""
    repos = config.projects.get("repos") or list(config.repos)
    return repos[0] if repos else None


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


def _escalate(store, config, adapter_fn, ticket_id, run_id, message: str) -> None:
    messaging = adapter_fn(
        "messaging", config.components["messaging"]["adapter"], repo=intake_repo(config)
    )
    members = config.approvers.get("groups", {}).get("escalation", {}).get("members", [])
    messaging.notify(
        {"ticket_id": ticket_id, "mentions": members},
        message,
        [],
        f"{run_id}:escalation",
    )


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
    """Re-enqueue the same task at a new attempt, preserving causal linkage
    (parent_run_id / source_event_id / enqueue_index) so the retry chains off
    the same base as the original run."""
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


def enqueue_targets(
    store, taskdefs, run: dict, taskdef: dict, phase: str, values: dict, chain_depth: int
) -> bool:
    """Enqueue a task's on_success/on_failure targets (predicate-filtered),
    each attempt 0, parent=this run. Returns whether anything was enqueued."""
    items = taskdef.get(phase, {}).get("enqueue", [])
    parent = {"run_id": run["run_id"]}
    enqueued = False
    for index, item in enumerate(items):
        pred = item.get("when")
        if pred and not evaluate(pred, values):
            continue
        target = taskdefs[item["task"]]
        enqueue(
            store,
            ticket_id=run["ticket_id"],
            parent_run=parent,
            enqueue_index=index,
            task_id=target["id"],
            task_version=target["version"],
            attempt=0,
            bindings=run.get("bindings", {}),
            chain_depth=chain_depth,
        )
        enqueued = True
    return enqueued


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
    values = dict(run)
    if not enqueue_targets(
        store, taskdefs, run, taskdef, "on_failure", values, run["chain_depth"] + 1
    ):
        _block_ticket(store, ticket_id, run_id, "retries exhausted, no on_failure path")


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


def sweep(config, taskdefs, store, workflow_api, now_iso: str, adapter_fn: AdapterFn) -> None:
    """Reconcile every ticket's in-flight runs: fail lost/timed-out RUNNING
    runs (then retry per policy) and resolve WAITING_GATE runs against the gate
    adapter. Runs before the trigger stage so freed capacity is visible."""

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
        timeout = gate_entry.get("timeout_working_hours")
        repo = _target_repo(config, adapter_fn, ticket_id) or next(iter(config.repos))
        gate = adapter_fn("gate", run.get("bindings", {}).get("gate", "pr-review"), repo=repo)
        decision = gate.status({**run, "timeout_working_hours": timeout})
        status = decision.status.value if hasattr(decision.status, "value") else decision.status
        if status == "APPROVED":
            # Enqueue BEFORE marking SUCCEEDED: both are idempotent, and a
            # crash after enqueue merely re-marks next sweep, while a crash
            # after mark-first would orphan the chain forever (nothing ever
            # re-drives a childless SUCCEEDED run).
            enqueue_targets(
                store, taskdefs, run, taskdef, "on_success", dict(run), run["chain_depth"] + 1
            )
            _mark_succeeded(store, ticket_id, run_id)
        elif status in ("CHANGES_REQUESTED", "REJECTED"):
            if run["attempt"] >= 2:
                _mark_failed(store, ticket_id, run_id, "run.rework", "rework_final")
                _block_ticket(store, ticket_id, run_id, "max rework cycles reached")
                return
            _mark_failed(store, ticket_id, run_id, "run.changes_requested", "changes_requested")
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
        elif status == "EXPIRED":
            _mark_failed(store, ticket_id, run_id, "run.gate_expired", "gate_expired")
            _block_ticket(store, ticket_id, run_id, "gate timed out")
            _escalate(
                store, config, adapter_fn, ticket_id, run_id,
                "Review gate expired without a decision; blocked pending escalation.",
            )
        # PENDING: leave the run WAITING_GATE.

    def redrive_succeeded(taskdef, ticket_id, state, run) -> None:
        """Self-heal a crash between success and downstream enqueue: a
        SUCCEEDED run with declared on_success targets but no child runs gets
        its (idempotent) enqueue re-driven, so an orphaned chain converges on
        the next sweep instead of stalling forever."""
        if not taskdef.get("on_success", {}).get("enqueue"):
            return
        has_child = any(
            r.get("parent_run_id") == run["run_id"] for r in state.get("runs", [])
        )
        if has_child:
            return
        try:
            enqueue_targets(
                store, taskdefs, run, taskdef, "on_success", dict(run), run["chain_depth"] + 1
            )
        except PredicateError:
            _block_ticket(
                store, ticket_id, run["run_id"],
                "cannot re-evaluate enqueue predicates after a crash; re-enqueue manually",
            )

    for ticket_id in store.list_tickets():
        state = store.read_state(ticket_id)
        for run in list(state.get("runs", [])):
            taskdef = taskdefs.get(run["task_id"])
            if taskdef is None:
                continue
            if run["state"] == "RUNNING":
                handle_running(taskdef, ticket_id, run)
            elif run["state"] == "WAITING_GATE":
                handle_gate(taskdef, ticket_id, run)
            elif run["state"] == "SUCCEEDED":
                redrive_succeeded(taskdef, ticket_id, state, run)


def _mark_succeeded(store, ticket_id, run_id) -> None:
    def fn(txn: Txn) -> None:
        txn.update_run(ticket_id, run_id, state="SUCCEEDED")
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

    store.write(fn)


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
) -> list[str]:
    """Two stages: sweep in-flight runs first, then trigger eligible QUEUED
    runs. Returns the run ids triggered this pass."""
    now_iso = now_iso or _now_iso()
    adapter_fn = adapter_fn or _default_adapter_fn(config)

    sweep(config, taskdefs, store, workflow_api, now_iso, adapter_fn)

    triggered: list[str] = []
    if kill_switch_active():
        return triggered

    budgets = config.budgets
    ticket_ids = store.list_tickets()
    all_states = {tid: store.read_state(tid) for tid in ticket_ids}
    for ticket_id in ticket_ids:
        state = all_states[ticket_id]
        if state.get("status") == "BLOCKED":
            continue
        for run in state.get("runs", []):
            if run["state"] != "QUEUED":
                continue
            taskdef = taskdefs.get(run["task_id"])
            if taskdef is None:
                continue
            run_id = run["run_id"]

            ok, _trace = check_loop_guard(
                state, budgets["loop_guard"]["max_runs"], budgets["loop_guard"]["max_depth"]
            )
            if not ok:
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
