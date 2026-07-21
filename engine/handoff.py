"""Pure handoff-proposal validation (schemas/control.schema.json).

`validate_handoffs` checks a task's `.agent-hq/control.json` against the
control schema, then -- for a `handoff` outcome -- each proposed handoff's
artifact-path containment and provenance. It takes no state-store or
ticket-state input: ledger-existence and loop/budget/depth guards need state
and are enforced atomically in Task 9's `apply_handoffs` transaction, not
here.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from engine.config import Config
from engine.engine import subst
from engine.models import Handoff, TaskRun

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "control.schema.json"


def _load_control_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text())


def _check_containment(worktree: Path, rel_path: str) -> str | None:
    """None if rel_path is a real file resolving inside worktree; else a
    rejection reason. worktree must already be an absolute, resolved path."""
    if Path(rel_path).is_absolute():
        return f"artifact path is absolute: {rel_path}"
    if ".." in Path(rel_path).parts:
        return f"artifact path contains '..': {rel_path}"
    full = worktree / rel_path
    if not full.exists():
        return f"artifact not found in worktree: {rel_path}"
    if not full.resolve().is_relative_to(worktree):
        return f"artifact path escapes worktree (symlink): {rel_path}"
    return None


def validate_handoffs(
    control: dict,
    *,
    taskdef: dict,
    taskdefs: dict[str, dict],
    config: Config,
    worktree: str | Path,
    run: TaskRun,
) -> tuple[list[Handoff], str | None]:
    """Validate the source run's proposed handoffs. Returns (accepted,
    rejection_reason): any single schema/containment/provenance violation
    rejects the WHOLE proposed set (accepted == []).
    """
    validator = Draft202012Validator(_load_control_schema())
    errors = sorted(validator.iter_errors(control), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        json_path = "/".join(str(p) for p in first.path) or "<root>"
        return [], f"control.json schema violation: {json_path}: {first.message}"

    if control["outcome"] != "handoff":
        return [], None

    proposed = control["handoffs"]
    worktree = Path(worktree).resolve()

    # Pass 1: path containment on every declared artifact across every handoff.
    for item in proposed:
        for rel_path in item.get("artifacts", []):
            reason = _check_containment(worktree, rel_path)
            if reason:
                return [], reason

    # Pass 2: per-handoff semantic checks.
    handoff_cfg = taskdef.get("handoff", {})
    allowed = set(handoff_cfg.get("allowed", []))
    max_handoffs = handoff_cfg.get("max", 0)
    if len(proposed) > max_handoffs:
        return [], f"{len(proposed)} handoffs exceeds this task's handoff.max ({max_handoffs})"

    provenance = set(run.input_artifacts or [])
    provenance |= {
        subst(a, run.ticket_id) for a in taskdef.get("outputs", {}).get("artifacts", [])
    }

    seen_keys: set[str] = set()
    accepted: list[Handoff] = []
    for item in proposed:
        key = item["key"]
        target = item["task"]
        repo = item.get("repo")
        artifacts = item.get("artifacts", [])

        if key in seen_keys:
            return [], f"duplicate handoff key: {key}"
        seen_keys.add(key)

        if target not in taskdefs:
            return [], f"handoff target '{target}' is not a known task"
        if target not in allowed:
            return [], f"handoff target '{target}' is not in this task's handoff.allowed"
        if repo is not None and repo not in config.repos:
            return [], f"handoff repo '{repo}' is not a configured repo"
        for rel_path in artifacts:
            if rel_path not in provenance:
                return [], f"artifact '{rel_path}' is not in this run's provenance set"

        accepted.append(
            Handoff(
                key=key,
                target_task=target,
                reason=item["reason"],
                repo=repo,
                artifacts=list(artifacts),
                source_run_id=run.run_id,
            )
        )

    return accepted, None
