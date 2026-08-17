from pathlib import Path

from test_state import _clone_worktree, _make_origin

from engine.config import Config
from engine.engine import (
    STATUS_LABELS,
    _handle_failure,
    _inputs_ready,
    apply_queue,
    check_budget,
    check_concurrency,
    check_loop_guard,
    dispatch,
    enqueue,
    intake_repo,
    kill_switch_active,
    queue_positions,
    reenqueue_same,
    resolve_input_source,
    resolve_target_repo,
    set_status_label,
)
from engine.models import Handoff, TicketDetails
from engine.state import GitJsonStateStore


def _store(tmp_path: Path) -> tuple[GitJsonStateStore, Path]:
    origin = _make_origin(tmp_path)
    worktree = _clone_worktree(tmp_path, origin, "wt")
    return GitJsonStateStore(worktree), worktree


def _noop_adapters():
    """Minimal adapter_fn covering the post-write side effects a block path
    makes: the status label (tracker) and the escalation comment (messaging)."""
    class _Tracker:
        def fetch_ticket(self, ticket_id):
            return TicketDetails(ticket_id=ticket_id, title="t", body="b", labels=[])

        def set_status_labels(self, ticket_id, status, labels):
            pass

    class _Messaging:
        def notify(self, target, message, attachments, event_id):
            pass

    return lambda port, adapter, **kw: _Tracker() if port == "tracker" else _Messaging()


def test_enqueue_is_idempotent(tmp_path):
    store, worktree = _store(tmp_path)
    kwargs = {
        "ticket_id": "ticket-1",
        "source_event_id": "evt-1",
        "task_id": "task-1",
        "task_version": 1,
        "bindings": {},
        "chain_depth": 0,
    }

    run_id_1 = enqueue(store, **kwargs)
    run_id_2 = enqueue(store, **kwargs)

    assert run_id_1 == run_id_2

    state = store.read_state("ticket-1")
    assert len(state["runs"]) == 1
    assert state["runs"][0]["run_id"] == run_id_1
    assert state["runs"][0]["state"] == "QUEUED"

    lines = (worktree / "tickets" / "ticket-1" / "events.jsonl").read_text().splitlines()
    assert len(lines) == 1


def test_enqueue_attempt_increment_yields_distinct_run_id(tmp_path):
    store, _ = _store(tmp_path)
    kwargs = {
        "ticket_id": "ticket-1",
        "source_event_id": "evt-1",
        "task_id": "task-1",
        "task_version": 1,
        "bindings": {},
        "chain_depth": 0,
    }

    run_id_0 = enqueue(store, attempt=0, **kwargs)
    run_id_1 = enqueue(store, attempt=1, **kwargs)

    assert run_id_0 != run_id_1
    assert len(store.read_state("ticket-1")["runs"]) == 2


def test_enqueue_from_parent_run_records_causal_fields(tmp_path):
    store, _ = _store(tmp_path)
    parent = {"run_id": "parent-run"}

    run_id = enqueue(
        store,
        ticket_id="ticket-1",
        parent_run=parent,
        enqueue_index=1,
        task_id="task-2",
        task_version=1,
        bindings={"llm": "claude"},
        chain_depth=1,
    )

    run = store.read_state("ticket-1")["runs"][0]
    assert run["run_id"] == run_id
    assert run["parent_run_id"] == "parent-run"
    assert run["chain_depth"] == 1


def _doc(runs: list[dict]) -> dict:
    return {"runs": runs}


def _run(run_id: str, state: str = "RUNNING") -> dict:
    return {"run_id": run_id, "task_id": "t", "state": state, "chain_depth": 0}


def test_check_concurrency_refuses_second_active_run_same_ticket():
    docs = {"ticket-1": _doc([_run("r1", "RUNNING")])}
    assert check_concurrency(docs, "ticket-1") is False


def test_check_concurrency_parallel_ok_allows_second_active_run():
    docs = {"ticket-1": _doc([_run("r1", "RUNNING")])}
    assert check_concurrency(docs, "ticket-1", parallel_ok=True) is True


