"""CLI-surface coverage for the `agent-hq run` phase output (Task 15).

`scripts/run-phases.sh` greps the last stdout line of the prepare phase for
`claimed=true`/`claimed=false`; the other phases still print the full JSON
result.
"""

import json
from argparse import Namespace
from pathlib import Path

from engine import cli

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
