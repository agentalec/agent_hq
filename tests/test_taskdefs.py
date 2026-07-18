from pathlib import Path

import pytest
import yaml

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


def test_schema_violation_rejected_with_clear_error(tmp_path):
    taskdef = _minimal_taskdef(
        on_success={
            "enqueue": [{"task": "other", "when": {"field": "x", "op": "nope", "value": 1}}]
        }
    )
    _write_task(tmp_path / "bad", taskdef)

    with pytest.raises(TaskDefError) as excinfo:
        load_task(tmp_path / "bad", SCHEMAS_DIR)

    assert any("op" in e for e in excinfo.value.errors)


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


def test_library_rejects_enqueue_target_not_in_library(tmp_path):
    task_a = _minimal_taskdef("task-a", on_success={"enqueue": [{"task": "task-b"}]})
    _write_task(tmp_path / "task-a", task_a)

    taskdefs = load_all(tmp_path, SCHEMAS_DIR)
    errors = validate_library(taskdefs)

    assert any("task-b" in e for e in errors)


def test_library_accepts_resolvable_enqueue_targets(tmp_path):
    task_a = _minimal_taskdef("task-a", on_success={"enqueue": [{"task": "task-b"}]})
    task_b = _minimal_taskdef("task-b")
    _write_task(tmp_path / "task-a", task_a)
    _write_task(tmp_path / "task-b", task_b)

    taskdefs = load_all(tmp_path, SCHEMAS_DIR)
    assert validate_library(taskdefs) == []