def test_check_concurrency_in_flight_cap_across_tickets():
    docs = {
        "ticket-1": _doc([_run("r1", "RUNNING")]),
        "ticket-2": _doc([_run("r2", "RUNNING")]),
    }
    assert check_concurrency(docs, "ticket-3", in_flight_cap=2) is False
    assert check_concurrency(docs, "ticket-3", in_flight_cap=3) is True


def test_check_concurrency_cap_ignores_queued_only_tickets():
    """Regression: QUEUED-only tickets must not count towards the cross-ticket
    cap (mirroring claim_run) — else cap+1 tickets intaken while the pipeline
    is busy all sit QUEUED and every unscoped cron pass skips every ticket,
    starving dispatch forever."""
    docs = {
        "ticket-1": _doc([_run("r1", "QUEUED")]),
        "ticket-2": _doc([_run("r2", "QUEUED")]),
        "ticket-3": _doc([_run("r3", "QUEUED")]),
        "ticket-4": _doc([_run("r4", "QUEUED")]),
    }
    for tid, run_id in (("ticket-1", "r1"), ("ticket-4", "r4")):
        assert check_concurrency(docs, tid, run_id=run_id, in_flight_cap=3) is True
    # RUNNING tickets do count.
    docs["ticket-1"]["runs"][0]["state"] = "RUNNING"
    docs["ticket-2"]["runs"][0]["state"] = "RUNNING"
    docs["ticket-3"]["runs"][0]["state"] = "RUNNING"
    assert check_concurrency(docs, "ticket-4", run_id="r4", in_flight_cap=3) is False


def test_check_loop_guard_within_limits_ok():
    ok, trace = check_loop_guard(_doc([_run("r1", "SUCCEEDED")]), max_runs=25)
    assert ok is True
    assert trace is None


def test_check_loop_guard_max_runs_breach_returns_trace():
    runs = [
        {"run_id": f"r{i}", "task_id": "t", "parent_run_id": None, "chain_depth": 0}
        for i in range(3)
    ]
    ok, trace = check_loop_guard(_doc(runs), max_runs=2)
    assert ok is False
    assert len(trace) == 3
    assert trace[0] == {"run_id": "r0", "task_id": "t", "parent_run_id": None}


def test_deep_chain_alone_no_longer_trips_the_loop_guard():
    """`max_depth` is gone. Depth is provenance now, not a ceiling: with a
    pre-declared queue every entry sits at the declaring run's depth + 1, so
    depth stopped measuring anything a runaway could exhaust. `max_runs` is the
    ceiling, and one deep run is still one run."""
    doc = _doc([{"run_id": "r1", "task_id": "t", "parent_run_id": "r0", "chain_depth": 99}])
    ok, trace = check_loop_guard(doc, max_runs=25)
    assert ok is True
    assert trace is None


def test_apply_queue_rejects_batch_that_would_exceed_max_runs(tmp_path):
    """Regression: capacity must be checked against the WHOLE accepted batch
    (`len(runs) + len(accepted)`), not just the pre-insertion run count --
    else a two-handoff batch can land both runs even past max_runs."""
    store, _ = _store(tmp_path)
    config = Config(
        components={}, repos={}, projects={}, approvers={},
        budgets={"loop_guard": {"max_runs": 2}, "ticket_cap_usd": 1000.0},
    )
    taskdefs = {
        "task-a": {"id": "task-a", "version": 1, "budget": {"max_cost_usd": 100.0}},
        "task-b": {"id": "task-b", "version": 1, "budget": {"max_cost_usd": 100.0}},
    }
    source_run = {
        "run_id": "src", "task_id": "task-0", "ticket_id": "ticket-1", "chain_depth": 0,
        "bindings": {}, "state": "RUNNING", "task_version": 1, "attempt": 0, "cost_usd": None,
        "tokens": None, "usage_known": False, "artifacts": [],
    }
    store.write(lambda txn: (
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None),
        txn.put_run("ticket-1", source_run),
    ))
    accepted = [
        Handoff(key="a", target_task="task-a", reason="r"),
        Handoff(key="b", target_task="task-b", reason="r"),
    ]

    result = {}

    def try_apply(txn):
        applied, reason = apply_queue(txn, config, taskdefs, "ticket-1", source_run, accepted)
        result["applied"], result["reason"] = applied, reason

    store.write(try_apply)
    assert result["applied"] == []
    assert "loop guard" in result["reason"]

    # One more run of headroom (max_runs=3: existing 1 + batch of 2 = 3) fits.
    config.budgets["loop_guard"]["max_runs"] = 3
    store.write(try_apply)
    assert result["reason"] is None
    assert len(result["applied"]) == 2


