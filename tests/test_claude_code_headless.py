import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.adapters import claude_code_headless as cch
from engine.adapters.claude_code_headless import ClaudeCodeHeadless

FUTURE_DEADLINE = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def _make_origin(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "--initial-branch", "main", str(origin))
    seed = tmp_path / "_seed"
    _git("clone", str(origin), str(seed))
    _git("config", "user.email", "seed@example.com", cwd=seed)
    _git("config", "user.name", "Seed", cwd=seed)
    (seed / "existing.txt").write_text("base\n")
    _git("add", "-A", cwd=seed)
    _git("commit", "-m", "base", cwd=seed)
    _git("push", "-u", "origin", "main", cwd=seed)
    return origin


# -- _child_env ---------------------------------------------------------------


def test_child_env_excludes_secrets_includes_anthropic_key(monkeypatch):
    monkeypatch.setenv("AGENT_HQ_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_TOKEN", "tok2")
    monkeypatch.setenv("GH_TOKEN", "tok3")
    monkeypatch.setenv("SOME_SECRET", "leak-me-not")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xyz")

    env = cch._child_env()

    assert "AGENT_HQ_TOKEN" not in env
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env
    assert "SOME_SECRET" not in env
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-xyz"


# -- run: argv and subprocess handling ----------------------------------------


class FakeProc:
    def __init__(self, stdout="", returncode=0, raise_timeout=False):
        self._stdout = stdout
        self.returncode = returncode
        self._raise_timeout = raise_timeout
        self.killed = False
        self.communicate_calls = []

    def communicate(self, input=None, timeout=None):
        self.communicate_calls.append(input)
        if self._raise_timeout and len(self.communicate_calls) == 1:
            raise subprocess.TimeoutExpired(cmd="claude", timeout=timeout)
        return self._stdout, ""

    def kill(self):
        self.killed = True


