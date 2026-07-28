import json
from dataclasses import fields
from pathlib import Path

from jsonschema import Draft202012Validator

from engine.models import Event, Handoff, RunState, TaskRun, Ticket, TicketStatus, compute_run_id

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

FULL_HANDOFF = Handoff(
    key="impl-1",
    target_task="implement",
    reason="fan out to implement",
    repo="org/work-repo",
    artifacts=["spec.md"],
    source_run_id="run-1",
)

FULL_RUN_KWARGS = {
    "run_id": "run-1",
    "task_id": "task-1",
    "task_version": 1,
    "ticket_id": "ticket-1",
    "state": RunState.RUNNING,
    "attempt": 1,
    "bindings": {"llm": "claude"},
    "cost_usd": 1.23,
    "tokens": 100,
    "usage_known": True,
    "artifacts": ["log.txt"],
    "chain_depth": 0,
    "deadline": "2026-07-18T00:00:00Z",
    "attempt_started_at": "2026-07-18T00:00:00Z",
    "gate_requested_at": "2026-07-18T00:00:00Z",
    "gate_request_id": "gr-1",
    "base_commit": "abc123",
    "output_commit": "def456",
    "pr_ref": "42",
    "parent_run_id": "run-0",
    "source_event_id": "evt-0",
    "enqueue_index": 3,
    "handoff_key": "impl-1",
    "repo": "org/work-repo",
    "input_artifacts": ["spec.md"],
    "pending_handoffs": [FULL_HANDOFF],
}

MINIMAL_RUN_KWARGS = {
    "run_id": "run-2",
    "task_id": "task-2",
    "task_version": 1,
    "ticket_id": "ticket-2",
    "state": RunState.QUEUED,
    "attempt": 0,
    "bindings": {},
    "cost_usd": None,
    "tokens": None,
    "usage_known": False,
    "artifacts": [],
    "chain_depth": 0,
}


def test_taskrun_full_round_trip():
    run = TaskRun(**FULL_RUN_KWARGS)
    assert TaskRun.from_dict(run.to_dict()) == run


def test_taskrun_minimal_round_trip():
    run = TaskRun(**MINIMAL_RUN_KWARGS)
    assert TaskRun.from_dict(run.to_dict()) == run


def test_taskrun_state_serialized_as_string():
    run = TaskRun(**FULL_RUN_KWARGS)
    assert run.to_dict()["state"] == "RUNNING"


def test_taskrun_to_dict_validates_against_run_subschema():
    schema = json.loads((SCHEMAS_DIR / "state.schema.json").read_text())
    # Keep $defs alongside the $ref so pending_handoffs' "#/$defs/handoff" ref resolves.
    run_schema = {"$defs": schema["$defs"], "$ref": "#/$defs/run"}
    validator = Draft202012Validator(run_schema)

    for kwargs in (FULL_RUN_KWARGS, MINIMAL_RUN_KWARGS):
        run = TaskRun(**kwargs)
        validator.validate(run.to_dict())


def test_taskrun_field_set_includes_handoff_and_repo_fields():
    names = {f.name for f in fields(TaskRun)}
    assert {"handoff_key", "repo", "input_artifacts", "pending_handoffs", "enqueue_index"} <= names


def test_handoff_full_round_trip():
    assert Handoff.from_dict(FULL_HANDOFF.to_dict()) == FULL_HANDOFF


def test_handoff_minimal_round_trip():
    handoff = Handoff(key="k", target_task="review", reason="ready for review")
    assert Handoff.from_dict(handoff.to_dict()) == handoff


def test_handoff_field_set():
    names = {f.name for f in fields(Handoff)}
    assert names == {"key", "target_task", "reason", "repo", "artifacts", "source_run_id"}


def test_handoff_to_dict_validates_against_handoff_subschema():
    schema = json.loads((SCHEMAS_DIR / "state.schema.json").read_text())
    validator = Draft202012Validator(schema["$defs"]["handoff"])
    validator.validate(FULL_HANDOFF.to_dict())


def test_ticket_field_set_includes_block_and_work_repo_fields():
    names = {f.name for f in fields(Ticket)}
    assert {"block_reason", "block_source", "interrupted_run_id", "work_repos"} <= names


def test_ticket_full_round_trip():
    ticket = Ticket(
        ticket_id="ticket-1",
        pinned_comment_id="1",
        status=TicketStatus.BLOCKED,
        block_reason="agent stuck",
        block_source="issue_closed",
        interrupted_run_id="run-1",
        work_repos=[
            {
                "repo": "org/work-repo",
                "branch": "agent-hq/1",
                "pr_ref": "42",
                "recorded_head": "abc123",
                "base_branch": "main",
            }
        ],
    )
    assert Ticket.from_dict(ticket.to_dict()) == ticket


def test_ticket_minimal_round_trip():
    ticket = Ticket(ticket_id="ticket-2", pinned_comment_id=None, status=TicketStatus.ACTIVE)
    assert Ticket.from_dict(ticket.to_dict()) == ticket


def test_ticket_to_dict_validates_against_state_document_schema():
    schema = json.loads((SCHEMAS_DIR / "state.schema.json").read_text())
    validator = Draft202012Validator(schema)
    ticket = Ticket(
        ticket_id="ticket-1",
        pinned_comment_id="1",
        status=TicketStatus.BLOCKED,
        block_reason="agent stuck",
        block_source="issue_closed",
        interrupted_run_id="run-1",
        work_repos=[{"repo": "org/work-repo"}],
    )
    doc = {**ticket.to_dict(), "runs": [TaskRun(**FULL_RUN_KWARGS).to_dict()]}
    validator.validate(doc)


def test_event_full_round_trip():
    event = Event(
        event_id="evt-1",
        kind="run.state_changed",
        ticket_id="ticket-1",
        run_id="run-1",
        task_id="task-1",
        task_version=1,
        state=RunState.SUCCEEDED,
        duration_seconds=12.5,
        tokens=100,
        cost_usd=0.5,
        bindings={"llm": "claude"},
        run_url="https://example.com/run/1",
        artifacts=["log.txt"],
    )
    assert Event.from_dict(event.to_dict()) == event


def test_event_minimal_round_trip():
    event = Event(event_id="evt-2", kind="run.queued", ticket_id="ticket-2", run_id="run-2")
    assert Event.from_dict(event.to_dict()) == event


def test_event_minimal_to_dict_validates_against_schema():
    schema = json.loads((SCHEMAS_DIR / "event.schema.json").read_text())
    validator = Draft202012Validator(schema)
    event = Event(event_id="evt-2", kind="run.queued", ticket_id="ticket-2", run_id="run-2")
    validator.validate(event.to_dict())


def test_compute_run_id_is_deterministic():
    id1 = compute_run_id("parent-1", 3, "task-1", 0)
    id2 = compute_run_id("parent-1", 3, "task-1", 0)
    assert id1 == id2
    assert len(id1) == 16


def test_compute_run_id_differs_per_component():
    base = compute_run_id("parent-1", 3, "task-1", 0)
    assert compute_run_id("parent-2", 3, "task-1", 0) != base
    assert compute_run_id("parent-1", 4, "task-1", 0) != base
    assert compute_run_id("parent-1", 3, "task-2", 0) != base
    assert compute_run_id("parent-1", 3, "task-1", 1) != base
