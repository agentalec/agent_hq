"""Git-JSON state store (PD-6, D5).

Reads/writes JSON documents on a worktree of the orphan `agent-hq-state`
branch: `tickets/<id>/state.json` (per-ticket doc), `tickets/<id>/events.jsonl`
(append-only), `health/latest.json`. Writers are serialized externally by an
Actions concurrency group (D5) -- the fetch/reset/reapply retry here is a
safety net, not the primary concurrency control. See
docs/ports/state-store.md for the contract. Not a registry port (PD-7) --
callers construct this directly with a worktree path.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _add_minutes(iso: str, minutes: float) -> str:
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (dt + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Txn:
    """Mutation surface passed into `GitJsonStateStore.write()`'s fn.

    Loads each ticket/health resource from disk at most once per attempt,
    merges in memory, and tracks which resources changed so `write()` only
    touches (and commits) files that actually moved.
    """

    def __init__(self, store: "GitJsonStateStore"):
        self._store = store
        self._tickets: dict[str, dict] = {}
        self._new_events: dict[str, list[dict]] = {}
        self._health: dict | None = None
        self.dirty_tickets: set[str] = set()
        self.dirty_events: set[str] = set()
        self.dirty_health = False

    def _ticket(self, ticket_id: str) -> dict:
        if ticket_id not in self._tickets:
            existing = self._store.read_state(ticket_id)
            self._tickets[ticket_id] = existing or {
                "ticket_id": ticket_id,
                "pinned_comment_id": None,
                "status": "ACTIVE",
                "runs": [],
            }
        return self._tickets[ticket_id]

    def set_ticket(self, ticket_id: str, **fields) -> None:
        self._ticket(ticket_id).update(fields)
        self.dirty_tickets.add(ticket_id)

    def put_run(self, ticket_id: str, run: dict) -> None:
        runs = self._ticket(ticket_id)["runs"]
        for i, existing in enumerate(runs):
            if existing["run_id"] == run["run_id"]:
                runs[i] = run
                break
        else:
            runs.append(run)
        self.dirty_tickets.add(ticket_id)

    def get_run(self, ticket_id: str, run_id: str) -> dict | None:
        for run in self._ticket(ticket_id)["runs"]:
            if run["run_id"] == run_id:
                return run
        return None

    def update_run(self, ticket_id: str, run_id: str, **fields) -> None:
        run = self.get_run(ticket_id, run_id)
        if run is None:
            raise KeyError(f"run {run_id} not found on ticket {ticket_id}")
        run.update(fields)
        self.dirty_tickets.add(ticket_id)

    def append_event(self, ticket_id: str, event: dict) -> None:
        pending = self._new_events.setdefault(ticket_id, [])
        seen_ids = {e["event_id"] for e in self._store._read_events(ticket_id)}
        seen_ids |= {e["event_id"] for e in pending}
        if event["event_id"] in seen_ids:
            return
        pending.append(event)
        self.dirty_events.add(ticket_id)

    def record_health(self, port: str, adapter: str, ok: bool, detail: str) -> None:
        if self._health is None:
            self._health = self._store._read_health()
        self._health[f"{port}/{adapter}"] = {"ok": ok, "detail": detail, "ts": _now_iso()}
        self.dirty_health = True


class GitJsonStateStore:
    def __init__(self, worktree_path: str | Path):
        self.worktree_path = Path(worktree_path)
        if not self._git("remote").strip():
            raise RuntimeError(f"{self.worktree_path} has no git remote configured")

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.worktree_path), *self._cred_args(), *args],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout

    def _cred_args(self) -> list[str]:
        if os.environ.get("AGENT_HQ_TOKEN"):
            return [
                "-c",
                "credential.helper=!f(){ echo username=x-access-token; "
                'echo "password=$AGENT_HQ_TOKEN"; };f',
            ]
        return []

    def _push(self) -> subprocess.CompletedProcess:
        cmd = ["git", "-C", str(self.worktree_path), *self._cred_args(), "push"]
        return subprocess.run(cmd, capture_output=True, text=True)

    def _current_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD").strip()

    def _state_path(self, ticket_id: str) -> Path:
        return self.worktree_path / "tickets" / ticket_id / "state.json"

    def _events_path(self, ticket_id: str) -> Path:
        return self.worktree_path / "tickets" / ticket_id / "events.jsonl"

    def _health_path(self) -> Path:
        return self.worktree_path / "health" / "latest.json"

    def read_state(self, ticket_id: str) -> dict | None:
        path = self._state_path(ticket_id)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def _read_events(self, ticket_id: str) -> list[dict]:
        path = self._events_path(ticket_id)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def _read_health(self) -> dict:
        path = self._health_path()
        if not path.exists():
            return {}
        return json.loads(path.read_text())

    def _flush(self, txn: Txn) -> None:
        for ticket_id in txn.dirty_tickets:
            path = self._state_path(ticket_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(txn._tickets[ticket_id], indent=2) + "\n")
        for ticket_id in txn.dirty_events:
            path = self._events_path(ticket_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as f:
                for event in txn._new_events[ticket_id]:
                    f.write(json.dumps(event) + "\n")
        if txn.dirty_health:
            path = self._health_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(txn._health, indent=2) + "\n")

    def _commit_message(self, txn: Txn) -> str:
        ids = sorted(txn.dirty_tickets | txn.dirty_events)
        if ids:
            return "state: " + ", ".join(ids)
        return "state: health update"

    def write(self, fn: Callable[[Txn], None]) -> None:
        for attempt in (1, 2):
            txn = Txn(self)
            fn(txn)
            if not (txn.dirty_tickets or txn.dirty_events or txn.dirty_health):
                return
            self._flush(txn)
            self._git("add", "-A")
            self._git("commit", "-m", self._commit_message(txn))
            result = self._push()
            if result.returncode == 0:
                return
            if attempt == 2:
                raise RuntimeError(f"state push rejected twice: {result.stderr}")
            # ponytail: Actions concurrency group serializes writers; this retry is a safety net only
            branch = self._current_branch()
            self._git("fetch", "origin", branch)
            self._git("reset", "--hard", f"origin/{branch}")

    def claim_run(
        self, ticket_id: str, run_id: str, now_iso: str, max_runtime_min: float
    ) -> bool:
        claimed = False

        def fn(txn: Txn) -> None:
            nonlocal claimed
            # Reset per attempt: a retry after a lost push race re-runs fn against
            # fresh state, and only the attempt that actually lands may claim.
            claimed = False
            run = txn.get_run(ticket_id, run_id)
            if run is None or run["state"] != "QUEUED":
                return
            deadline = run.get("deadline") or _add_minutes(now_iso, max_runtime_min)
            txn.update_run(
                ticket_id,
                run_id,
                state="RUNNING",
                deadline=deadline,
                attempt_started_at=now_iso,
            )
            claimed = True

        self.write(fn)
        return claimed