def test_engine_side_block_records_its_reason_in_state(tmp_path):
    """Regression: `_block_ticket` used to set only `status="BLOCKED"` and drop
    the `reason` it was handed, so every engine-side block (gate rejected /
    expired, retries exhausted, unknown spend, handoff-apply failure, PR
    feedback over budget) left `block_reason` null and the dashboard rendered
    "BLOCKED" with no reason. Driven here through `_handle_failure`'s
    retries-exhausted branch."""
    store, _ = _store(tmp_path)
    config = Config(
        components={"tracker": {"adapter": "fake"}, "messaging": {"adapter": "fake"}},
        repos={}, projects={"engine_repo": "o/engine"},
        approvers={"groups": {"escalation": {"members": ["example-carol"]}}},
        budgets={"loop_guard": {"max_runs": 25}, "ticket_cap_usd": 1000.0},
    )
    taskdef = {"id": "build", "version": 1, "budget": {"retries": 0, "max_cost_usd": 100.0}}
    run = {
        "run_id": "r1", "task_id": "build", "ticket_id": "ticket-1", "chain_depth": 0,
        "bindings": {}, "state": "FAILED", "task_version": 1, "attempt": 0,
        "cost_usd": 0.5, "tokens": 10, "usage_known": True, "artifacts": [],
    }
    store.write(lambda txn: (
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None),
        txn.put_run("ticket-1", run),
    ))

    _handle_failure(
        store, config, {"build": taskdef}, taskdef, "ticket-1", run,
        _noop_adapters(), block_on_unknown_usage=True,
    )

    state = store.read_state("ticket-1")
    assert state["status"] == "BLOCKED"
    assert state["block_reason"] == "retries exhausted"
    assert state["block_source"] == "engine"
    assert state["interrupted_run_id"] == "r1"


def test_dispatch_does_not_block_a_queued_run_exactly_at_max_runs(tmp_path):
    """Regression: dispatch must reject only a ticket ALREADY beyond the
    configured limit, not reuse the enqueue-time '<' ceiling against a run
    that was already legitimately queued at the boundary."""
    store, config, taskdefs = _dispatch_fixture(tmp_path)
    config.budgets["loop_guard"]["max_runs"] = 1  # ticket-1 already has exactly 1 run
    wf = _FakeWorkflowApi()

    triggered = dispatch(
        config, taskdefs, store, wf, now_iso="2026-07-18T00:00:00Z", issue="ticket-1"
    )

    assert triggered == ["run-ticket-1"]


def test_check_budget_sums_only_usage_known_runs():
    doc = _doc(
        [
            {"state": "SUCCEEDED", "usage_known": True, "cost_usd": 3.0},
            {"state": "SUCCEEDED", "usage_known": False, "cost_usd": None},
            {"state": "SUCCEEDED", "usage_known": True, "cost_usd": 4.0},
        ]
    )
    budget = {"max_cost_usd": 5, "max_runtime_min": 30, "retries": 2}

    verdict = check_budget(doc, budget, ticket_cap_usd=25)

    assert verdict["ticket_spend"] == 7.0
    assert verdict["over_ticket_cap"] is False
    assert verdict["unknown_usage_block"] is False


