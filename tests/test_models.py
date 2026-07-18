import json
from pathlib import Path

from jsonschema import Draft202012Validator

from engine.models import Event, RunState, TaskRun, compute_run_id

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

FULL_RUN_KWARGS = dict(
    run_id="run-1",
    task_id="task-1",
    task_version=1,
    ticket_id="ticket-1",
    state=RunState.RUNNING,
    attempt=1,
    bindings={"llm": "claude"},
    cost_usd=1.23,
    tokens=100,
    usage_known=True,
    artifacts=["log.txt"],
    chain_depth=0,
    deadline="2026-07-18T00:00:00Z",
    attempt_started_at="2026-07-18T00:00:00Z",
    gate_requested_at="2026-07-18T00:00:00Z",
    gate_request_id="gr-1",
    base_commit="abc123",
    output_commit="def456",
    pr_ref="42",
    parent_run_id="run-0",
    source_event_id="evt-0",
    enqueue_index=3,
)

MINIMAL_RUN_KWARGS = dict(
    run_id="run-2",
    task_id="task-2",
    task_version=1,
    ticket_id="ticket-2",
    state=RunState.QUEUED,
    attempt=0,
    bindings={},
    cost_usd=None,
    tokens=None,
    usage_known=False,
    artifacts=[],
    chain_depth=0,
)


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
    run_schema = schema["$defs"]["run"]
    validator = Draft202012Validator(run_schema)

    for kwargs in (FULL_RUN_KWARGS, MINIMAL_RUN_KWARGS):
        run = TaskRun(**kwargs)
        validator.validate(run.to_dict())


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
