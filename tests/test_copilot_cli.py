import json
import subprocess
from datetime import datetime, timedelta, timezone

from engine.adapters import copilot_cli as cc
from engine.adapters.claude_code_headless import ClaudeCodeHeadless
from engine.adapters.copilot_cli import CopilotCli

FUTURE_DEADLINE = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)


def test_copilot_cli_is_claude_code_headless_subclass():
    assert issubclass(CopilotCli, ClaudeCodeHeadless)


# -- _child_env ---------------------------------------------------------------


def test_child_env_includes_copilot_token_excludes_forbidden_and_anthropic(monkeypatch):
    monkeypatch.setenv("AGENT_HQ_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_TOKEN", "tok2")
    monkeypatch.setenv("GH_TOKEN", "tok3")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xyz")
    monkeypatch.setenv("SOME_SECRET", "leak-me-not")
    monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "ghu_bot_seat")

    env = cc._child_env()

    assert env["COPILOT_GITHUB_TOKEN"] == "ghu_bot_seat"
    assert "AGENT_HQ_TOKEN" not in env
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "SOME_SECRET" not in env


def test_child_env_without_copilot_token_in_parent_omits_it(monkeypatch):
    monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)

    env = cc._child_env()

    assert "COPILOT_GITHUB_TOKEN" not in env


# -- run: argv and subprocess handling ----------------------------------------


class FakeProc:
    def __init__(self, returncode=0, raise_timeout=False):
        self.returncode = returncode
        self._raise_timeout = raise_timeout
        self.killed = False
        self.communicate_calls = 0

    def communicate(self, input=None, timeout=None):
        self.communicate_calls += 1
        if self._raise_timeout and self.communicate_calls == 1:
            raise subprocess.TimeoutExpired(cmd="copilot", timeout=timeout)
        return "", ""

    def kill(self):
        self.killed = True


def _install_fake_popen(monkeypatch, proc: FakeProc):
    calls = []

    def fake_popen(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        return proc

    monkeypatch.setattr(cc.subprocess, "Popen", fake_popen)
    return calls


def test_run_argv_allows_all_tools_when_none_given(monkeypatch, tmp_path):
    proc = FakeProc()
    calls = _install_fake_popen(monkeypatch, proc)
    executor = CopilotCli({"copilot_bin": "copilot"})

    executor.run({"prompt": "do stuff", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    argv = calls[0]["argv"]
    assert argv[0] == "copilot"
    assert argv[1:5] == ["-p", "do stuff", "-s", "--no-ask-user"]
    assert argv[argv.index("--model") + 1] == "claude-sonnet-4.5"
    assert "--allow-all-tools" in argv


def test_run_argv_omits_allow_all_tools_when_tools_given(monkeypatch, tmp_path):
    proc = FakeProc()
    calls = _install_fake_popen(monkeypatch, proc)
    executor = CopilotCli({})

    executor.run({"prompt": "hi", "worktree": str(tmp_path)}, ["Bash", "Read"], FUTURE_DEADLINE)

    argv = calls[0]["argv"]
    assert "--allow-all-tools" not in argv


def test_run_uses_configured_model(monkeypatch, tmp_path):
    proc = FakeProc()
    calls = _install_fake_popen(monkeypatch, proc)
    executor = CopilotCli({"model": "custom-model"})

    executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    argv = calls[0]["argv"]
    assert argv[argv.index("--model") + 1] == "custom-model"


def test_run_timeout_kills_process_and_returns_timeout_outcome(monkeypatch, tmp_path):
    proc = FakeProc(raise_timeout=True)
    _install_fake_popen(monkeypatch, proc)
    executor = CopilotCli({})

    result = executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    assert result["outcome"] == "timeout"
    assert proc.killed is True


def test_run_success_records_zero_cost_and_usage_known(monkeypatch, tmp_path):
    proc = FakeProc(returncode=0)
    _install_fake_popen(monkeypatch, proc)
    executor = CopilotCli({})

    result = executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    assert result["outcome"] == "success"
    assert result["cost_usd"] == 0.0
    assert result["tokens"] is None
    assert result["usage_known"] is True
    assert result["session_id"] is None

    written = json.loads((tmp_path / ".agent-hq" / "execute-result.json").read_text())
    assert written == result


def test_run_nonzero_exit_is_failure_outcome(monkeypatch, tmp_path):
    proc = FakeProc(returncode=1)
    _install_fake_popen(monkeypatch, proc)
    executor = CopilotCli({})

    result = executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    assert result["outcome"] == "failure"


# -- healthcheck ----------------------------------------------------------------


def test_healthcheck_false_when_binary_missing():
    executor = CopilotCli({"copilot_bin": "definitely-not-a-real-binary-xyz"})
    assert executor.healthcheck() is False
