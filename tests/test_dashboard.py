"""`dashboard.json` projection coverage (D6, NFR-OBS).

The hostile-string check matters here and survives the move from a rendered
page to a fetched document: `tests/fixtures/state/tickets/HQ-1/state.json`
plants `</script><img src=x onerror=alert(1)>` inside a run's `artifacts`.
It has to round-trip as inert JSON data — the page that consumes it never
uses innerHTML (`dashboard/app.js`), so the string can only ever become text.
"""

import json
from argparse import Namespace
from pathlib import Path

from engine import cli
from engine.dashboard import document, write_document

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "state"
REPO_ROOT = Path(__file__).resolve().parent.parent

HOSTILE = "</script><img src=x onerror=alert(1)>"


def test_document_carries_whole_ticket_documents_and_health():
    doc = document(FIXTURES)

    assert doc["generated_at"].endswith("Z")
    assert len(doc["tickets"]) == 1

    ticket = doc["tickets"][0]
    assert ticket["ticket_id"] == "HQ-1"
    assert len(ticket["runs"]) == 3
    # Copied through unmodified: a trimmed field is a field the page can
    # never show, and every view is derived client-side from these.
    assert ticket == json.loads((FIXTURES / "tickets" / "HQ-1" / "state.json").read_text())

    assert doc["health"]["gate/github-pr"]["ok"] is False


def test_document_preserves_the_hostile_artifact_string_verbatim():
    doc = document(FIXTURES)
    artifacts = [a for run in doc["tickets"][0]["runs"] for a in run.get("artifacts", [])]

    assert HOSTILE in artifacts


def test_written_document_round_trips_as_json(tmp_path):
    doc = document(FIXTURES)
    out_path = write_document(doc, tmp_path)

    assert out_path.name == "dashboard.json"
    assert json.loads(out_path.read_text()) == doc


def test_document_of_an_empty_state_dir_is_still_valid(tmp_path):
    doc = document(tmp_path)

    assert doc["tickets"] == []
    assert doc["health"] == {}


def test_cli_dashboard_writes_dashboard_json(tmp_path):
    out_dir = tmp_path / "site"
    args = Namespace(state=str(FIXTURES), out=str(out_dir))
    cli._dashboard(args, REPO_ROOT)
    assert (out_dir / "dashboard.json").exists()
