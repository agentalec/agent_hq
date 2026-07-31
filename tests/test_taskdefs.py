from pathlib import Path

import pytest
import yaml

from engine.models import TicketDetails
from engine.runner import _assemble_prompt
from engine.taskdefs import TaskDefError, load_all, load_task, validate_library

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "tasks"


def _write_task(task_dir: Path, taskdef: dict) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.yml").write_text(yaml.safe_dump(taskdef))


def _minimal_taskdef(task_id: str = "sample", **overrides) -> dict:
    base = {
        "id": task_id,
        "version": 1,
        "description": "A test task.",
        "trigger": "enqueued_by",
        "budget": {"max_cost_usd": 5, "max_runtime_min": 30, "retries": 2},
    }
    base.update(overrides)
    return base


def test_sample_fixture_loads():
    taskdef = load_task(FIXTURES_DIR / "sample", SCHEMAS_DIR)
    assert taskdef["id"] == "sample"
    assert taskdef["skills"] == ["prompts/sample.md"]


def test_prompt_inlines_task_instructions_context_and_required_outputs():
    taskdef = load_task(REPO_ROOT / "tasks" / "spec", SCHEMAS_DIR)
    details = TicketDetails("HQ-7", "Example", "A sufficiently detailed ticket.", [])

    prompt = _assemble_prompt(taskdef, details, None)

    assert "# Spec quality checklist" in prompt
    assert "# Constitution" in prompt
    assert "`specs/HQ-7/spec.md`" in prompt
    assert "{ticket}" not in prompt


def test_queueable_menu_carries_each_task_description():
    """With no `handoff.allowed` left, the runtime menu is the only thing that
    tells an agent what it may queue -- ids alone would make it guess from a
    name, so every entry carries its task.yml description."""
    taskdefs = load_all(REPO_ROOT / "tasks", SCHEMAS_DIR)
    details = TicketDetails("HQ-7", "Example", "A sufficiently detailed ticket.", [])

    prompt = _assemble_prompt(
        load_task(REPO_ROOT / "tasks" / "spec", SCHEMAS_DIR),
        details,
        None,
        run={"run_id": "r1"},
        taskdefs=taskdefs,
    )

    for task_id, taskdef in taskdefs.items():
        assert f"`{task_id}` -- {taskdef['description']}".replace("{ticket}", "HQ-7") in prompt
    assert "{ticket}" not in prompt


def test_schema_violation_rejected_with_clear_error(tmp_path):
    taskdef = _minimal_taskdef(budget={"max_cost_usd": -1})
    _write_task(tmp_path / "bad", taskdef)

    with pytest.raises(TaskDefError) as excinfo:
        load_task(tmp_path / "bad", SCHEMAS_DIR)

    assert any("max_cost_usd" in e or "-1" in e for e in excinfo.value.errors)


def test_a_task_declaring_a_route_is_rejected(tmp_path):
    """`handoff` is gone from the task schema: a task no longer declares which
    tasks may follow it. A leftover block is a hard load error rather than a
    silently ignored key, so a stale task.yml can't look like it still
    constrains the route."""
    _write_task(tmp_path / "stale", _minimal_taskdef(handoff={"allowed": ["x"], "max": 1}))

    with pytest.raises(TaskDefError) as excinfo:
        load_task(tmp_path / "stale", SCHEMAS_DIR)

    assert any("handoff" in e for e in excinfo.value.errors)


def test_gate_auto_approve_loads_and_is_typed(tmp_path):
    """`auto_approve` is a real schema field, not something the engine reads
    out of an unvalidated dict -- and a non-boolean is rejected at load."""
    gate = {"approvers": "product-owners", "adapter": "default", "auto_approve": True}
    _write_task(tmp_path / "auto", _minimal_taskdef("auto", gates={"post": [gate]}))
    loaded = load_task(tmp_path / "auto", SCHEMAS_DIR)
    assert loaded["gates"]["post"][0]["auto_approve"] is True

    _write_task(tmp_path / "bad", _minimal_taskdef("bad", gates={"post": [{**gate, "auto_approve": "yes"}]}))
    with pytest.raises(TaskDefError) as excinfo:
        load_task(tmp_path / "bad", SCHEMAS_DIR)
    assert any("auto_approve" in e for e in excinfo.value.errors)


def test_missing_skills_path_rejected(tmp_path):
    taskdef = _minimal_taskdef(skills=["prompts/missing.md"])
    _write_task(tmp_path / "bad", taskdef)

    with pytest.raises(TaskDefError) as excinfo:
        load_task(tmp_path / "bad", SCHEMAS_DIR)

    assert any("prompts/missing.md" in e for e in excinfo.value.errors)


def test_symbolic_context_refs_are_not_checked_for_existence(tmp_path):
    taskdef = _minimal_taskdef(
        context=["capability-index@latest", "constitution", "specs/{ticket}/*"]
    )
    _write_task(tmp_path / "ok", taskdef)

    loaded = load_task(tmp_path / "ok", SCHEMAS_DIR)

    assert loaded["context"][0] == "capability-index@latest"


def test_library_validates_each_task_in_isolation(tmp_path):
    """There are no declared route edges left to cross-check. A queue entry's
    target is checked against the loaded library when a run actually declares
    one (`engine.handoff.validate_queue`), which is the only place a real
    target exists."""
    _write_task(tmp_path / "task-a", _minimal_taskdef("task-a"))
    _write_task(tmp_path / "task-b", _minimal_taskdef("task-b"))

    taskdefs = load_all(tmp_path, SCHEMAS_DIR)
    assert validate_library(taskdefs) == []
