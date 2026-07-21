"""CLI-surface coverage for the `agent-hq run` phase output (Task 15).

`scripts/run-phases.sh` greps the last stdout line of the prepare phase for
`claimed=true`/`claimed=false`; the other phases still print the full JSON
result.
"""

import json
from argparse import Namespace
from pathlib import Path

from engine import cli
from engine.config import Config
from engine.models import TicketDetails
from engine.runner import intake_ticket

REPO_ROOT = Path(__file__).resolve().parent.parent


def _args(**over):
    base = dict(state="/tmp/whatever", phase="prepare", run_id="r1", execute_outcome=None)
    base.update(over)
    return Namespace(**base)


def _stub_load_and_store(monkeypatch):
    monkeypatch.setattr(cli, "_load", lambda repo_root: (object(), object()))
    monkeypatch.setattr(cli, "_store", lambda args: object())


def test_run_prepare_prints_claimed_true(monkeypatch, capsys):
    _stub_load_and_store(monkeypatch)
    monkeypatch.setattr("engine.runner.run_task", lambda *a, **k: {"claimed": True, "worktree": "x"})
    cli._run(_args(), REPO_ROOT)
    assert capsys.readouterr().out.strip().splitlines()[-1] == "claimed=true"


def test_run_prepare_prints_claimed_false(monkeypatch, capsys):
    _stub_load_and_store(monkeypatch)
    monkeypatch.setattr("engine.runner.run_task", lambda *a, **k: {"claimed": False})
    cli._run(_args(), REPO_ROOT)
    assert capsys.readouterr().out.strip().splitlines()[-1] == "claimed=false"


def test_run_execute_prints_json(monkeypatch, capsys):
    _stub_load_and_store(monkeypatch)
    monkeypatch.setattr("engine.runner.run_task", lambda *a, **k: {"outcome": "success"})
    cli._run(_args(phase="execute"), REPO_ROOT)
    assert json.loads(capsys.readouterr().out) == {"outcome": "success"}


class _FakeTracker:
    """Records the repo it was built with and the ref it was fetched with."""

    def __init__(self, repo):
        self.repo = repo
        self.fetched_ref = None

    def fetch_ticket(self, ref):
        self.fetched_ref = ref
        return TicketDetails(ticket_id="42", title="t", body="b", labels=[])


class _FakeStore:
    def read_state(self, ticket_id):
        return None


def _intake_config():
    return Config(
        components={"tracker": {"adapter": "github-issues"}}, repos={},
        projects={"engine_repo": "engine-org/engine-repo", "intake_label": "hq:intake"},
        approvers={}, budgets={},
    )


def _adapter_fn(captured):
    def fn(port, adapter_name, repo=None):
        tracker = _FakeTracker(repo)
        captured.append(tracker)
        return tracker

    return fn


def test_intake_bare_issue_id_touches_only_engine_repo():
    captured = []
    result = intake_ticket(
        "42", "evt-1", _intake_config(), {"intake": {}}, _FakeStore(), _adapter_fn(captured)
    )
    assert captured[0].repo == "engine-org/engine-repo"
    assert captured[0].fetched_ref == "42"
    assert result == "skipped"


def test_intake_stale_org_repo_ref_form_is_ignored_not_honored():
    captured = []
    result = intake_ticket(
        "other-org/other-repo#42", "evt-1", _intake_config(), {"intake": {}},
        _FakeStore(), _adapter_fn(captured),
    )
    assert captured[0].repo == "engine-org/engine-repo"
    assert captured[0].fetched_ref == "42"
    assert result == "skipped"
