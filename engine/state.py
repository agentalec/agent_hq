"""Git-JSON state store (PD-6, D5).

Reads/writes JSON documents on a worktree of the orphan `agent-hq-state`
branch: `tickets/<id>/state.json` (per-ticket doc), `tickets/<id>/events.jsonl`
(append-only), `health/latest.json`. The bounded fetch/reset/replay retry on a
confirmed non-fast-forward push rejection is the concurrency model (the CAS
that serializes concurrent writers across tickets -- docs/operations.md §11).
No Actions concurrency group stands behind it: the credentialed jobs are keyed
per run/issue, since one shared group made a burst of triggers cancel each
other's pending runs. See
docs/ports/state-store.md for the contract. Not a registry port (PD-7) --
callers construct this directly with a worktree path.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Bounded replay: fetch -> reset --hard -> re-run fn, only on a *confirmed*
# non-fast-forward push rejection (see `_push_rejected`). Auth/network/server
# errors are not CAS contention and fail on the first attempt.
#
# A writer can lose to each of its N-1 concurrent peers before winning, so the
# bound has to exceed the realistic writer count. That count went UP when the
# credentialed jobs stopped sharing one Actions concurrency group (they were
# cancelling each other's pending runs): concurrent writers are now up to
# `in_flight_cap` claimed runs, the dispatcher, and one intake per issue in a
# filing burst. 5 was sized for the serialized world and a 6-issue burst could
# exhaust it. Retries are sub-second (see `_retry_backoff_seconds`), so the
# cost of headroom here is a few seconds on a genuinely stuck writer.
_MAX_WRITE_ATTEMPTS = 12

# Run states that occupy a ticket's one in-flight slot for `claim_run`'s
# per-ticket exclusivity and global in-flight cap. Duplicated from
# `engine.engine.EXCLUSIVE_STATES` (not imported -- engine.py imports this
# module, so the reverse import would be circular); QUEUED is deliberately
# excluded from the cap count -- see `claim_run`.
_EXCLUSIVE_STATES = {"RUNNING", "WAITING_GATE"}

# The ledger layout, in one place: `artifacts_dir` resolves it against the
# worktree, `artifact_ledger_path` hands the same path to anything that
# addresses the state branch remotely (a gate comment's artifact link).
_ARTIFACTS_DIR = "tickets/{ticket_id}/artifacts/{run_id}"


def artifact_ledger_path(ticket_id: str, run_id: str, rel_path: str) -> str:
    """Where `rel_path` lives on the state branch, branch-relative -- the
    stable reference for a reader outside the engine."""
    return f"{_ARTIFACTS_DIR.format(ticket_id=ticket_id, run_id=run_id)}/{rel_path}"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _add_minutes(iso: str, minutes: float) -> str:
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return (dt + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _retry_backoff_seconds(attempt: int) -> float:
    # ponytail: small jittered linear backoff; replays are local (same
    # remote, orphan branch) so sub-second delay is plenty.
    return random.uniform(0.02, 0.1) * attempt


def _push_rejected(porcelain_stdout: str) -> bool:
    """True only for a confirmed non-fast-forward rejection: a `!`-flagged
    line in `git push --porcelain` output whose summary contains `[rejected`.
    Parsed from the machine-readable porcelain format, not human-readable
    stderr, so auth/network/server failures are never mistaken for CAS
    contention (they must fail fast instead of being replayed)."""
    for line in porcelain_stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0] == "!" and "[rejected" in parts[2]:
            return True
    return False


class Txn:
    """Mutation surface passed into `GitJsonStateStore.write()`'s fn.

    Loads each ticket/health resource from disk at most once per attempt,
    merges in memory, and tracks which resources changed so `write()` only
    touches (and commits) files that actually moved.
    """

    def __init__(self, store: GitJsonStateStore):
        self._store = store
        self._tickets: dict[str, dict] = {}
        self._new_events: dict[str, list[dict]] = {}
        self._health: dict | None = None
        self._artifacts: dict[tuple[str, str], dict[str, bytes]] = {}
        self.dirty_tickets: set[str] = set()
        self.dirty_events: set[str] = set()
        self.dirty_health = False
        self.dirty_artifacts: set[str] = set()

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

    def write_artifact(self, ticket_id: str, run_id: str, rel_path: str, content: bytes) -> None:
        """Stage a ledger-artifact file under tickets/<id>/artifacts/<run_id>/,
        namespaced by the PRODUCING run so a later sibling handoff's child can
        never overwrite a shared path. Flushed and committed by `write()`
        alongside any ticket/event changes in the same transaction -- never a
        work-repo commit."""
        self._artifacts.setdefault((ticket_id, run_id), {})[rel_path] = content
        self.dirty_artifacts.add(ticket_id)

    def set_pending_handoffs(self, ticket_id: str, run_id: str, handoffs: list[dict]) -> None:
        """Store a gated source run's proposed handoffs pending gate approval."""
        self.update_run(ticket_id, run_id, pending_handoffs=handoffs)

    def has_artifact(self, ticket_id: str, run_id: str, rel_path: str) -> bool:
        """True if `rel_path` was staged in THIS transaction or already
        persisted for (ticket_id, run_id) -- the state-dependent "ledger
        entry exists" guard `apply_handoffs` enforces before appending a
        child run that depends on it."""
        staged = self._artifacts.get((ticket_id, run_id), {})
        if rel_path in staged:
            return True
        return self._store.read_artifact(ticket_id, run_id, rel_path) is not None

    def ticket_doc(self, ticket_id: str) -> dict:
        """Current in-transaction view of the ticket doc (reflects any
        mutation already applied earlier this attempt) -- for guards that
        need to see runs appended earlier in the same transaction, e.g.
        `apply_handoffs`'s loop/budget check."""
        return self._ticket(ticket_id)

    def upsert_work_repo(self, ticket_id: str, repo: str, **fields) -> None:
        """Insert or update this ticket's `work_repos` entry for `repo`
        (schemas/state.schema.json $defs/work_repo -- only `repo` required);
        used whenever a task opens/updates a PR for a repo, so queue-empty
        completion can find every repo's PR without walking run ancestry."""
        ticket = self._ticket(ticket_id)
        work_repos = ticket.setdefault("work_repos", [])
        for wr in work_repos:
            if wr["repo"] == repo:
                wr.update(fields)
                break
        else:
            work_repos.append({"repo": repo, **fields})
        self.dirty_tickets.add(ticket_id)

    def set_block(
        self, ticket_id: str, *, reason: str, source: str, interrupted_run: str | None = None
    ) -> None:
        """Flip a ticket to BLOCKED and record the lifecycle-block fields
        (schemas/state.schema.json block_reason/block_source/interrupted_run_id)."""
        self.set_ticket(
            ticket_id,
            status="BLOCKED",
            block_reason=reason,
            block_source=source,
            interrupted_run_id=interrupted_run,
        )


