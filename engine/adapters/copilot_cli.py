"""`executor`/`agent-session` port adapter (PD-3, PD-5, D1, user decision:
Copilot everywhere): `copilot-cli` -- runs Claude billed through a GitHub
Copilot seat instead of a direct Anthropic API key.

Settings: `{"workdir": "<parent dir for clones>", "copilot_bin": "copilot",
"model": "claude-sonnet-4.5"}`. Subclasses `ClaudeCodeHeadless` to inherit all
git/PR plumbing (`prepare_worktree`, `build_pr_branch`, `collect_outputs`,
`open_draft_pr`/`mark_pr_ready`/`request_reviewers`, `_git`,
`_commit_if_dirty`) unchanged; only `run`, `_child_env`, and `healthcheck`
differ from the parent.

**Tool policy mapping:** Claude tool names (`Read`/`Grep`/`Bash`/...) don't
exist in Copilot CLI's vocabulary, so there's no allowlist flag to translate
them into. Instead: taskdef `tools` absent -> `--allow-all-tools`; taskdef
`tools` present -> no tool flags at all -- Copilot CLI denies any tool use it
can't get interactive confirmation for, and `--no-ask-user` suppresses that
confirmation, so an unapproved tool is denied by construction. This is a
deny-by-default read-only mode, the honest equivalent for a task (e.g.
`review`) that must stay read-only.

**PD-5 deviation:** unlike the Anthropic-key child, this child process
necessarily holds a GitHub credential (`COPILOT_GITHUB_TOKEN`). Blast radius
is that account's GitHub access; the dedicated bot seat (no repo write
access) reduces it to "model access only". `AGENT_HQ_TOKEN`/`GITHUB_TOKEN`/
`GH_TOKEN` remain forbidden in the child env -- see docs/architecture.md.

**Budget note:** Copilot billing is premium-request subscription metering,
not per-run USD -- see `run()`.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from engine.adapters.claude_code_headless import (
    _FORBIDDEN_ENV_KEYS,
    ClaudeCodeHeadless,
    _seconds_until,
)

_ALLOWLIST_KEYS = ("PATH", "HOME", "TMPDIR", "LANG", "TERM", "XDG_CONFIG_HOME")


def _child_env() -> dict:
    """Allowlisted child env (PD-5), same from-scratch construction as the
    parent adapter, plus `COPILOT_GITHUB_TOKEN` instead of
    `ANTHROPIC_API_KEY` -- no Anthropic key reaches this child."""
    env = {}
    for key in _ALLOWLIST_KEYS:
        if key in os.environ:
            env[key] = os.environ[key]
    for key, value in os.environ.items():
        if key.startswith("LC_"):
            env[key] = value
    if "COPILOT_GITHUB_TOKEN" in os.environ:
        env["COPILOT_GITHUB_TOKEN"] = os.environ["COPILOT_GITHUB_TOKEN"]
    # ponytail: structurally impossible with the allowlist above -- kept as
    # the documented boundary, not as real defense.
    assert not any(key in env for key in _FORBIDDEN_ENV_KEYS), (
        "credential leaked into agent-session child env"
    )
    return env


class CopilotCli(ClaudeCodeHeadless):
    def __init__(self, settings: dict):
        super().__init__(settings)
        self.copilot_bin = settings.get("copilot_bin", "copilot")
        self.model = settings.get("model", "claude-sonnet-4.5")

    def run(self, bundle: dict, tools: list[str], deadline_iso: str) -> dict:
        prompt = bundle["prompt"]
        worktree = Path(bundle["worktree"])
        argv = [
            self.copilot_bin,
            "-p",
            prompt,
            "-s",
            "--no-ask-user",
            "--model",
            self.model,
        ]
        if not tools:
            argv.append("--allow-all-tools")

        timeout = max(1, _seconds_until(deadline_iso))
        proc = subprocess.Popen(
            argv,
            cwd=worktree,
            env=_child_env(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            proc.communicate(timeout=timeout)
            outcome = "success" if proc.returncode == 0 else "failure"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            outcome = "timeout"

        # ponytail: premium-request billing; USD caps don't bind -- see docs.
        result = {
            "outcome": outcome,
            "cost_usd": 0.0,
            "tokens": None,
            "usage_known": True,
            "session_id": None,
        }
        result_path = worktree / ".agent-hq" / "execute-result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        return result

    def healthcheck(self) -> bool:
        try:
            result = subprocess.run(
                [self.copilot_bin, "--version"], capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
