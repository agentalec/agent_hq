"""Engine core: causal enqueue and the concurrency/loop/budget/kill guards
(§5.2).

Guard functions are pure (state docs / config in, verdict out) so dispatch
logic (Task 13) can compose them without re-reading the state store.
"""

from __future__ import annotations

import os

from engine.models import Event, RunState, TaskRun, compute_run_id
from engine.state import GitJsonStateStore, Txn

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