class GitJsonStateStore:
    def __init__(self, worktree_path: str | Path):
        self.worktree_path = Path(worktree_path)
        if not self._git("remote").strip():
            raise RuntimeError(f"{self.worktree_path} has no git remote configured")

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.worktree_path), *self._cred_args(), *args],
            capture_output=True,
            text=True, check=False
)
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
        return result.stdout

    def _cred_args(self) -> list[str]:
        if os.environ.get("AGENT_HQ_TOKEN"):
            return [
                "-c",
                (
                    "credential.helper=!f(){ echo username=x-access-token; "
                    'echo "password=$AGENT_HQ_TOKEN"; };f'
                ),
            ]
        return []

    def _push(self) -> subprocess.CompletedProcess:
        cmd = ["git", "-C", str(self.worktree_path), *self._cred_args(), "push", "--porcelain"]
        return subprocess.run(cmd, capture_output=True, text=True, check=False)

    def _current_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD").strip()

    def _state_path(self, ticket_id: str) -> Path:
        return self.worktree_path / "tickets" / ticket_id / "state.json"

    def _events_path(self, ticket_id: str) -> Path:
        return self.worktree_path / "tickets" / ticket_id / "events.jsonl"

    def _health_path(self) -> Path:
        return self.worktree_path / "health" / "latest.json"

    def artifacts_dir(self, ticket_id: str, run_id: str) -> Path:
        return self.worktree_path / _ARTIFACTS_DIR.format(ticket_id=ticket_id, run_id=run_id)

    def read_artifact(self, ticket_id: str, run_id: str, rel_path: str) -> bytes | None:
        """Raw bytes -- ledger artifacts are not all text. A directory
        artifact (see `engine.runner._expand_declared`) holds whatever the
        producing run put there, screenshots included."""
        path = self.artifacts_dir(ticket_id, run_id) / rel_path
        if not path.exists():
            return None
        return path.read_bytes()

    def read_artifact_text(self, ticket_id: str, run_id: str, rel_path: str) -> str | None:
        """`read_artifact` for the callers that want text (review.md,
        summary.md). Undecodable bytes read as None rather than raising --
        a caller asking a PNG for its text gets "no text", not a crash."""
        raw = self.read_artifact(ticket_id, run_id, rel_path)
        if raw is None:
            return None
        try:
            return raw.decode()
        except UnicodeDecodeError:
            return None

    def healthcheck(self) -> bool:
        return self.worktree_path.exists() and bool(self._git("remote").strip())

    def read_state(self, ticket_id: str) -> dict | None:
        path = self._state_path(ticket_id)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def list_tickets(self) -> list[str]:
        tickets_dir = self.worktree_path / "tickets"
        if not tickets_dir.exists():
            return []
        return sorted(
            p.name for p in tickets_dir.iterdir() if (p / "state.json").exists()
        )

    def read_events(self, ticket_id: str) -> list[dict]:
        return self._read_events(ticket_id)

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
        for (ticket_id, run_id), files in txn._artifacts.items():
            base = self.artifacts_dir(ticket_id, run_id)
            for rel_path, content in files.items():
                path = base / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
        if txn.dirty_health:
            path = self._health_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(txn._health, indent=2) + "\n")

    def _write_dashboard_document(self) -> None:
        """Rebuild `dashboard.json` at the branch root from what is on disk.

        # ponytail: re-reads every ticket file per write -- 11 tickets is
        # ~60 KB, so it costs nothing today. If the branch grows past a few
        # hundred tickets, project incrementally from `txn._tickets` instead.
        """
        from engine.dashboard import document, write_document

        write_document(document(self.worktree_path), self.worktree_path)

    def _commit_message(self, txn: Txn) -> str:
        ids = sorted(txn.dirty_tickets | txn.dirty_events | txn.dirty_artifacts)
        if ids:
            return "state: " + ", ".join(ids)
        return "state: health update"

    def write(self, fn: Callable[[Txn], None]) -> None:
        # This replay loop is the concurrency model: a rejected push is the
        # CAS that forces a re-read (docs/operations.md §11). Nothing
        # pre-serializes the writers any more, so this is the whole of it.
        for attempt in range(1, _MAX_WRITE_ATTEMPTS + 1):
            txn = Txn(self)
            fn(txn)
            if not (
                txn.dirty_tickets or txn.dirty_events or txn.dirty_health or txn.dirty_artifacts
            ):
                return
            self._flush(txn)
            self._git("add", "-A")
            # Dirtiness is DECLARED by the mutators, not computed -- writing a
            # field its current value still marks the ticket dirty. Without
            # this check `git commit` fails outright on an empty tree, so a
            # caller that re-writes an unchanged value (the sweep's PR-comment
            # watermark, re-read with no new comments) would raise every pass.
            if not self._git("diff", "--cached", "--name-only").strip():
                return
            # Only now that the state really moved: `dashboard.json` carries a
            # fresh `generated_at`, so regenerating it before the check above
            # would make every no-op write look like a change and undo that
            # guard. It is a projection -- rebuilt from what was just
            # flushed, never read back as state.
            self._write_dashboard_document()
            self._git("add", "-A")
            self._git("commit", "-m", self._commit_message(txn))
            result = self._push()
            if result.returncode == 0:
                return
            if not _push_rejected(result.stdout):
                raise RuntimeError(f"state push failed: {result.stderr}")
            if attempt == _MAX_WRITE_ATTEMPTS:
                raise RuntimeError(
                    f"state push rejected after {_MAX_WRITE_ATTEMPTS} attempts: {result.stderr}"
                )
            time.sleep(_retry_backoff_seconds(attempt))
            branch = self._current_branch()
            self._git("fetch", "origin", branch)
            self._git("reset", "--hard", f"origin/{branch}")

    def _has_exclusive_run(self, ticket_id: str) -> bool:
        doc = self.read_state(ticket_id) or {}
        return any(r["state"] in _EXCLUSIVE_STATES for r in doc.get("runs", []))

    def claim_run(
        self,
        ticket_id: str,
        run_id: str,
        now_iso: str,
        max_runtime_min: float,
        in_flight_cap: int | None = None,
    ) -> bool:
        """Atomically claim a QUEUED run for execution.

        This is the real compare-and-swap enforcement point -- unlike
        `engine.check_concurrency`, which is only a cheap, stale-tolerant
        ADVISORY pre-filter the dispatcher uses to skip an obviously-blocked
        run before even attempting a claim. Refuses (leaves the run QUEUED,
        unclaimed) when:
        - the run isn't QUEUED (already claimed, or claimed by a concurrent
          winner since this attempt started reading state), or
        - the SAME ticket already has another RUNNING/WAITING_GATE run
          (per-ticket exclusivity -- at most one in-flight run per ticket),
          or
        - `in_flight_cap` is given and the number of OTHER tickets with a
          RUNNING/WAITING_GATE run has already reached it. QUEUED runs on
          other tickets never count towards this cap -- counting them would
          let a batch of already-queued tickets permanently deadlock every
          future claim once the cap is reached.
        """
        claimed = False

        def fn(txn: Txn) -> None:
            nonlocal claimed
            # Reset per attempt: a retry after a lost push race re-runs fn against
            # fresh state, and only the attempt that actually lands may claim.
            claimed = False
            run = txn.get_run(ticket_id, run_id)
            if run is None or run["state"] != "QUEUED":
                return
            same_ticket_exclusive = any(
                r["run_id"] != run_id and r["state"] in _EXCLUSIVE_STATES
                for r in txn.ticket_doc(ticket_id).get("runs", [])
            )
            if same_ticket_exclusive:
                return
            if in_flight_cap is not None:
                other_in_flight = sum(
                    1
                    for tid in self.list_tickets()
                    if tid != ticket_id and self._has_exclusive_run(tid)
                )
                if other_in_flight >= in_flight_cap:
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
