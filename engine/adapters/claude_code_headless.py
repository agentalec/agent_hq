"""`executor`/`agent-session` port adapter (PD-3, PD-5, D1): `claude-code-headless`.

Settings: `{"workdir": "<parent dir for clones>", "claude_bin": "claude"}`.
No checkpoint/resume in P0 (D1): every run starts from a fresh clone: a
killed session is retried from scratch by the dispatcher, not resumed here.
`start`/`result` are thin stubs -- the runner drives `prepare_worktree`/
`run`/`collect_outputs`/`materialize_work_patch` (execute) and
`prepare_worktree`/`apply_patch`/`land_branch` (collect) directly against
this same adapter instance; there is no separate async dispatch step for the
in-process claude-code-headless executor.

Isolated-job model (hardening plan Task 12): `prepare_worktree` +
`materialize_work_patch` run in execute's credential-free job (a plain clone
of a public repo needs no credential -- PD-5); `apply_patch` + `land_branch`
run only in collect's credentialed job -- this adapter never pushes from
execute.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from engine.adapters._github import (
    GitHubClient,
    git_credential_args,
    open_draft_pr,
    request_reviewers,
)
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
    deadline = datetime.strptime(deadline_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return (deadline - datetime.now(UTC)).total_seconds()


def _result_is_error(stdout: str) -> bool:
    try:
        return bool(json.loads(stdout).get("is_error"))
    except (json.JSONDecodeError, AttributeError):
        return False


def _parse_execute_result(outcome: str, stdout: str) -> dict:
    """Build `schemas/execute-result.schema.json`-shaped output directly
    (Task 12 normalization): no `session_id` (not part of the transported
    contract -- collect validates against this schema, which forbids it),
    and a `timeout` outcome maps to `failure` + a `detail` (the schema only
    knows `success`/`failure`; collect's own failure/retry accounting
    already treats `timeout` identically to `failure`, so this is a schema
    fix, not a behavior change)."""
    cost_usd = None
    tokens = None
    usage_known = False
    try:
        data = json.loads(stdout) if stdout else None
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        usage = data.get("usage")
        cost = data.get("total_cost_usd")
        if isinstance(usage, dict) and cost is not None:
            tokens = sum(v for v in usage.values() if isinstance(v, int) and not isinstance(v, bool))
            cost_usd = cost
            usage_known = True
    result = {"outcome": outcome, "cost_usd": cost_usd, "tokens": tokens, "usage_known": usage_known}
    if outcome == "timeout":
        result["outcome"] = "failure"
        result["detail"] = "execution timed out before the deadline"
    return result


class ClaudeCodeHeadless:
    def __init__(self, settings: dict):
        self.settings = settings
        self.workdir = Path(settings.get("workdir", "."))
        self.claude_bin = settings.get("claude_bin", "claude")

    # -- shared git plumbing -------------------------------------------------

    def _git(self, *args: str, cwd: str | Path | None = None) -> str:
        result = subprocess.run(
            ["git", *git_credential_args(), *args], cwd=cwd, capture_output=True, text=True, check=False
)
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout

    def _commit_if_dirty(self, cwd: str | Path, message: str) -> None:
        self._git("add", "-A", cwd=cwd)
        diff = subprocess.run(["git", "-C", str(cwd), "diff", "--cached", "--quiet"], check=False)
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

    def resolve_ref(self, repo: str, ref: str) -> str:
        """Resolve a branch name to its immutable commit SHA via a
        lightweight `git ls-remote` -- no clone needed (prepare has no
        work-repo clone, Task 12). Called once at prepare so execute and
        collect, which run in separate clones, operate on a pinned SHA
        rather than a mutable branch name that could move between phases."""
        out = self._git("ls-remote", _clone_url(repo), f"refs/heads/{ref}")
        line = out.strip().splitlines()[0] if out.strip() else ""
        if not line:
            raise RuntimeError(f"ref not found: {repo}@refs/heads/{ref}")
        return line.split()[0]

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

    def materialize_work_patch(self, worktree: str | Path, exclude_paths: list[str]) -> str:
        """Diff the agent's committed+uncommitted changes against this run's
        base tag, excluding `exclude_paths` (the declared outputs and
        restored input artifacts -- neither is work-repo code) and
        `.agent-hq/`. This is the ONLY payload that ever reaches the target
        repo -- Task 12: execute holds no push credential, so it never
        pushes directly; it hands this patch to collect, which applies it
        to a fresh, credentialed clone."""
        worktree = Path(worktree)
        self._commit_if_dirty(worktree, "agent-hq: work")
        base = self._git("rev-parse", _BASE_TAG, cwd=worktree).strip()
        tip = self._git("rev-parse", "work", cwd=worktree).strip()
        excludes = [f":!{p}" for p in exclude_paths] + [":!.agent-hq"]
        # --binary: without it git emits "Binary files differ" and `git apply`
        # on the collect side rejects the patch -- any PNG/font/fixture the
        # agent adds (QA screenshots, notably) would fail the run.
        return self._git("diff", "--binary", base, tip, "--", ".", *excludes, cwd=worktree)

    def apply_patch(self, worktree: str | Path, patch_text: str) -> None:
        """Apply a transported work patch to a fresh landing clone (collect,
        Task 12). Raises (via `_git`) if it doesn't apply cleanly -- a patch
        that fails to apply fails the run, it is never silently dropped."""
        worktree = Path(worktree)
        patch_path = worktree / ".agent-hq-work.patch"
        patch_path.write_text(patch_text)
        try:
            # Bare filename: git runs with cwd=worktree, and a relative
            # worktree path (run-phases.sh) would otherwise double up.
            self._git("apply", ".agent-hq-work.patch", cwd=worktree)
        finally:
            patch_path.unlink(missing_ok=True)

    def _parent_sha(self, worktree: str | Path, ref: str) -> str | None:
        try:
            return self._git("rev-parse", f"{ref}^", cwd=worktree).strip()
        except RuntimeError:
            return None

    def land_branch(
        self, run_id: str, worktree: str | Path, branch: str, base_branch: str, message: str
    ) -> dict:
        """Commit the applied patch (if dirty) under `message` and
        fast-forward-push onto the ticket's stable `branch` (created from
        `base_branch` on the first push -- Task 12). A plain fast-forward
        push IS the lease: every attempt is built on the branch's last
        recorded head, so a rejection means someone moved it since. On
        rejection, fetch the remote tip and compare its tree/parent to this
        attempt's own -- identical content from a retried (fresh-timestamp)
        attempt is adopted (`landed: True`, the remote head); a real
        divergence is reported (`landed: False`) for the caller to block.

        `message` comes from the caller, not from here: this is the commit a
        work-repo reader sees, and the adapter knows only a run id."""
        worktree = Path(worktree)
        self._commit_if_dirty(worktree, message)
        head = self._git("rev-parse", "HEAD", cwd=worktree).strip()
        push = subprocess.run(
            ["git", "-C", str(worktree), *git_credential_args(), "push", "origin",
             f"HEAD:refs/heads/{branch}"],
            capture_output=True, text=True, check=False
)
        if push.returncode == 0:
            return {"landed": True, "head": head}

        self._git("fetch", "origin", branch, cwd=worktree)
        remote_head = self._git("rev-parse", "FETCH_HEAD", cwd=worktree).strip()
        remote_tree = self._git("rev-parse", "FETCH_HEAD^{tree}", cwd=worktree).strip()
        our_tree = self._git("rev-parse", "HEAD^{tree}", cwd=worktree).strip()
        if remote_tree == our_tree and self._parent_sha(worktree, "FETCH_HEAD") == self._parent_sha(
            worktree, "HEAD"
        ):
            return {"landed": True, "head": remote_head}
        return {"landed": False, "head": head, "remote_head": remote_head}

    # -- PR lifecycle (repo-side effects owned by this adapter, same as
    # land_branch's push -- runner.py calls these through the agent-session
    # port so swapping the executor swaps PR behavior too) ----

    def open_draft_pr(self, repo: str, branch: str, base: str, title: str, body: str) -> str:
        pr = open_draft_pr(GitHubClient(), repo, branch, base, title, body)
        return f"{repo}#{pr['number']}"

    def mark_pr_ready(self, pr_ref: str) -> None:
        repo, _, number = pr_ref.rpartition("#")
        client = GitHubClient()
        pr = client.get(f"/repos/{repo}/pulls/{number}")
        if not pr.get("draft"):
            return
        result = client.post(
            "/graphql",
            json={
                "query": (
                    "mutation($id:ID!){markPullRequestReadyForReview("
                    "input:{pullRequestId:$id}){pullRequest{isDraft}}}"
                ),
                "variables": {"id": pr["node_id"]},
            },
        )
        if result.get("errors"):
            raise RuntimeError(f"GitHub markPullRequestReadyForReview failed: {result['errors']}")

    def pr_state(self, pr_ref: str) -> dict:
        """Whether a work PR is still open, and if closed whether it was
        merged -- what the sweep needs to resolve an AWAITING_MERGE ticket
        (`engine.engine.resolve_awaiting_merge`). Closed-unmerged is a human
        declining the work, so the caller must be able to tell it from a
        merge; `state` alone cannot.
        ponytail: no helper in `_github.py` for a one-line GET with exactly
        one caller -- same shape as `mark_pr_ready` right above."""
        repo, _, number = pr_ref.rpartition("#")
        pr = GitHubClient().get(f"/repos/{repo}/pulls/{number}")
        return {"state": pr["state"], "merged": bool(pr.get("merged_at"))}

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
                [self.claude_bin, "--version"], capture_output=True, text=True, timeout=10, check=False
)
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