def test_check_budget_over_ticket_cap():
    doc = _doc([{"state": "SUCCEEDED", "usage_known": True, "cost_usd": 30.0}])
    budget = {"max_cost_usd": 5, "max_runtime_min": 30, "retries": 2}

    verdict = check_budget(doc, budget, ticket_cap_usd=25)

    assert verdict["over_ticket_cap"] is True


def test_check_budget_unknown_usage_failed_run_blocks():
    doc = _doc([{"state": "FAILED", "usage_known": False, "cost_usd": None}])
    budget = {"max_cost_usd": 5, "max_runtime_min": 30, "retries": 2}

    verdict = check_budget(doc, budget, ticket_cap_usd=25)

    assert verdict["unknown_usage_block"] is True


def test_kill_switch_env_toggle(monkeypatch):
    monkeypatch.delenv("AGENT_HQ_KILL_SWITCH", raising=False)
    assert kill_switch_active() is False

    monkeypatch.setenv("AGENT_HQ_KILL_SWITCH", "1")
    assert kill_switch_active() is True

    monkeypatch.setenv("AGENT_HQ_KILL_SWITCH", "0")
    assert kill_switch_active() is False


def test_check_concurrency_own_queued_run_does_not_block_itself():
    """Regression: a QUEUED run must be dispatchable — its own record (or a
    queued sibling) never counts as exclusivity; only RUNNING/WAITING_GATE do."""
    docs = {"ticket-1": _doc([_run("r1", "QUEUED")])}
    assert check_concurrency(docs, "ticket-1", run_id="r1") is True
    # a queued sibling also does not block
    docs["ticket-1"]["runs"].append(_run("r2", "QUEUED"))
    assert check_concurrency(docs, "ticket-1", run_id="r1") is True
    # but a RUNNING sibling does
    docs["ticket-1"]["runs"].append(_run("r3", "RUNNING"))
    assert check_concurrency(docs, "ticket-1", run_id="r1") is False


def test_check_budget_insufficient_headroom():
    doc = _doc([{"state": "SUCCEEDED", "usage_known": True, "cost_usd": 22.0}])
    verdict = check_budget(doc, {"max_cost_usd": 5.0}, ticket_cap_usd=25.0)
    assert verdict["insufficient_headroom"] is True
    assert verdict["over_ticket_cap"] is False
    verdict = check_budget(doc, {"max_cost_usd": 2.0}, ticket_cap_usd=25.0)
    assert verdict["insufficient_headroom"] is False


def test_predicate_in_with_scalar_value_raises():
    import pytest as _pytest

    from engine.predicates import PredicateError, evaluate

    with _pytest.raises(PredicateError):
        evaluate({"field": "a", "op": "in", "value": "beyond-crud"}, {"a": "beyond"})


def test_intake_repo_returns_engine_repo():
    config = Config(
        components={}, repos={}, projects={"engine_repo": "org/engine"}, approvers={}, budgets={},
    )
    assert intake_repo(config) == "org/engine"


def test_resolve_target_repo_still_returns_a_work_repo():
    config = Config(
        components={},
        repos={"org/product-be": {"product_area": "billing"}},
        projects={"engine_repo": "org/engine"},
        approvers={},
        budgets={},
    )
    details = TicketDetails(ticket_id="1", title="Billing bug", body="", labels=[])
    assert resolve_target_repo(config, details) == "org/product-be"


def test_resolve_target_repo_picks_backend_over_frontend_when_keyword_matches():
    """Pilot order: FE then BE. A ticket that only says 'backend' must not
    land on the FE repo; one that only says 'frontend' stays on FE."""
    config = Config(
        components={},
        repos={
            "agentalec/care_fe": {"product_area": "frontend"},
            "agentalec/care": {"product_area": "backend"},
        },
        projects={"engine_repo": "agentalec/agent_hq"},
        approvers={},
        budgets={},
    )
    be = TicketDetails(
        ticket_id="1", title="Fix Django serializer", body="backend API change", labels=[]
    )
    fe = TicketDetails(
        ticket_id="2", title="Button layout", body="frontend polish", labels=[]
    )
    assert resolve_target_repo(config, be) == "agentalec/care"
    assert resolve_target_repo(config, fe) == "agentalec/care_fe"


