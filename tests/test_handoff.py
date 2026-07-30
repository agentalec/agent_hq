"""Tests for engine.handoff.validate_queue -- pure schema, containment,
and provenance validation of a task's proposed handoffs. No state-store
input: ledger/loop/budget/depth guards are Task 9's apply_queue, not this
module."""

import os

import pytest

from engine.config import Config
from engine.handoff import validate_queue
from engine.models import RunState, TaskRun

TICKET_ID = "T-1"

SOURCE_TASKDEF = {
    "id": "spec",
    "outputs": {"artifacts": ["specs/{ticket}/spec.md"]},
    "handoff": {"allowed": ["implement", "review"], "max": 2},
}

TASKDEFS = {
    "spec": SOURCE_TASKDEF,
    "implement": {"id": "implement"},
    "review": {"id": "review"},
    "finalize": {"id": "finalize"},
}

CONFIG = Config(
    components={}, repos={"org/repo": {}}, projects={}, approvers={}, budgets={}
)


def _run(**overrides) -> TaskRun:
    kwargs = {
        "run_id": "src-1",
        "task_id": "spec",
        "task_version": 1,
        "ticket_id": TICKET_ID,
        "state": RunState.RUNNING,
        "attempt": 1,
        "bindings": {},
        "cost_usd": None,
        "tokens": None,
        "usage_known": False,
        "artifacts": [],
        "chain_depth": 0,
        "input_artifacts": ["specs/T-1/plan.md"],
    }
    kwargs.update(overrides)
    return TaskRun(**kwargs)


@pytest.fixture
def worktree(tmp_path):
    (tmp_path / "specs" / TICKET_ID).mkdir(parents=True)
    (tmp_path / "specs" / TICKET_ID / "spec.md").write_text("spec")
    (tmp_path / "specs" / TICKET_ID / "plan.md").write_text("plan")
    (tmp_path / "specs" / TICKET_ID / "extra.md").write_text("not declared anywhere")
    return tmp_path


def _handoff_doc(*handoffs):
    return {"outcome": "queue", "queue": list(handoffs)}


def _valid_item(**overrides):
    item = {
        "key": "impl-1",
        "task": "implement",
        "reason": "fan out",
        "repo": "org/repo",
        "artifacts": ["specs/T-1/spec.md", "specs/T-1/plan.md"],
    }
    item.update(overrides)
    return item


def test_valid_handoff_set_accepted(worktree):
    control = _handoff_doc(_valid_item())
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert reason is None
    assert len(accepted) == 1
    h = accepted[0]
    assert h.key == "impl-1"
    assert h.target_task == "implement"
    assert h.repo == "org/repo"
    assert h.source_run_id == "src-1"
    assert h.artifacts == ["specs/T-1/spec.md", "specs/T-1/plan.md"]


def test_non_handoff_outcome_is_a_noop(worktree):
    control = {"outcome": "queue", "queue": []}
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert accepted == []
    assert reason is None


def test_schema_invalid_control_doc_rejects_whole_set(worktree):
    # handoff item missing required "reason" -> schema-invalid.
    control = {
        "outcome": "queue",
        "queue": [{"key": "impl-1", "task": "implement"}],
    }
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert accepted == []
    assert reason is not None
    assert "schema" in reason


def test_absolute_artifact_path_rejected(worktree):
    control = _handoff_doc(_valid_item(artifacts=["/etc/passwd"]))
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert accepted == []
    assert "absolute" in reason


def test_parent_traversal_artifact_path_rejected(worktree):
    control = _handoff_doc(_valid_item(artifacts=["../secret.txt"]))
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert accepted == []
    assert ".." in reason


def test_missing_artifact_file_rejected(worktree):
    control = _handoff_doc(_valid_item(artifacts=["specs/T-1/missing.md"]))
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert accepted == []
    assert "not found" in reason


def test_symlink_escape_artifact_rejected(worktree, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    secret = outside / "secret.md"
    secret.write_text("secret")
    escape_link = worktree / "specs" / TICKET_ID / "escape.md"
    os.symlink(secret, escape_link)

    control = _handoff_doc(_valid_item(artifacts=["specs/T-1/escape.md"]))
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert accepted == []
    assert "escapes" in reason


def test_unknown_target_task_rejected(worktree):
    control = _handoff_doc(_valid_item(task="does-not-exist", artifacts=[]))
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert accepted == []
    assert "not a known task" in reason


def test_target_not_in_allowed_rejected(worktree):
    control = _handoff_doc(_valid_item(task="finalize", artifacts=[]))
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert accepted == []
    assert "handoff.allowed" in reason


def test_unknown_repo_rejected(worktree):
    control = _handoff_doc(_valid_item(repo="org/unknown-repo", artifacts=[]))
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert accepted == []
    assert "configured repo" in reason


def test_over_max_handoffs_rejected(worktree):
    control = _handoff_doc(
        _valid_item(key="impl-1", task="implement", artifacts=[]),
        _valid_item(key="impl-2", task="implement", artifacts=[]),
        _valid_item(key="review-1", task="review", artifacts=[]),
    )
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert accepted == []
    assert "handoff.max" in reason


def test_duplicate_handoff_key_rejected(worktree):
    control = _handoff_doc(
        _valid_item(key="dup", task="implement", artifacts=[]),
        _valid_item(key="dup", task="review", artifacts=[]),
    )
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert accepted == []
    assert "duplicate" in reason


def test_artifact_outside_provenance_rejected(worktree):
    # specs/T-1/extra.md is a real, contained file, but neither an inherited
    # input_artifact nor a declared output of this task -- must be rejected.
    control = _handoff_doc(_valid_item(artifacts=["specs/T-1/extra.md"]))
    accepted, reason = validate_queue(
        control, taskdef=SOURCE_TASKDEF, taskdefs=TASKDEFS, config=CONFIG,
        worktree=worktree, run=_run(),
    )
    assert accepted == []
    assert "provenance" in reason
