"""Dashboard snapshot + HTML render coverage (Task 16, D6 minimal dashboard).

The XSS check matters here: `tests/fixtures/state/tickets/HQ-1/state.json`
plants a hostile `</script><img src=x onerror=alert(1)>` string inside a
run's `artifacts`. The rendered page must embed it as inert JSON text, never
as markup.
"""

import json
from argparse import Namespace
from html.parser import HTMLParser
from pathlib import Path

from engine import cli
from engine.dashboard import build, snapshot

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "state"
REPO_ROOT = Path(__file__).resolve().parent.parent


class _TagWalker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.script_count = 0
        self.data_script_count = 0
        self.img_count = 0
        self._data_chunks: list[str] = []
        self._in_data_script = False

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs)

    def _open(self, tag, attrs):
        if tag == "script":
            self.script_count += 1
            if dict(attrs).get("id") == "data":
                self.data_script_count += 1
                self._in_data_script = True
        if tag == "img":
            self.img_count += 1

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_data_script = False

    def handle_data(self, data):
        if self._in_data_script:
            self._data_chunks.append(data)

    @property
    def data_text(self) -> str:
        return "".join(self._data_chunks)


def test_snapshot_sums_only_usage_known_cost_and_lists_waiting_gate_runs():
    snap = snapshot(FIXTURES, config=None)

    assert snap["total_spend_usd"] == 1.5

    assert len(snap["waiting_on_humans"]) == 1
    waiting = snap["waiting_on_humans"][0]
    assert waiting["ticket_id"] == "HQ-1"
    assert waiting["task_id"] == "review"
    assert waiting["gate_request_id"] == 7
    assert waiting["gate_requested_at"] == "2026-07-18T00:00:00Z"

    assert len(snap["tickets"]) == 1
    assert snap["tickets"][0]["ticket_id"] == "HQ-1"
    assert len(snap["tickets"][0]["runs"]) == 3
    assert snap["health"]["gate/github-pr"]["ok"] is False


def test_build_renders_one_data_script_no_injected_markup_and_round_trips(tmp_path):
    snap = snapshot(FIXTURES, config=None)
    out_path = build(snap, tmp_path)
    html = out_path.read_text()

    walker = _TagWalker()
    walker.feed(html)

    # Exactly one <script id="data"> and exactly two <script> tags overall
    # (the data payload + the inline render logic) -- the hostile artifact
    # string must not have split into extra script/img elements.
    assert walker.data_script_count == 1
    assert walker.script_count == 2
    assert walker.img_count == 0

    assert json.loads(walker.data_text) == snap

    assert "HQ-1" in html
    assert "implement" in html
    assert "review" in html
    assert "docs" in html
    assert "1.5" in html
    assert "token expired" in html


def test_cli_dashboard_writes_index_html(tmp_path):
    out_dir = tmp_path / "site"
    args = Namespace(state=str(FIXTURES), out=str(out_dir))
    cli._dashboard(args, REPO_ROOT)
    assert (out_dir / "index.html").exists()
