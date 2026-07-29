"""`executor`/`agent-session` port adapter (PD-3, PD-5, D1, user decision:
Copilot everywhere): `copilot-cli` -- runs Claude billed through a GitHub
Copilot seat instead of a direct Anthropic API key.

Settings: `{"workdir": "<parent dir for clones>", "copilot_bin": "copilot",
"model": "claude-sonnet-4.5"}`. Subclasses `ClaudeCodeHeadless` to inherit all
git/PR plumbing (`prepare_worktree`, `collect_outputs`,
`materialize_work_patch`, `apply_patch`, `land_branch`,
`open_draft_pr`/`mark_pr_ready`/`request_reviewers`, `_git`,
`_commit_if_dirty`) unchanged; only `run`, `_child_env`, and `healthcheck`
differ from the parent.

**Tool policy mapping:** taskdef `tools` absent -> `--allow-all-tools`;
Claude's `Read`/`Grep`/`Glob`/`Write`/`Bash` names map to Copilot CLI's
`read`/`write`/`shell` tool kinds when an allowlist is present.

**PD-5 deviation:** unlike the Anthropic-key child, this child process
necessarily holds a GitHub credential (`COPILOT_GITHUB_TOKEN`). Blast radius
is that account's GitHub access; the dedicated bot seat (no repo write
access) reduces it to "model access only". `AGENT_HQ_TOKEN`/`GITHUB_TOKEN`/
`GH_TOKEN` remain forbidden in the child env -- see docs/architecture.md.

**Budget note:** Copilot bills tokens, converted to AI credits at published
per-model rates -- so a run's USD spend is the billed figure, not an
estimate. See `_parse_usage`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from engine.adapters.claude_code_headless import (
    _FORBIDDEN_ENV_KEYS,
    ClaudeCodeHeadless,
    _seconds_until,
)

_ALLOWLIST_KEYS = ("PATH", "HOME", "TMPDIR", "LANG", "TERM", "XDG_CONFIG_HOME")
_TOOL_MAP = {
    "Read": "read",
    "Grep": "read",
    "Glob": "read",
    "Write": "write",
    "Bash": "shell",
}

_USD_PER_CREDIT = 0.01
# ponytail: a piped child emits no escape codes today -- kept because a
# future colorized trailer would fail silently as $0, not loudly.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
_CREDITS = re.compile(r"AI Credits\s+([\d.]+)")
_TRAILER_LINE = re.compile(r"^(Changes|AI Credits|Tokens|Resume)\s")
_TOKENS_UP = re.compile(r"↑\s*([\d.]+)([kKmM]?)")
_TOKENS_DOWN = re.compile(r"↓\s*([\d.]+)([kKmM]?)")
_SUFFIX = {"k": 1_000, "m": 1_000_000}


def _token_count(match: re.Match | None) -> int:
    if match is None:
        return 0
    return int(float(match.group(1)) * _SUFFIX.get(match.group(2).lower(), 1))


_SECRETISH = re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b")
_DETAIL_MAX = 500


def _failure_detail(stderr: str) -> str:
    """Why the child exited nonzero, for the run's `detail`.

    The CLI puts one-line diagnostics here that are otherwise unrecoverable
    -- `Error: Model "x" from --model flag is not available.` is the whole
    explanation for an entire config being wrong, and without this the run
    records a bare `failure`. Trailer lines are dropped (they describe a run
    that worked, not one that failed) and anything token-shaped is redacted:
    `detail` reaches the state ledger and escalation comments, and the child
    holds a real `COPILOT_GITHUB_TOKEN`.
    """
    lines = [
        line.strip()
        for line in _ANSI.sub("", stderr or "").splitlines()
        if line.strip() and not _TRAILER_LINE.match(line.strip())
    ]
    detail = " ".join(lines)[-_DETAIL_MAX:]
    return _SECRETISH.sub("<redacted>", detail) or "agent exited nonzero without output"


def _parse_usage(blob: str) -> tuple[float, int | None]:
    """`(cost_usd, tokens)` from the CLI's end-of-session trailer, which it
    writes to **stderr** (stdout carries only the answer text) whenever `-s`
    is absent:

        Changes    +0 -0
        AI Credits 0.46 (16s)
        Tokens     ↑ 17.3k (1.7k cached) • ↓ 310 (256 reasoning)

    1 AI credit = $0.01, and GitHub prices the underlying input/cached/output
    tokens per model (docs: copilot/reference/copilot-billing/models-and-pricing),
    so the credits line is what the seat is actually billed. Cost comes from
    that line rather than from token math because the token counts are
    printed rounded (`17.3k`) while the credits are not.

    A missing trailer (timeout, kill, or a future format change) yields
    `0.0`. That understates spend, but the alternative -- reporting
    `usage_known: False` -- makes `_handle_failure` block the ticket on every
    transient failure instead of retrying it (`engine/engine.py`), which is a
    worse trade for an unmetered edge case than a $0 row is.
    """
    blob = _ANSI.sub("", blob)
    credits = _CREDITS.search(blob)
    cost_usd = round(float(credits.group(1)) * _USD_PER_CREDIT, 4) if credits else 0.0
    tokens = _token_count(_TOKENS_UP.search(blob)) + _token_count(_TOKENS_DOWN.search(blob))
    return cost_usd, tokens or None


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
        # No `-s`: silent mode suppresses the session trailer `_parse_usage`
        # reads the run's spend out of. It only ever wrote to stderr, which
        # nothing else here consumes.
        argv = [
            self.copilot_bin,
            "-p",
            prompt,
            "--no-ask-user",
            "--model",
            self.model,
        ]
        if not tools:
            argv.append("--allow-all-tools")
        else:
            for tool in dict.fromkeys(_TOOL_MAP[name] for name in tools if name in _TOOL_MAP):
                argv.append(f"--allow-tool={tool}")

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
            stdout, stderr = proc.communicate(timeout=timeout)
            outcome = "success" if proc.returncode == 0 else "failure"
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            outcome = "timeout"

        cost_usd, tokens = _parse_usage((stdout or "") + (stderr or ""))
        # Task 12 normalization: no `session_id` (not part of the
        # transported contract) and `timeout` maps to `failure` + `detail`
        # (schemas/execute-result.schema.json only knows success/failure;
        # collect already treats them identically for failure/retry
        # accounting, so this is a schema fix, not a behavior change).
        result = {
            "outcome": "failure" if outcome == "timeout" else outcome,
            "cost_usd": cost_usd,
            "tokens": tokens,
            "usage_known": True,
        }
        if outcome == "timeout":
            result["detail"] = "execution timed out before the deadline"
        elif outcome == "failure":
            result["detail"] = _failure_detail(stderr)
        result_path = worktree / ".agent-hq" / "execute-result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        return result

    def healthcheck(self) -> bool:
        try:
            result = subprocess.run(
                [self.copilot_bin, "version"], capture_output=True, text=True, timeout=10, check=False
)
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
