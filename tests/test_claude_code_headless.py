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


def test_run_timeout_maps_to_failure_with_detail(monkeypatch, tmp_path):
    """Task 12 normalization: schemas/execute-result.schema.json only knows
    success/failure -- a timeout is reported as a schema-valid failure with
    a `detail`, not a bare "timeout" outcome."""
    proc = FakeProc(raise_timeout=True)
    _install_fake_popen(monkeypatch, proc)
    executor = ClaudeCodeHeadless({})

    result = executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    assert result["outcome"] == "failure"
    assert "timed out" in result["detail"]
    assert proc.killed is True
    assert result["usage_known"] is False
    assert result["cost_usd"] is None
    assert result["tokens"] is None
    assert "session_id" not in result


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
    assert "session_id" not in result  # Task 12: not part of the transported contract
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
    assert "session_id" not in result


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


# -- prepare_worktree (real git) ------------------------------------------------


def test_prepare_worktree_checks_out_base_commit_and_tags_it(monkeypatch, tmp_path):
    origin = _make_origin(tmp_path)
    base_commit = _git("rev-parse", "main", cwd=tmp_path / "_seed").strip()
    monkeypatch.setattr(cch, "_clone_url", lambda repo: str(origin))

    executor = ClaudeCodeHeadless({"workdir": str(tmp_path / "work")})
    worktree = executor.prepare_worktree("run-1", "o/r", base_commit)

    assert worktree == tmp_path / "work" / "_target" / "run-1"
    assert worktree.exists()
    assert _git("rev-parse", "agent-hq-base", cwd=worktree).strip() == base_commit


# -- materialize_work_patch / apply_patch / land_branch (Task 12, real git) -----


def test_materialize_work_patch_excludes_declared_and_agent_hq(monkeypatch, tmp_path):
    origin = _make_origin(tmp_path)
    base_commit = _git("rev-parse", "main", cwd=tmp_path / "_seed").strip()
    monkeypatch.setattr(cch, "_clone_url", lambda repo: str(origin))

    executor = ClaudeCodeHeadless({"workdir": str(tmp_path / "work")})
    worktree = executor.prepare_worktree("run-1", "o/r", base_commit)

    # code the agent wrote (must be in the patch)...
    (worktree / "code.py").write_text("print('hi')\n")
    # ...a declared/input artifact (must be EXCLUDED -- ledger-only, never
    # work-repo code)...
    (worktree / "specs" / "7").mkdir(parents=True)
    (worktree / "specs" / "7" / "spec.md").write_text("the spec\n")
    # ...and runner metadata (always excluded).
    (worktree / ".agent-hq").mkdir()
    (worktree / ".agent-hq" / "execute-result.json").write_text("{}")

    patch = executor.materialize_work_patch(worktree, ["specs/7/spec.md"])

    assert "code.py" in patch
    assert "spec.md" not in patch
    assert ".agent-hq" not in patch


def test_apply_patch_applies_cleanly_on_a_fresh_clone(monkeypatch, tmp_path):
    origin = _make_origin(tmp_path)
    base_commit = _git("rev-parse", "main", cwd=tmp_path / "_seed").strip()
    monkeypatch.setattr(cch, "_clone_url", lambda repo: str(origin))

    executor = ClaudeCodeHeadless({"workdir": str(tmp_path / "work")})
    source = executor.prepare_worktree("run-1", "o/r", base_commit)
    (source / "code.py").write_text("print('hi')\n")
    patch = executor.materialize_work_patch(source, [])

    landing = executor.prepare_worktree("run-1-collect", "o/r", base_commit)
    executor.apply_patch(landing, patch)

    assert (landing / "code.py").read_text() == "print('hi')\n"
    assert not (landing / ".agent-hq-work.patch").exists()