def _install_fake_popen(monkeypatch, proc: FakeProc):
    calls = []

    def fake_popen(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        return proc

    monkeypatch.setattr(cch.subprocess, "Popen", fake_popen)
    return calls


def test_run_argv_has_disallowed_tools_and_no_allowed_tools_when_none_given(monkeypatch, tmp_path):
    proc = FakeProc(stdout=json.dumps({"session_id": "s1", "total_cost_usd": 0.1, "usage": {}}))
    calls = _install_fake_popen(monkeypatch, proc)
    executor = ClaudeCodeHeadless({"claude_bin": "claude"})

    executor.run({"prompt": "do stuff", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    argv = calls[0]["argv"]
    assert argv[0] == "claude"
    assert "--disallowedTools" in argv
    assert argv[argv.index("--disallowedTools") + 1] == "WebFetch,WebSearch"
    assert "--allowedTools" not in argv


def test_run_argv_includes_allowed_tools_when_given(monkeypatch, tmp_path):
    proc = FakeProc(stdout=json.dumps({"session_id": "s1", "total_cost_usd": 0.1, "usage": {}}))
    calls = _install_fake_popen(monkeypatch, proc)
    executor = ClaudeCodeHeadless({})

    executor.run({"prompt": "do stuff", "worktree": str(tmp_path)}, ["Bash", "Read"], FUTURE_DEADLINE)

    argv = calls[0]["argv"]
    assert "--allowedTools" in argv
    assert argv[argv.index("--allowedTools") + 1] == "Bash,Read"


def test_run_timeout_kills_process_and_returns_timeout_outcome(monkeypatch, tmp_path):
    proc = FakeProc(raise_timeout=True)
    _install_fake_popen(monkeypatch, proc)
    executor = ClaudeCodeHeadless({})

    result = executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    assert result["outcome"] == "timeout"
    assert proc.killed is True
    assert result["usage_known"] is False
    assert result["cost_usd"] is None
    assert result["tokens"] is None


def test_run_success_parses_usage_and_writes_result_file(monkeypatch, tmp_path):
    stdout = json.dumps(
        {
            "session_id": "sess-42",
            "total_cost_usd": 0.0456,
            "result": "done",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
    )
    proc = FakeProc(stdout=stdout, returncode=0)
    _install_fake_popen(monkeypatch, proc)
    executor = ClaudeCodeHeadless({})

    result = executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    assert result["outcome"] == "success"
    assert result["session_id"] == "sess-42"
    assert result["cost_usd"] == 0.0456
    assert result["tokens"] == 150
    assert result["usage_known"] is True

    written = json.loads((tmp_path / ".agent-hq" / "execute-result.json").read_text())
    assert written == result


def test_run_nonzero_exit_is_failure_outcome(monkeypatch, tmp_path):
    proc = FakeProc(stdout=json.dumps({"session_id": "s", "total_cost_usd": 0.1, "usage": {}}),
                     returncode=1)
    _install_fake_popen(monkeypatch, proc)
    executor = ClaudeCodeHeadless({})

    result = executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    assert result["outcome"] == "failure"


def test_run_garbage_stdout_usage_unknown(monkeypatch, tmp_path):
    proc = FakeProc(stdout="not json at all", returncode=0)
    _install_fake_popen(monkeypatch, proc)
    executor = ClaudeCodeHeadless({})

    result = executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    assert result["usage_known"] is False
    assert result["cost_usd"] is None
    assert result["tokens"] is None
    assert result["session_id"] is None


# -- collect_outputs ------------------------------------------------------------


def test_collect_outputs_raises_listing_missing(tmp_path):
    (tmp_path / "present.txt").write_text("x")
    executor = ClaudeCodeHeadless({})

    with pytest.raises(RuntimeError, match="missing.txt"):
        executor.collect_outputs(tmp_path, ["present.txt", "missing.txt"])


def test_collect_outputs_returns_declared_when_all_present(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.txt").write_text("y")
    executor = ClaudeCodeHeadless({})

    assert executor.collect_outputs(tmp_path, ["a.txt", "b.txt"]) == ["a.txt", "b.txt"]


# -- prepare_worktree + build_pr_branch (real git) ------------------------------


def test_prepare_worktree_and_build_pr_branch_materialize_committed_and_uncommitted_work(
    monkeypatch, tmp_path
):
    origin = _make_origin(tmp_path)
    base_commit = _git("rev-parse", "main", cwd=tmp_path / "_seed").strip()
    monkeypatch.setattr(cch, "_clone_url", lambda repo: str(origin))

    executor = ClaudeCodeHeadless({"workdir": str(tmp_path / "work")})
    worktree = executor.prepare_worktree("run-1", "o/r", base_commit)

    assert worktree == tmp_path / "work" / "_target" / "run-1"
    assert worktree.exists()

    # agent commits a change...
    (worktree / "existing.txt").write_text("committed change\n")
    _git("add", "-A", cwd=worktree)
    _git("commit", "-m", "agent commit", cwd=worktree)
    # ...leaves an uncommitted edit...
    (worktree / "new_uncommitted.txt").write_text("uncommitted\n")
    # ...and drops runner metadata that must never reach the PR branch.
    (worktree / ".agent-hq").mkdir()
    (worktree / ".agent-hq" / "execute-result.json").write_text("{}")

    output_commit = executor.build_pr_branch("run-1", worktree, base_commit)

    assert (worktree / "existing.txt").read_text() == "committed change\n"
    assert (worktree / "new_uncommitted.txt").read_text() == "uncommitted\n"
    assert not (worktree / ".agent-hq").exists()

    branch = _git("rev-parse", "agent-hq/run-1", cwd=worktree).strip()
    assert branch == output_commit

    # pushed to origin -- fresh clone shows the same branch and content
    check = tmp_path / "check"
    _git("clone", "--branch", "agent-hq/run-1", str(origin), str(check))
    assert _git("rev-parse", "HEAD", cwd=check).strip() == output_commit
    assert (check / "existing.txt").read_text() == "committed change\n"
    assert (check / "new_uncommitted.txt").read_text() == "uncommitted\n"
    assert not (check / ".agent-hq").exists()


def test_build_pr_branch_uses_base_tag_when_base_commit_none(monkeypatch, tmp_path):
    origin = _make_origin(tmp_path)
    monkeypatch.setattr(cch, "_clone_url", lambda repo: str(origin))

    executor = ClaudeCodeHeadless({"workdir": str(tmp_path / "work")})
    worktree = executor.prepare_worktree("run-2", "o/r", None)
    base_tip = _git("rev-parse", "HEAD~0", cwd=worktree).strip()

    (worktree / "existing.txt").write_text("changed\n")
    _git("add", "-A", cwd=worktree)
    _git("commit", "-m", "agent commit", cwd=worktree)

    executor.build_pr_branch("run-2", worktree, None)

    parent = _git("rev-parse", "agent-hq/run-2^", cwd=worktree).strip()
    assert parent == base_tip


# -- healthcheck ----------------------------------------------------------------


def test_healthcheck_false_when_binary_missing():
    executor = ClaudeCodeHeadless({"claude_bin": "definitely-not-a-real-binary-xyz"})
    assert executor.healthcheck() is False
