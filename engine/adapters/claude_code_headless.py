"""`executor`/`agent-session` port adapter (PD-3, PD-5, D1): `claude-code-headless`.

Settings: `{"workdir": "<parent dir for clones>", "claude_bin": "claude"}`.
No checkpoint/resume in P0 (D1): every run starts from a fresh clone: a
killed session is retried from scratch by the dispatcher, not resumed here.
`start`/`result` are thin stubs -- the runner (Task 13) drives
`prepare_worktree`/`run`/`collect_outputs`/`build_pr_branch` directly against
this same adapter instance; there is no separate async dispatch step for the
in-process claude-code-headless executor.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from engine.adapters._github import GitHubClient, git_credential_args, open_draft_pr, request_reviewers
from engine.models import TaskRun

_BOT_NAME = "agent-hq[bot]"
_BOT_EMAIL = "agent-hq@users.noreply.github.com"
_FORBIDDEN_ENV_KEYS = ("AGENT_HQ_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
_BASE_TAG = "agent-hq-base"


def _clone_url(repo: str) -> str:
    return f"https://github.com/{repo}.git"


def _child_env() -> dict:
    """Allowlisted child env (PD-5): built key-by-key from scratch, never by
    copying and deleting from `os.environ`, so a new secret landing in the
    parent env can't leak into the agent process by omission."""
    env = {}
    for key in ("PATH", "HOME", "TMPDIR", "LANG", "TERM"):
        if key in os.environ:
            env[key] = os.environ[key]
    for key, value in os.environ.items():
        if key.startswith("LC_"):
            env[key] = value
    for key in ("CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY"):
        if key in os.environ:
            env[key] = os.environ[key]
    # ponytail: structurally impossible with the allowlist above -- kept as
    # the documented boundary, not as real defense.
    assert not any(key in env for key in _FORBIDDEN_ENV_KEYS), (
        "credential leaked into agent-session child env"
    )
    return env


def _seconds_until(deadline_iso: str) -> float:
    deadline = datetime.strptime(deadline_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (deadline - datetime.now(timezone.utc)).total_seconds()


def _result_is_error(stdout: str) -> bool:
    try:
        return bool(json.loads(stdout).get("is_error"))
    except (json.JSONDecodeError, AttributeError):
        return False


def _parse_execute_result(outcome: str, stdout: str) -> dict:
    cost_usd = None
    tokens = None
    session_id = None
    usage_known = False
    try:
        data = json.loads(stdout) if stdout else None
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        session_id = data.get("session_id")
        usage = data.get("usage")
        cost = data.get("total_cost_usd")
        if isinstance(usage, dict) and cost is not None:
            tokens = sum(v for v in usage.values() if isinstance(v, int) and not isinstance(v, bool))
            cost_usd = cost
            usage_known = True
    return {
        "outcome": outcome,
        "cost_usd": cost_usd,
        "tokens": tokens,
        "usage_known": usage_known,
        "session_id": session_id,
    }


class ClaudeCodeHeadless:
    def __init__(self, settings: dict):
        self.settings = settings
        self.workdir = Path(settings.get("workdir", "."))
        self.claude_bin = settings.get("claude_bin", "claude")

    # -- shared git plumbing -------------------------------------------------

    def _git(self, *args: str, cwd: str | Path | None = None) -> str:
        result = subprocess.run(
            ["git", *git_credential_args(), *args], cwd=cwd, capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout

    def _commit_if_dirty(self, cwd: str | Path, message: str) -> None:
        self._git("add", "-A", cwd=cwd)
        diff = subprocess.run(["git", "-C", str(cwd), "diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            return
        self._git("commit", "-m", message, cwd=cwd)

    # -- agent-session --------------------------------------------------------

    def prepare_worktree(self, run_id: str, repo: str, base_commit: str | None) -> Path:
        worktree = self.workdir / "_target" / run_id
        worktree.parent.mkdir(parents=True, exist_ok=True)
        self._git("clone", _clone_url(repo), str(worktree))
        if base_commit:
            self._git("checkout", base_commit, cwd=worktree)
        self._git("checkout", "-b", "work", cwd=worktree)
        self._git("tag", _BASE_TAG, cwd=worktree)
        self._git("config", "user.name", _BOT_NAME, cwd=worktree)
        self._git("config", "user.email", _BOT_EMAIL, cwd=worktree)
        return worktree

    def run(self, bundle: dict, tools: list[str], deadline_iso: str) -> dict:
        prompt = bundle["prompt"]
        worktree = Path(bundle["worktree"])
        argv = [
            self.claude_bin,
            "-p",
            "--output-format",
            "json",
            "--disallowedTools",
            "WebFetch,WebSearch",
        ]
        if tools:
            argv += ["--allowedTools", ",".join(tools)]

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
            stdout, _stderr = proc.communicate(input=prompt, timeout=timeout)
            outcome = "success" if proc.returncode == 0 else "failure"
            # Defense in depth: a CLI result reporting is_error is a failure
            # even when the exit code says otherwise.
            if outcome == "success" and _result_is_error(stdout):
                outcome = "failure"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            outcome = "timeout"
            stdout = ""

        result = _parse_execute_result(outcome, stdout)
        result_path = worktree / ".agent-hq" / "execute-result.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, indent=2) + "\n")
        return result

    def collect_outputs(self, worktree: str | Path, declared: list[str]) -> list[str]:
        worktree = Path(worktree)
        missing = [path for path in declared if not (worktree / path).exists()]
        if missing:
            raise RuntimeError(f"missing declared artifacts: {missing}")
        return list(declared)

    def build_pr_branch(self, run_id: str, worktree: str | Path, base_commit: str | None) -> str:
        worktree = Path(worktree)
        self._commit_if_dirty(worktree, "agent-hq: uncommitted work")
        work_tip = self._git("rev-parse", "work", cwd=worktree).strip()
        base = base_commit or self._git("rev-parse", _BASE_TAG, cwd=worktree).strip()

        branch = f"agent-hq/{run_id}"
        self._git("checkout", "-B", branch, base, cwd=worktree)
        self._git("restore", "--source", work_tip, "--", ".", ":!.agent-hq", cwd=worktree)
        self._commit_if_dirty(worktree, f"agent-hq: run {run_id}")
        self._git("push", "-u", "origin", branch, cwd=worktree)
        return self._git("rev-parse", branch, cwd=worktree).strip()

    # -- PR lifecycle (repo-side effects owned by this adapter, same as
    # build_pr_branch's push -- runner.py calls these through the
    # agent-session port so swapping the executor swaps PR behavior too) ----

    def open_draft_pr(self, repo: str, branch: str, base: str, title: str, body: str) -> str:
        pr = open_draft_pr(GitHubClient(), repo, branch, base, title, body)
        return f"{repo}#{pr['number']}"

    def mark_pr_ready(self, pr_ref: str) -> None:
        repo, _, number = pr_ref.rpartition("#")
        GitHubClient().patch(f"/repos/{repo}/pulls/{number}", json={"draft": False})

    def request_reviewers(self, pr_ref: str, members: list[str]) -> None:
        repo, _, number = pr_ref.rpartition("#")
        request_reviewers(GitHubClient(), repo, number, members)

    # -- executor (thin passthrough; see module docstring) --------------------

    def start(self, run_ctx: TaskRun) -> None:
        pass

    def result(self, run_ctx: TaskRun) -> dict | None:
        return None

    # -- shared -----------------------------------------------------------

    def healthcheck(self) -> bool:
        try:
            result = subprocess.run(
                [self.claude_bin, "--version"], capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
