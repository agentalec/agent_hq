from pathlib import Path

from test_state import _clone_worktree, _make_origin

from engine.config import Config
from engine.engine import (
    STATUS_LABELS,
    apply_handoffs,
    check_budget,
    check_concurrency,
    check_loop_guard,
    dispatch,
    enqueue,
    intake_repo,
    kill_switch_active,
    resolve_target_repo,
    set_status_label,
)
from engine.models import Handoff, TicketDetails
from engine.state import GitJsonStateStore


def _store(tmp_path: Path) -> tuple[GitJsonStateStore, Path]:
    origin = _make_origin(tmp_path)
    worktree = _clone_worktree(tmp_path, origin, "wt")
    return GitJsonStateStore(worktree), worktree


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
    ok, trace = check_loop_guard(_doc([_run("r1", "SUCCEEDED")]), max_runs=25, max_depth=12)
    assert ok is True
    assert trace is None


def test_check_loop_guard_max_runs_breach_returns_trace():
    runs = [
        {"run_id": f"r{i}", "task_id": "t", "parent_run_id": None, "chain_depth": 0}
        for i in range(3)
    ]
    ok, trace = check_loop_guard(_doc(runs), max_runs=2, max_depth=12)
    assert ok is False
    assert len(trace) == 3
    assert trace[0] == {"run_id": "r0", "task_id": "t", "parent_run_id": None}


def test_check_loop_guard_max_depth_breach():
    doc = _doc([{"run_id": "r1", "task_id": "t", "parent_run_id": "r0", "chain_depth": 13}])
    ok, trace = check_loop_guard(doc, max_runs=25, max_depth=12)
    assert ok is False
    assert trace[0]["run_id"] == "r1"


def test_apply_handoffs_rejects_batch_that_would_exceed_max_runs(tmp_path):
    """Regression: capacity must be checked against the WHOLE accepted batch
    (`len(runs) + len(accepted)`), not just the pre-insertion run count --
    else a two-handoff batch can land both runs even past max_runs."""
    store, _ = _store(tmp_path)
    config = Config(
        components={}, repos={}, projects={}, approvers={},
        budgets={"loop_guard": {"max_runs": 2, "max_depth": 12}, "ticket_cap_usd": 1000.0},
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
        applied, reason = apply_handoffs(txn, config, taskdefs, "ticket-1", source_run, accepted)
        result["applied"], result["reason"] = applied, reason

    store.write(try_apply)
    assert result["applied"] == []
    assert "loop guard" in result["reason"]

    # One more run of headroom (max_runs=3: existing 1 + batch of 2 = 3) fits.
    config.budgets["loop_guard"]["max_runs"] = 3
    store.write(try_apply)
    assert result["reason"] is None
    assert len(result["applied"]) == 2


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
            "loop_guard": {"max_runs": 25, "max_depth": 12},
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