class _FakeWorkflowApi:
    def __init__(self):
        self.triggered: list[str] = []

    def active_workflow(self, run_name: str) -> bool:
        return False

    def trigger_run(self, run_id: str) -> None:
        self.triggered.append(run_id)


def _dispatch_fixture(tmp_path):
    store, _ = _store(tmp_path)
    config = Config(
        components={}, repos={}, projects={}, approvers={},
        budgets={
            "loop_guard": {"max_runs": 25},
            "ticket_cap_usd": 1000.0,
            "in_flight_cap": 3,
        },
    )
    taskdefs = {"task-1": {"budget": {"max_cost_usd": 100.0, "max_runtime_min": 30, "retries": 2}}}

    def setup(txn) -> None:
        for tid in ("ticket-1", "ticket-2"):
            txn.set_ticket(tid, status="ACTIVE", pinned_comment_id=None)
            txn.put_run(
                tid,
                {
                    "run_id": f"run-{tid}",
                    "task_id": "task-1",
                    "task_version": 1,
                    "ticket_id": tid,
                    "state": "QUEUED",
                    "attempt": 0,
                    "bindings": {},
                    "cost_usd": None,
                    "tokens": None,
                    "usage_known": False,
                    "artifacts": [],
                    "chain_depth": 0,
                },
            )

    store.write(setup)
    return store, config, taskdefs


def _queued_run(run_id, ticket_id="ticket-1", **over):
    run = {
        "run_id": run_id, "task_id": "task-1", "task_version": 1, "ticket_id": ticket_id,
        "state": "QUEUED", "attempt": 0, "bindings": {}, "cost_usd": None, "tokens": None,
        "usage_known": False, "artifacts": [], "chain_depth": 0,
    }
    run.update(over)
    return run


def test_queue_positions_falls_back_to_array_index_for_legacy_runs():
    """No state migration: a ticket written before `queue_seq` existed keeps
    exactly the order dispatch gave it, and new runs continue past the end."""
    runs = [_queued_run("old-a"), _queued_run("old-b"), _queued_run("new", queue_seq=7)]
    assert queue_positions(runs) == {"old-a": 0, "old-b": 1, "new": 7}


def test_batch_enqueued_in_one_write_gets_increasing_positions(tmp_path):
    """`_next_queue_seq` reads the in-transaction doc, so two runs inserted in
    the SAME write must not both land on the same position."""
    store, _ = _store(tmp_path)
    config = Config(
        components={}, repos={}, projects={}, approvers={},
        budgets={"loop_guard": {"max_runs": 25}, "ticket_cap_usd": 1000.0},
    )
    taskdefs = {
        "task-a": {"id": "task-a", "version": 1, "budget": {"max_cost_usd": 100.0}},
        "task-b": {"id": "task-b", "version": 1, "budget": {"max_cost_usd": 100.0}},
    }
    source = _queued_run("src", state="RUNNING", task_id="task-0")
    store.write(lambda txn: (
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None),
        txn.put_run("ticket-1", source),
    ))
    store.write(lambda txn: apply_queue(
        txn, config, taskdefs, "ticket-1", source,
        [Handoff(key="a", target_task="task-a", reason="r"),
         Handoff(key="b", target_task="task-b", reason="r")],
    ))

    runs = store.read_state("ticket-1")["runs"]
    positions = queue_positions(runs)
    # The source run predates queue_seq here (put_run directly), so it falls
    # back to index 0; the two handoffs must take distinct later positions.
    assert sorted(positions.values()) == [0, 1, 2]
    handoffs = [r for r in runs if r["run_id"] != "src"]
    assert sorted(r["queue_seq"] for r in handoffs) == [1, 2]


