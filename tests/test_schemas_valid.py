import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
SCHEMA_FILES = sorted(SCHEMAS_DIR.glob("*.json"))


@pytest.mark.parametrize("schema_path", SCHEMA_FILES, ids=lambda p: p.name)
def test_schema_is_valid_draft_2020_12(schema_path):
    schema = json.loads(schema_path.read_text())
    Draft202012Validator.check_schema(schema)


def _load_schema(name):
    return json.loads((SCHEMAS_DIR / name).read_text())


CONTROL_SCHEMA = _load_schema("control.schema.json")


@pytest.mark.parametrize(
    "doc",
    [
        # An empty queue is how a run says "nothing further from me" -- there is
        # no separate `complete` outcome to say it with.
        {"outcome": "queue", "queue": []},
        {"outcome": "blocked", "reason": "missing credentials"},
        {
            "outcome": "queue",
            "queue": [{"key": "impl-1", "task": "implement", "reason": "fan out"}],
        },
        {"outcome": "queue", "queue": [], "cancel": ["stale-qa"]},
        {
            "outcome": "queue",
            "cancel_pending": True,
            "queue": [{"key": "respec", "task": "spec", "reason": "re-route"}],
        },
    ],
    ids=[
        "queue-empty-means-done",
        "blocked-with-reason",
        "queue-with-entries",
        "queue-cancelling-a-key",
        "queue-replacing-the-route",
    ],
)
def test_control_schema_accepts_valid_docs(doc):
    Draft202012Validator(CONTROL_SCHEMA).validate(doc)


@pytest.mark.parametrize(
    "doc",
    [
        {"outcome": "queue"},
        {"outcome": "complete"},
        {
            "outcome": "handoff",
            "handoffs": [{"key": "impl-1", "task": "implement", "reason": "fan out"}],
        },
        {
            "outcome": "blocked",
            "reason": "stuck",
            "queue": [{"key": "impl-1", "task": "implement", "reason": "fan out"}],
        },
        {"outcome": "blocked", "reason": "stuck", "cancel": ["impl-1"]},
        {"outcome": "blocked", "reason": "stuck", "cancel_pending": True},
        {"outcome": "blocked"},
    ],
    ids=[
        "queue-missing-queue",
        "retired-complete-outcome",
        "retired-handoff-outcome",
        "blocked-with-queue",
        "blocked-with-cancel",
        "blocked-with-cancel-pending",
        "blocked-missing-reason",
    ],
)
def test_control_schema_rejects_invalid_docs(doc):
    with pytest.raises(ValidationError):
        Draft202012Validator(CONTROL_SCHEMA).validate(doc)


EXECUTE_RESULT_SCHEMA = _load_schema("execute-result.schema.json")


@pytest.mark.parametrize(
    "doc",
    [
        {"outcome": "success", "usage_known": True, "cost_usd": 0.12, "tokens": 4200},
        {
            "outcome": "failure",
            "usage_known": False,
            "cost_usd": None,
            "tokens": None,
            "detail": "agent timed out",
        },
    ],
    ids=["success", "failure-with-detail"],
)
def test_execute_result_schema_accepts_valid_docs(doc):
    Draft202012Validator(EXECUTE_RESULT_SCHEMA).validate(doc)


@pytest.mark.parametrize(
    "doc",
    [
        {"outcome": "timeout", "usage_known": False, "cost_usd": None, "tokens": None},
        {
            "outcome": "success",
            "usage_known": True,
            "cost_usd": 0.1,
            "tokens": 10,
            "session_id": "abc123",
        },
    ],
    ids=["timeout-not-allowed", "session_id-not-allowed"],
)
def test_execute_result_schema_rejects_invalid_docs(doc):
    with pytest.raises(ValidationError):
        Draft202012Validator(EXECUTE_RESULT_SCHEMA).validate(doc)
