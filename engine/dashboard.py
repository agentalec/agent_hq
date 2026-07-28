"""Minimal status dashboard (NFR-OBS per D6).

Reads `tickets/*/state.json` and `health/latest.json` directly off a
state-store worktree (read-only -- no `GitJsonStateStore` needed) and
renders one self-contained HTML page. All dynamic values are inserted via
`createTextNode`/`textContent` in the page's inline script, never
`innerHTML`, so an untrusted string sitting in e.g. `artifacts` can't inject
markup.

# ponytail: single state-table page; kanban/timelines/spend breakdowns land
# with P1 (docs/roadmap.md)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from engine.config import Config


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot(state_dir: str | Path, config: Config) -> dict:
    # ponytail: config unused today; kept for the P1 effective-config view
    state_dir = Path(state_dir)
    tickets = []
    waiting_on_humans = []
    total_spend_usd = 0.0

    tickets_dir = state_dir / "tickets"
    ticket_dirs = sorted(tickets_dir.iterdir()) if tickets_dir.exists() else []
    for ticket_dir in ticket_dirs:
        state_path = ticket_dir / "state.json"
        if not state_path.exists():
            continue
        ticket = json.loads(state_path.read_text())
        runs = ticket.get("runs", [])
        tickets.append({
            "ticket_id": ticket["ticket_id"],
            "status": ticket["status"],
            "runs": runs,
        })
        for run in runs:
            if run.get("usage_known") and run.get("cost_usd") is not None:
                total_spend_usd += run["cost_usd"]
            if run.get("state") == "WAITING_GATE":
                waiting_on_humans.append({
                    "ticket_id": ticket["ticket_id"],
                    "task_id": run.get("task_id"),
                    "run_id": run.get("run_id"),
                    "gate_request_id": run.get("gate_request_id"),
                    "gate_requested_at": run.get("gate_requested_at"),
                })

    health_path = state_dir / "health" / "latest.json"
    health = json.loads(health_path.read_text()) if health_path.exists() else {}

    return {
        "generated_at": _now_iso(),
        "tickets": tickets,
        "waiting_on_humans": waiting_on_humans,
        "total_spend_usd": total_spend_usd,
        "health": health,
    }


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>agent_hq dashboard</title>
<style>
body { font-family: system-ui, sans-serif; margin: 2rem; }
table { border-collapse: collapse; margin: 0.5rem 0 1.5rem; }
th, td { border: 1px solid #ccc; padding: 0.3rem 0.6rem; text-align: left; }
h2 { margin-top: 2rem; }
</style>
</head>
<body>
<h1>agent_hq dashboard</h1>
<p id="generated-at"></p>
<p id="total-spend"></p>

<h2>Tickets</h2>
<table id="tickets-table">
<thead><tr>
<th>Ticket</th><th>Status</th><th>Run</th><th>Task</th><th>State</th>
<th>Attempt</th><th>Cost ($)</th><th>PR</th>
</tr></thead>
<tbody></tbody>
</table>

<h2>Waiting on humans</h2>
<ul id="waiting-list"></ul>

<h2>Adapter health</h2>
<ul id="health-list"></ul>

<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  var data = JSON.parse(document.getElementById('data').textContent);

  function cell(tag, value) {
    var el = document.createElement(tag);
    if (value !== null && value !== undefined) {
      el.appendChild(document.createTextNode(String(value)));
    }
    return el;
  }

  document.getElementById('generated-at').appendChild(
    document.createTextNode('Generated: ' + data.generated_at));
  document.getElementById('total-spend').appendChild(
    document.createTextNode('Total spend (usage-known runs): $' + data.total_spend_usd));

  var tbody = document.querySelector('#tickets-table tbody');
  data.tickets.forEach(function (ticket) {
    var runs = ticket.runs.length ? ticket.runs : [null];
    runs.forEach(function (run) {
      var row = document.createElement('tr');
      row.appendChild(cell('td', ticket.ticket_id));
      row.appendChild(cell('td', ticket.status));
      if (run) {
        row.appendChild(cell('td', run.run_id ? run.run_id.slice(0, 8) : ''));
        row.appendChild(cell('td', run.task_id));
        row.appendChild(cell('td', run.state));
        row.appendChild(cell('td', run.attempt));
        row.appendChild(cell('td', run.cost_usd));
        var prCell = document.createElement('td');
        if (run.pr_ref) {
          var a = document.createElement('a');
          a.href = 'https://github.com/' + run.pr_ref.replace('#', '/pull/');
          a.appendChild(document.createTextNode(run.pr_ref));
          prCell.appendChild(a);
        }
        row.appendChild(prCell);
      } else {
        for (var i = 0; i < 6; i++) row.appendChild(document.createElement('td'));
      }
      tbody.appendChild(row);
    });
  });

  var waitingList = document.getElementById('waiting-list');
  data.waiting_on_humans.forEach(function (w) {
    waitingList.appendChild(cell('li',
      w.ticket_id + ' / ' + w.task_id + ' -- gate ' + w.gate_request_id +
      ' requested ' + w.gate_requested_at));
  });

  var healthList = document.getElementById('health-list');
  Object.keys(data.health).forEach(function (key) {
    var entry = data.health[key];
    healthList.appendChild(cell('li',
      key + ': ' + (entry.ok ? 'OK' : 'FAILING') + ' -- ' + entry.detail));
  });
})();
</script>
</body>
</html>
"""


def build(snapshot: dict, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    embedded = json.dumps(snapshot).replace("<", "\\u003c")
    out_path = out_dir / "index.html"
    out_path.write_text(_PAGE.replace("__DATA__", embedded), encoding="utf-8")
    return out_path