def test_retry_inherits_its_predecessor_queue_position(tmp_path):
    """A retry must resume the failed attempt's place in the queue. Appending
    it would let a run enqueued AFTER the failure jump ahead of the rework."""
    store, _ = _store(tmp_path)
    taskdef = {"id": "task-1", "version": 1, "budget": {"retries": 2, "max_cost_usd": 100.0}}
    failed = _queued_run(
        "r1", state="FAILED", queue_seq=0, parent_run_id="src", handoff_key="impl",
    )
    store.write(lambda txn: (
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None),
        txn.put_run("ticket-1", failed),
        # Enqueued after the failure, so it sits later in the queue.
        txn.put_run("ticket-1", _queued_run("later", queue_seq=1)),
    ))

    retry_id = reenqueue_same(store, failed, taskdef, attempt=1)

    runs = {r["run_id"]: r for r in store.read_state("ticket-1")["runs"]}
    assert runs[retry_id]["queue_seq"] == 0
    positions = queue_positions(list(runs.values()))
    assert positions[retry_id] < positions["later"]


def _cancel_fixture(tmp_path):
    store, _ = _store(tmp_path)
    config = Config(
        components={}, repos={}, projects={}, approvers={},
        budgets={"loop_guard": {"max_runs": 25}, "ticket_cap_usd": 1000.0},
    )
    taskdefs = {"task-a": {"id": "task-a", "version": 1, "budget": {"max_cost_usd": 100.0}}}
    source = _queued_run("src", state="RUNNING", task_id="task-0", queue_seq=0)
    store.write(lambda txn: (
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None),
        txn.put_run("ticket-1", source),
        txn.put_run("ticket-1", _queued_run("pending-a", queue_seq=1, handoff_key="qa")),
        txn.put_run("ticket-1", _queued_run("pending-b", queue_seq=2, handoff_key="docs")),
    ))
    return store, config, taskdefs, source


def _apply(store, config, taskdefs, source, accepted=(), **kw):
    result = {}

    def run(txn):
        applied, reason = apply_queue(
            txn, config, taskdefs, "ticket-1", source, list(accepted), **kw
        )
        result["applied"], result["reason"] = applied, reason

    store.write(run)
    return result


def test_omission_never_cancels_a_pending_entry(tmp_path):
    """The safety property: a run that declares its own entry and says nothing
    about a sibling must leave the sibling alone. Otherwise one branch of a
    fan-out silently drops the other by finishing first."""
    store, config, taskdefs, source = _cancel_fixture(tmp_path)

    result = _apply(
        store, config, taskdefs, source,
        [Handoff(key="mine", target_task="task-a", reason="r")],
    )

    assert result["reason"] is None
    states = {r["run_id"]: r["state"] for r in store.read_state("ticket-1")["runs"]}
    assert states["pending-a"] == "QUEUED"
    assert states["pending-b"] == "QUEUED"


def test_cancel_by_key_cancels_only_that_entry_and_records_it(tmp_path):
    store, config, taskdefs, source = _cancel_fixture(tmp_path)

    result = _apply(store, config, taskdefs, source, cancel_keys=["qa"])

    assert result["reason"] is None
    states = {r["run_id"]: r["state"] for r in store.read_state("ticket-1")["runs"]}
    assert states["pending-a"] == "CANCELLED"
    assert states["pending-b"] == "QUEUED"
    cancelled = [e for e in store.read_events("ticket-1") if e["kind"] == "run.cancelled"]
    assert [e["run_id"] for e in cancelled] == ["pending-a"]
    # Who cancelled it is a structured field, not prose.
    assert cancelled[0]["source"] == "src"


