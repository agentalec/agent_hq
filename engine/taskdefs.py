"""Task-definition loader (§5.1, TE-4).

Parses per-task task.yml files, schema-validates them, verifies that
task-local skill/context references exist on disk, and cross-checks
on_success/on_failure enqueue targets against the loaded task library.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

# context entries not starting with one of these are symbolic references
# (e.g. "capability-index@latest", "constitution", "specs/{ticket}/*") and
# are not task-local files, so their existence is not checked.
TASK_LOCAL_CONTEXT_PREFIXES = ("prompts/", "checklists/")


class TaskDefError(Exception):
    """Raised with every violation found while loading task definitions."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def load_task(task_dir: str | Path, schemas_dir: str | Path) -> dict:
    """Load and validate a single task_dir/task.yml.

    Returns the parsed task definition dict. Raises TaskDefError with every
    schema violation, or every missing task-local skills/context reference.
    """
    task_dir = Path(task_dir)
    schemas_dir = Path(schemas_dir)
    label = f"{task_dir.name}/task.yml"
    yml_path = task_dir / "task.yml"

    try:
        taskdef = yaml.safe_load(yml_path.read_text()) or {}
    except FileNotFoundError as exc:
        raise TaskDefError([f"{label}: <root>: file is missing"]) from exc
    except yaml.YAMLError as exc:
        raise TaskDefError([f"{label}: <root>: YAML parse error: {exc}"]) from exc

    schema = json.loads((schemas_dir / "task.schema.json").read_text())
    validator = Draft202012Validator(schema)
    errors = []
    for error in validator.iter_errors(taskdef):
        json_path = "/".join(str(p) for p in error.path) or "<root>"
        errors.append(f"{label}: {json_path}: {error.message}")
    if errors:
        # Path references are only meaningful once the def is structurally valid.
        raise TaskDefError(errors)

    for ref in taskdef.get("skills", []):
        if not (task_dir / ref).exists():
            errors.append(f"{label}: skills: '{ref}' does not exist in task dir")
    for ref in taskdef.get("context", []):
        if ref.startswith(TASK_LOCAL_CONTEXT_PREFIXES) and not (task_dir / ref).exists():
            errors.append(f"{label}: context: '{ref}' does not exist in task dir")
    if errors:
        raise TaskDefError(errors)

    # Runtime-only source locations let the runner inline task instructions;
    # these keys are added after schema validation and never written to state.
    taskdef["_task_dir"] = str(task_dir)
    taskdef["_repo_root"] = str(schemas_dir.parent)
    return taskdef


def load_all(tasks_dir: str | Path, schemas_dir: str | Path) -> dict[str, dict]:
    """Load every task.yml under tasks_dir/*/task.yml.

    Returns a dict of task id -> task definition dict. Raises TaskDefError
    with every violation collected across all task dirs, including id
    collisions between two directories.
    """
    tasks_dir = Path(tasks_dir)
    errors: list[str] = []
    taskdefs: dict[str, dict] = {}
    for task_dir in sorted(p for p in tasks_dir.iterdir() if p.is_dir()):
        if not (task_dir / "task.yml").exists():
            continue
        try:
            taskdef = load_task(task_dir, schemas_dir)
        except TaskDefError as exc:
            errors.extend(exc.errors)
            continue
        task_id = taskdef["id"]
        if task_id in taskdefs:
            errors.append(f"{task_dir.name}/task.yml: id: duplicate task id '{task_id}'")
            continue
        taskdefs[task_id] = taskdef

    if errors:
        raise TaskDefError(errors)
    return taskdefs


def validate_library(taskdefs: dict[str, dict]) -> list[str]:
    """Cross-task checks against an already-loaded library.

    Ids are unique by construction (dict keys); this also flags a taskdef
    whose declared `id` doesn't match the key it's stored under. Every
    on_success/on_failure enqueue target must resolve to a loaded task id.
    """
    errors: list[str] = []
    for task_id, taskdef in taskdefs.items():
        if taskdef.get("id") != task_id:
            errors.append(f"{task_id}: id: declared id '{taskdef.get('id')}' does not match")
        for phase in ("on_success", "on_failure"):
            for item in taskdef.get(phase, {}).get("enqueue", []):
                target = item["task"]
                if target not in taskdefs:
                    errors.append(
                        f"{task_id}: {phase}.enqueue: task '{target}' is not in the loaded library"
                    )
    return errors
