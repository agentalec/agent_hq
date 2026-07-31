"""Task library: schema/library validity, gate-adapter resolvability,
no-concrete-adapter-name discipline, and retired-vocabulary discipline in the
agent-facing prompts. The static P0_CHAIN (on_success/on_failure) is gone, and
so is the per-task `handoff.allowed` graph that replaced it -- the route is the
queue a run declares, so this file asserts the generic properties every task
must hold, not one fixed chain.
"""

from __future__ import annotations

import re
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

# Every wired task and its P1 (defined-but-unwired) siblings; no `intake` --
# intake is engine entry logic (config.projects["intake"]/["initial_task"]),
# not a task definition.
EXPECTED_TASK_IDS = {
    "spec", "arch-plan", "arch-approval", "breakdown", "implement", "review",
    "finalize", "clinical", "poll", "qa", "docs", "triage",
}

CONCRETE_ADAPTER_NAMES = (
    "github-issues", "github-comment", "pr-review", "github-issue-comment",
    "claude-code-headless", "copilot-cli",
)


def test_task_library_loads_and_validates_clean():
    taskdefs = load_all(TASKS_DIR, SCHEMAS_DIR)
    assert set(taskdefs) == EXPECTED_TASK_IDS
    assert validate_library(taskdefs) == []


def test_no_task_declares_a_route():
    """The library encodes no graph. There used to be a hand-maintained
    `handoff.allowed`/`max` table across every task.yml -- eleven files
    describing one route -- and the queue replaced it: what runs next is
    declared per run and revisable by any later run. A task.yml that still
    carries a `handoff` block would fail schema load, so this asserts the
    stronger property that none of them mention it at all."""
    taskdefs = load_all(TASKS_DIR, SCHEMAS_DIR)
    assert set(taskdefs) == EXPECTED_TASK_IDS
    offenders = [tid for tid, td in taskdefs.items() if "handoff" in td]
    assert offenders == []


def test_gate_tasks_resolve_to_constructible_adapters():
    config = load_config(CONFIG_DIR, SCHEMAS_DIR)
    taskdefs = load_all(TASKS_DIR, SCHEMAS_DIR)
    gate_tasks = [t for t in taskdefs.values() if t.get("gates", {}).get("post")]
    assert gate_tasks, "expected at least one gate task in the library"
    for taskdef in gate_tasks:
        for gate in taskdef["gates"]["post"]:
            adapter_name = resolve_binding(config, "gate", gate["adapter"], [])
            adapter = build_port_adapter(config, "gate", adapter_name, repo="agentalec/care")
            assert adapter is not None


def test_default_and_spec_approval_gate_bindings_use_the_issue_comment_gate():
    """The atomic cutover repoints the default/spec-approval gate bindings
    off pr-review onto the authorized issue-comment gate (docs/ports/gate.md)."""
    config = load_config(CONFIG_DIR, SCHEMAS_DIR)
    assert resolve_binding(config, "gate", "default", []) == "github-issue-comment"
    assert resolve_binding(config, "gate", "spec-approval", []) == "github-issue-comment"


def test_no_concrete_adapter_name_leaks_into_task_defs():
    for task_yml in TASKS_DIR.glob("*/task.yml"):
        text = task_yml.read_text()
        for name in CONCRETE_ADAPTER_NAMES:
            assert name not in text, f"{task_yml}: concrete adapter name '{name}' found"


def test_no_intake_task_directory():
    assert not (TASKS_DIR / "intake").exists()


def test_cli_tasks_validate_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "engine.cli", "tasks", "validate", "--repo-root", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT, check=False
)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tasks OK" in result.stdout


def test_cli_tasks_validate_direct_call(capsys):
    parser = build_parser()
    args = parser.parse_args(["tasks", "validate", "--repo-root", str(REPO_ROOT)])
    args.func(args, REPO_ROOT)
    assert "tasks OK" in capsys.readouterr().out


# Vocabulary the control schema no longer accepts. `outcome: "handoff"` and
# `outcome: "complete"` are rejected outright, and `handoff.allowed`/`max` are
# not schema fields any more -- a prompt naming any of them tells an agent to
# emit a document that fails validation, which costs a run and its retries
# before the ticket blocks.
RETIRED_PROMPT_VOCABULARY = re.compile(
    r'"outcome"\s*:\s*"(handoff|complete)"'
    r"|handoff\.(allowed|max)"
    r"|\bhand(s|ed)? off\b"
    r"|\bhandoffs?\b",
    re.IGNORECASE,
)


def _prompt_sources() -> list[Path]:
    files = sorted(TASKS_DIR.glob("*/prompts/*.md")) + sorted(TASKS_DIR.glob("*/checklists/*.md"))
    assert files, "task prompts not found"
    return files


def test_no_prompt_teaches_retired_control_vocabulary():
    """Prompts are agent-facing contract, and nothing else checks them.

    The engine never parses a prompt, so a prompt still saying "propose a
    `review` handoff" passes every other check in CI and only fails against a
    real ticket -- the agent emits `outcome: "handoff"`, the schema rejects it,
    the run burns its retries and blocks. That is exactly what happened to
    `implement` and `qa` when the queue cutover landed: the engine-injected
    contract said `queue` while the task prompt said handoff, and the two
    disagreed in the one place no test was looking.

    Same discipline `test_no_task_yml_names_a_concrete_adapter` applies to
    task.yml, applied to the text an agent actually reads.
    """
    offenders = {
        str(path.relative_to(TASKS_DIR)): sorted({m.group(0) for m in
                                                  RETIRED_PROMPT_VOCABULARY.finditer(path.read_text())})
        for path in _prompt_sources()
        if RETIRED_PROMPT_VOCABULARY.search(path.read_text())
    }
    assert not offenders, (
        f"prompts teach vocabulary the control schema rejects: {offenders}. "
        'A run declares `{"outcome": "queue", "queue": [...]}`; an empty queue '
        "means nothing further. Say `queue`/`entry`, never `handoff`."
    )


def test_task_yml_headers_do_not_describe_the_retired_route_model():
    """The same trap one file over: a `task.yml` header comment claiming a task
    is activated by "pointing spec's handoff.allowed at it" sends whoever reads
    it looking for a field that no longer exists."""
    offenders = [
        str(p.relative_to(TASKS_DIR)) for p in sorted(TASKS_DIR.glob("*/task.yml"))
        if RETIRED_PROMPT_VOCABULARY.search(p.read_text())
    ]
    assert not offenders, (
        f"task.yml headers describe the retired handoff model: {offenders}. "
        'A task declares no route; "unwired" now means no prompt queues it.'
    )