def test_cancel_pending_clears_the_queue_but_not_the_new_entries(tmp_path):
    """The re-route move: drop the plan, state a new one. Cancellation runs
    before insertion and only over pre-existing QUEUED runs, so a declaration
    can never cancel what it is adding."""
    store, config, taskdefs, source = _cancel_fixture(tmp_path)

    result = _apply(
        store, config, taskdefs, source,
        [Handoff(key="replacement", target_task="task-a", reason="r")],
        cancel_pending=True,
    )

    assert result["reason"] is None
    runs = {r["run_id"]: r for r in store.read_state("ticket-1")["runs"]}
    assert runs["pending-a"]["state"] == "CANCELLED"
    assert runs["pending-b"]["state"] == "CANCELLED"
    assert runs[result["applied"][0]]["state"] == "QUEUED"


def test_cancel_key_matching_two_entries_is_rejected_whole(tmp_path):
    """Keys are unique per source run, not per ticket, so an ambiguous key is
    an error rather than a guess -- and it rejects the WHOLE declaration."""
    store, config, taskdefs, source = _cancel_fixture(tmp_path)
    store.write(lambda txn: txn.put_run(
        "ticket-1", _queued_run("pending-c", queue_seq=3, handoff_key="qa")
    ))

    result = _apply(
        store, config, taskdefs, source,
        [Handoff(key="mine", target_task="task-a", reason="r")],
        cancel_keys=["qa"],
    )

    assert result["applied"] == []
    assert "ambiguous" in result["reason"]
    states = {r["run_id"]: r["state"] for r in store.read_state("ticket-1")["runs"]}
    assert states["pending-a"] == "QUEUED"  # nothing cancelled
    assert "mine" not in [r.get("handoff_key") for r in store.read_state("ticket-1")["runs"]]


def test_cancelled_runs_do_not_consume_the_run_ceiling(tmp_path):
    """A route revised a few times must not exhaust `max_runs` with work that
    never executed and spent nothing."""
    runs = [
        _queued_run("a", state="CANCELLED"),
        _queued_run("b", state="CANCELLED"),
        _queued_run("c", state="SUCCEEDED"),
    ]
    ok, trace = check_loop_guard(_doc(runs), max_runs=2)
    assert ok is True and trace is None


def test_input_source_is_the_queue_predecessor_not_the_enqueuer(tmp_path):
    """`spec` declaring [implement, review] enqueues both, but `review` reads
    `implement`'s output. Keyed on the enqueuer this resolves to `spec`."""
    runs = [
        _queued_run("spec", state="SUCCEEDED", queue_seq=0),
        _queued_run("implement", state="SUCCEEDED", queue_seq=1, parent_run_id="spec"),
        _queued_run("review", state="QUEUED", queue_seq=2, parent_run_id="spec"),
    ]
    assert resolve_input_source(runs, runs[2]) == "implement"
    # Before implement succeeds, review falls back to the run that enqueued it.
    runs[1]["state"] = "RUNNING"
    assert resolve_input_source(runs, runs[2]) == "spec"


def test_inputs_ready_gates_on_the_predecessor_not_the_enqueuer(tmp_path):
    """Regression for the same conflation at the dispatch gate: `review` must
    wait for `implement`'s artifacts, and must not be admitted merely because
    `spec` (its enqueuer) recorded something."""
    taskdef = {"inputs": {"artifacts": ["specs/{ticket}/review-input.md"]}}
    review = _queued_run("review", state="QUEUED", queue_seq=2, parent_run_id="spec")
    state = {"runs": [
        _queued_run("spec", state="SUCCEEDED", queue_seq=0, artifacts=["specs/7/spec.md"]),
        _queued_run("implement", state="SUCCEEDED", queue_seq=1, parent_run_id="spec",
                    artifacts=[]),
        review,
    ]}
    state["runs"][2]["ticket_id"] = "7"

    assert _inputs_ready(taskdef, review, state) is False

    state["runs"][1]["artifacts"] = ["specs/7/review-input.md"]
    assert _inputs_ready(taskdef, review, state) is True