def test_apply_patch_raises_on_a_patch_that_does_not_apply(monkeypatch, tmp_path):
    origin = _make_origin(tmp_path)
    base_commit = _git("rev-parse", "main", cwd=tmp_path / "_seed").strip()
    monkeypatch.setattr(cch, "_clone_url", lambda repo: str(origin))

    executor = ClaudeCodeHeadless({"workdir": str(tmp_path / "work")})
    landing = executor.prepare_worktree("run-2", "o/r", base_commit)

    with pytest.raises(RuntimeError):
        executor.apply_patch(landing, "not a valid patch at all\n")


def test_land_branch_creates_branch_then_fast_forwards_a_later_attempt(monkeypatch, tmp_path):
    origin = _make_origin(tmp_path)
    base_commit = _git("rev-parse", "main", cwd=tmp_path / "_seed").strip()
    monkeypatch.setattr(cch, "_clone_url", lambda repo: str(origin))
    executor = ClaudeCodeHeadless({"workdir": str(tmp_path / "work")})

    first = executor.prepare_worktree("run-1", "o/r", base_commit)
    (first / "a.py").write_text("a\n")
    landed_1 = executor.land_branch("run-1", first, "agent-hq/7", "main")
    assert landed_1["landed"] is True

    check = tmp_path / "check-1"
    _git("clone", "--branch", "agent-hq/7", str(origin), str(check))
    assert _git("rev-parse", "HEAD", cwd=check).strip() == landed_1["head"]
    assert (check / "a.py").read_text() == "a\n"

    # A later task/rework attempt bases on the recorded head (Task 12) --
    # its push is a plain fast-forward onto the same branch.
    second = executor.prepare_worktree("run-2", "o/r", landed_1["head"])
    (second / "b.py").write_text("b\n")
    landed_2 = executor.land_branch("run-2", second, "agent-hq/7", "main")
    assert landed_2["landed"] is True
    assert landed_2["head"] != landed_1["head"]


def test_land_branch_adopts_identical_retry_and_blocks_a_real_conflict(monkeypatch, tmp_path):
    origin = _make_origin(tmp_path)
    base_commit = _git("rev-parse", "main", cwd=tmp_path / "_seed").strip()
    monkeypatch.setattr(cch, "_clone_url", lambda repo: str(origin))
    executor = ClaudeCodeHeadless({"workdir": str(tmp_path / "work")})

    # Someone else's identically-contented commit already landed on the
    # branch (e.g. a retry that got a fresh timestamp -- different SHA,
    # same tree/parent as this attempt's own commit).
    zombie = tmp_path / "zombie"
    _git("clone", str(origin), str(zombie))
    _git("checkout", base_commit, cwd=zombie)
    _git("checkout", "-b", "agent-hq/9", cwd=zombie)
    (zombie / "same.py").write_text("same\n")
    _git("add", "-A", cwd=zombie)
    _git("-c", "user.name=z", "-c", "user.email=z@example.com", "commit", "-m", "zombie",
         cwd=zombie)
    _git("push", "origin", "agent-hq/9", cwd=zombie)
    zombie_head = _git("rev-parse", "agent-hq/9", cwd=zombie).strip()

    # Our own attempt, built from the SAME base, with the SAME resulting
    # content -- its push is rejected (the branch moved), but the content
    # matches, so it's adopted rather than blocked.
    ours = executor.prepare_worktree("run-adopt", "o/r", base_commit)
    (ours / "same.py").write_text("same\n")
    landed = executor.land_branch("run-adopt", ours, "agent-hq/9", "main")
    assert landed == {"landed": True, "head": zombie_head}

    # A real conflict (different content from the same base) is reported,
    # never force-pushed over.
    conflicting = executor.prepare_worktree("run-conflict", "o/r", base_commit)
    (conflicting / "same.py").write_text("different\n")
    blocked = executor.land_branch("run-conflict", conflicting, "agent-hq/9", "main")
    assert blocked["landed"] is False
    assert blocked["remote_head"] == zombie_head


# -- healthcheck ----------------------------------------------------------------


def test_healthcheck_false_when_binary_missing():
    executor = ClaudeCodeHeadless({"claude_bin": "definitely-not-a-real-binary-xyz"})
    assert executor.healthcheck() is False
