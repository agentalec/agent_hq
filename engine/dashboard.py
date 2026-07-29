"""`dashboard.json` — the state branch's own projection for the operator
dashboard (NFR-OBS per D6).

The dashboard is a static page in `dashboard/` that fetches exactly one
document from the state branch and derives every view client-side. This
module builds that document; `GitJsonStateStore.write()` emits it alongside
the state files it just wrote, so the projection can never be staler than the
branch and the Pages deploy never has to read state
(`docs/dashboard-design-requirements.md` §4.5).

Ticket documents are copied through **unmodified**: the renderer wants the
run chain, `work_repos`, `block_reason` and per-run `artifacts`, and any
field trimmed here is a field the page can never show. Nothing is
precomputed -- totals, the gate queue and the run chain are all derived in
the browser.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

DOCUMENT_NAME = "dashboard.json"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def document(state_dir: str | Path, generated_at: str | None = None) -> dict:
    """`{generated_at, tickets, health}` read off a state-store worktree.

    Read-only -- no `GitJsonStateStore` needed, so this also runs against a
    plain checkout of the branch.
    """
    state_dir = Path(state_dir)

    tickets = []
    tickets_dir = state_dir / "tickets"
    for ticket_dir in sorted(tickets_dir.iterdir()) if tickets_dir.exists() else []:
        state_path = ticket_dir / "state.json"
        if state_path.exists():
            tickets.append(json.loads(state_path.read_text()))

    health_path = state_dir / "health" / "latest.json"
    health = json.loads(health_path.read_text()) if health_path.exists() else {}

    return {
        "generated_at": generated_at or _now_iso(),
        "tickets": tickets,
        "health": health,
    }


def write_document(doc: dict, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / DOCUMENT_NAME
    out_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return out_path