def test_dispatch_takes_the_lowest_queue_position_first(tmp_path):
    """Ordering is by `queue_seq`, not array position -- the retry inserted
    last in `runs` but holding position 0 goes first."""
    store, config, taskdefs = _dispatch_fixture(tmp_path)
    store.write(lambda txn: (
        txn.update_run("ticket-1", "run-ticket-1", state="SUCCEEDED"),
        txn.put_run("ticket-1", _queued_run("appended-later", queue_seq=5)),
        txn.put_run("ticket-1", _queued_run("holds-position-1", queue_seq=1)),
    ))
    api = _FakeWorkflowApi()

    dispatch(config, taskdefs, store, api, now_iso="2026-07-18T09:00:00Z", issue="ticket-1")

    # Both get triggered -- `check_concurrency` is an advisory pre-filter over a
    # state snapshot, and `claim_run` is the CAS that actually serializes them.
    # What this pins is the ORDER they are offered in: the earlier queue
    # position first, even though it sits last in the `runs` array.
    assert api.triggered[0] == "holds-position-1"
    assert set(api.triggered) == {"holds-position-1", "appended-later"}


def test_dispatch_issue_scope_triggers_only_the_named_ticket(tmp_path):
    """`dispatch(..., issue=...)` is the fast path: it triggers only the
    named ticket's ready run, leaving an equally-eligible run on a different
    ticket for the next unscoped (scheduled) call."""
    store, config, taskdefs = _dispatch_fixture(tmp_path)
    wf = _FakeWorkflowApi()

    triggered = dispatch(
        config, taskdefs, store, wf, now_iso="2026-07-18T00:00:00Z", issue="ticket-1"
    )

    assert triggered == ["run-ticket-1"]
    assert wf.triggered == ["run-ticket-1"]


def test_dispatch_unscoped_call_scans_every_ticket(tmp_path):
    store, config, taskdefs = _dispatch_fixture(tmp_path)
    wf = _FakeWorkflowApi()

    triggered = dispatch(config, taskdefs, store, wf, now_iso="2026-07-18T00:00:00Z")

    assert set(triggered) == {"run-ticket-1", "run-ticket-2"}


class _LabelTracker:
    """Records what `set_status_label` asks for, and answers the next
    `fetch_ticket` with it -- so a sequence of transitions exercises the
    read-modify-write the real adapter performs."""

    def __init__(self, labels):
        self.labels = list(labels)
        self.calls: list[list[str]] = []

    def fetch_ticket(self, ref):
        return TicketDetails(ticket_id="7", title="t", body="b", labels=list(self.labels))

    def set_status_labels(self, ticket_id, status, labels):
        self.labels = sorted(labels)
        self.calls.append(self.labels)


def _label_config():
    return Config(
        projects={"engine_repo": "org/engine"},
        repos={}, components={"tracker": {"adapter": "fake"}}, approvers={}, budgets={},
    )


def test_status_label_transitions_keep_exactly_one_and_preserve_config_labels():
    """The adapter replaces the WHOLE `hq:`-prefixed set, so a status label
    that filtered on the prefix would strip `hq:intake`/`hq:public-safe`/
    `hq:executor=` off the issue. Only STATUS_LABELS values may be dropped,
    and only one of them may ever be applied at a time."""
    tracker = _LabelTracker(["hq:intake", "hq:public-safe", "hq:executor=copilot-cli", "bug"])
    config = _label_config()

    for status in ("ACTIVE", "WAITING_GATE", "ACTIVE", "AWAITING_MERGE", "BLOCKED", "DONE"):
        set_status_label(config, lambda *a, **k: tracker, "7", status)
        owned = [name for name in tracker.labels if name in STATUS_LABELS.values()]
        assert owned == [STATUS_LABELS[status]], f"{status} -> {tracker.labels}"
        # Nothing the engine does not own is ever dropped.
        assert {"hq:intake", "hq:public-safe", "hq:executor=copilot-cli", "bug"} <= set(
            tracker.labels
        )


def test_status_label_for_unknown_status_clears_without_adding():
    tracker = _LabelTracker(["hq:intake", "hq:blocked"])
    set_status_label(_label_config(), lambda *a, **k: tracker, "7", "NOT_A_STATUS")
    assert tracker.labels == ["hq:intake"]
