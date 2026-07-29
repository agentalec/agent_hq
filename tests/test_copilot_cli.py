import json
import subprocess
from datetime import UTC, datetime, timedelta

from engine.adapters import copilot_cli as cc
from engine.adapters.claude_code_headless import ClaudeCodeHeadless
from engine.adapters.copilot_cli import CopilotCli

FUTURE_DEADLINE = (datetime.now(UTC) + timedelta(hours=1)).strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)

# Captured from a real piped `copilot -p "say hi" --no-ask-user` (stderr).
REAL_TRAILER = (
    "\n\nChanges    +0 -0\n"
    "AI Credits 0.46 (16s)\n"
    "Tokens     ↑ 17.3k (1.7k cached) • ↓ 310 (256 reasoning)\n"
    "Resume     copilot --resume=5e77213d-83e4-4984-ab14-d93d774d4794\n"
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
    def __init__(self, returncode=0, raise_timeout=False, stdout="", stderr=""):
        self.returncode = returncode
        self._raise_timeout = raise_timeout
        self._stdout = stdout
        self._stderr = stderr
        self.killed = False
        self.communicate_calls = 0

    def communicate(self, input=None, timeout=None):
        self.communicate_calls += 1
        if self._raise_timeout and self.communicate_calls == 1:
            raise subprocess.TimeoutExpired(cmd="copilot", timeout=timeout)
        return self._stdout, self._stderr

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
    # No `-s`: it suppresses the session trailer the spend is parsed from.
    assert argv[1:4] == ["-p", "do stuff", "--no-ask-user"]
    assert "-s" not in argv
    assert argv[argv.index("--model") + 1] == "claude-sonnet-4.5"
    assert "--allow-all-tools" in argv


def test_run_argv_maps_task_tool_allowlist(monkeypatch, tmp_path):
    proc = FakeProc()
    calls = _install_fake_popen(monkeypatch, proc)
    executor = CopilotCli({})

    executor.run(
        {"prompt": "hi", "worktree": str(tmp_path)},
        ["Read", "Grep", "Glob", "Write"],
        FUTURE_DEADLINE,
    )

    argv = calls[0]["argv"]
    assert "--allow-all-tools" not in argv
    assert "--allow-tool=read" in argv
    assert "--allow-tool=write" in argv
    assert argv.count("--allow-tool=read") == 1


def test_run_uses_configured_model(monkeypatch, tmp_path):
    proc = FakeProc()
    calls = _install_fake_popen(monkeypatch, proc)
    executor = CopilotCli({"model": "custom-model"})

    executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    argv = calls[0]["argv"]
    assert argv[argv.index("--model") + 1] == "custom-model"


def test_run_timeout_maps_to_failure_with_detail(monkeypatch, tmp_path):
    """Task 12 normalization: schemas/execute-result.schema.json only knows
    success/failure -- a timeout is reported as a schema-valid failure with
    a `detail`, not a bare "timeout" outcome."""
    proc = FakeProc(raise_timeout=True)
    _install_fake_popen(monkeypatch, proc)
    executor = CopilotCli({})

    result = executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    assert result["outcome"] == "failure"
    assert "timed out" in result["detail"]
    assert proc.killed is True


def test_run_success_parses_spend_from_the_stderr_trailer(monkeypatch, tmp_path):
    """The trailer is verbatim from a piped (non-TTY) `copilot -p` run: it
    lands on stderr, stdout carries only the answer text, and no escape
    codes survive the pipe."""
    proc = FakeProc(returncode=0, stdout="hi\n", stderr=REAL_TRAILER)
    _install_fake_popen(monkeypatch, proc)
    executor = CopilotCli({})

    result = executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    assert result["outcome"] == "success"
    assert result["cost_usd"] == 0.0046  # 0.46 AI credits at $0.01 each
    assert result["tokens"] == 17610  # 17.3k up + 310 down
    assert result["usage_known"] is True
    assert "session_id" not in result  # Task 12: not part of the transported contract

    written = json.loads((tmp_path / ".agent-hq" / "execute-result.json").read_text())
    assert written == result


def test_run_without_a_trailer_reports_zero_but_stays_usage_known(monkeypatch, tmp_path):
    """A killed or reformatted run understates rather than reporting unknown
    usage -- `usage_known: False` would block the ticket on every transient
    failure instead of retrying it."""
    proc = FakeProc(returncode=1, stderr="boom\n")
    _install_fake_popen(monkeypatch, proc)
    executor = CopilotCli({})

    result = executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    assert result["outcome"] == "failure"
    assert result["cost_usd"] == 0.0
    assert result["tokens"] is None
    assert result["usage_known"] is True


def test_run_failure_reports_the_child_stderr_as_detail(monkeypatch, tmp_path):
    """Verbatim from a real misconfigured run: without this the whole
    explanation for a bad `config/components.yml` model is discarded and the
    run records a bare `failure`."""
    proc = FakeProc(returncode=1, stderr='Error: Model "gpt-5-mini" from --model flag is not available.\n')
    _install_fake_popen(monkeypatch, proc)
    executor = CopilotCli({})

    result = executor.run({"prompt": "hi", "worktree": str(tmp_path)}, [], FUTURE_DEADLINE)

    assert result["detail"] == 'Error: Model "gpt-5-mini" from --model flag is not available.'


def test_failure_detail_redacts_tokens_and_drops_trailer_lines():
    """`detail` reaches the state ledger and escalation comments, and the
    child holds a real COPILOT_GITHUB_TOKEN."""
    detail = cc._failure_detail(f"Error: bad credentials ghu_abcdefghij0123456789xyz\n{REAL_TRAILER}")

    assert "ghu_" not in detail
    assert "<redacted>" in detail
    assert "AI Credits" not in detail


def test_failure_detail_without_output_still_says_something():
    assert cc._failure_detail("") == "agent exited nonzero without output"


def test_parse_usage_expands_suffixes_and_ignores_escape_codes():
    blob = "\x1b[1mAI Credits\x1b[0m 128 (4m2s)\nTokens     ↑ 1.5M (900k cached) • ↓ 12.5k\n"

    cost_usd, tokens = cc._parse_usage(blob)

    assert cost_usd == 1.28
    assert tokens == 1_512_500


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
