"""P0 task library (Task 14): schema/library validity, the exact P0 enqueue
chain, gate-adapter resolvability, and no-concrete-adapter-name discipline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from engine.cli import build_parser
from engine.config import load_config, resolve_binding
from engine.engine import build_port_adapter
from engine.taskdefs import load_all, validate_library

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
TASKS_DIR = REPO_ROOT / "tasks"
CONFIG_DIR = REPO_ROOT / "config"

P0_CHAIN = {
    "intake": [{"task": "spec"}],
    "spec": [{"task": "arch-plan"}],
    "arch-plan": [
        {
            "task": "arch-approval",
            "when": {"field": "plan.classification", "op": "eq", "value": "beyond-crud"},
        },
        {
            "task": "breakdown",
            "when": {"field": "plan.classification", "op": "ne", "value": "beyond-crud"},
        },
    ],
    "arch-approval": [{"task": "breakdown"}],
    "breakdown": [{"task": "implement"}],
    "implement": [{"task": "review"}],
    "review": [{"task": "finalize"}],
    "finalize": [],
}

CONCRETE_ADAPTER_NAMES = ("github-issues", "github-comment", "pr-review", "claude-code-headless")


def test_task_library_loads_and_validates_clean():
    taskdefs = load_all(TASKS_DIR, SCHEMAS_DIR)
    assert set(taskdefs) == set(P0_CHAIN)
    assert validate_library(taskdefs) == []


def test_enqueue_graph_is_exactly_the_p0_chain():
    taskdefs = load_all(TASKS_DIR, SCHEMAS_DIR)
    for task_id, expected in P0_CHAIN.items():
        actual = taskdefs[task_id].get("on_success", {}).get("enqueue", [])
        assert actual == expected, f"{task_id}: on_success.enqueue mismatch"


def test_gate_tasks_resolve_to_constructible_adapters():
    config = load_config(CONFIG_DIR, SCHEMAS_DIR)
    taskdefs = load_all(TASKS_DIR, SCHEMAS_DIR)
    gate_tasks = [t for t in taskdefs.values() if t.get("gates", {}).get("post")]
    assert gate_tasks, "expected at least one gate task in the P0 library"
    for taskdef in gate_tasks:
        for gate in taskdef["gates"]["post"]:
            adapter_name = resolve_binding(config, "gate", gate["adapter"], [])
            adapter = build_port_adapter(config, "gate", adapter_name, repo="example-org/product-be")
            assert adapter is not None


def test_no_concrete_adapter_name_leaks_into_task_defs():
    for task_yml in TASKS_DIR.glob("*/task.yml"):
        text = task_yml.read_text()
        for name in CONCRETE_ADAPTER_NAMES:
            assert name not in text, f"{task_yml}: concrete adapter name '{name}' found"


def test_cli_tasks_validate_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "engine.cli", "tasks", "validate", "--repo-root", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tasks OK" in result.stdout


def test_cli_tasks_validate_direct_call(capsys):
    parser = build_parser()
    args = parser.parse_args(["tasks", "validate", "--repo-root", str(REPO_ROOT)])
    args.func(args, REPO_ROOT)
    assert "tasks OK" in capsys.readouterr().out
