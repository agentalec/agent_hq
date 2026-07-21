import json
import subprocess
from pathlib import Path

import pytest

from engine.state import GitJsonStateStore, Txn

BRANCH = "agent-hq-state"

RUN = {
    "run_id": "run-1",
    "task_id": "task-1",
    "task_version": 1,
    "ticket_id": "ticket-1",
    "state": "QUEUED",
    "attempt": 0,
    "bindings": {},
    "cost_usd": None,
    "tokens": None,
    "usage_known": False,
    "artifacts": [],
    "chain_depth": 0,
}


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout


def _make_origin(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    _git("init", "--bare", str(origin))
    seed = tmp_path / "_seed"
    _git("clone", str(origin), str(seed))
    _git("config", "user.email", "test@example.com", cwd=seed)
    _git("config", "user.name", "Test", cwd=seed)
    _git("checkout", "--orphan", BRANCH, cwd=seed)
    (seed / ".keep").write_text("")
    _git("add", ".keep", cwd=seed)
    _git("commit", "-m", "init", cwd=seed)
    _git("push", "-u", "origin", BRANCH, cwd=seed)
    return origin


def _clone_worktree(tmp_path: Path, origin: Path, name: str) -> Path:
    worktree = tmp_path / name
    _git("clone", "--branch", BRANCH, str(origin), str(worktree))
    _git("config", "user.email", "test@example.com", cwd=worktree)
    _git("config", "user.name", "Test", cwd=worktree)
    return worktree


def test_write_lands_as_one_commit_touching_three_files(tmp_path):
    origin = _make_origin(tmp_path)
    worktree = _clone_worktree(tmp_path, origin, "wt1")
    store = GitJsonStateStore(worktree)

    def fn(txn: Txn) -> None:
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None)
        txn.put_run("ticket-1", dict(RUN))
        txn.append_event(
            "ticket-1",
            {"event_id": "evt-1", "kind": "run.queued", "ticket_id": "ticket-1", "run_id": "run-1"},
        )
        txn.record_health("executor", "claude-code-headless", True, "ok")

    store.write(fn)

    log = _git("log", "--oneline", BRANCH, cwd=worktree).strip().splitlines()
    assert len(log) == 2  # seed commit + this write

    changed = _git("show", "--stat", "--format=", "HEAD", cwd=worktree)
    assert "state.json" in changed
    assert "events.jsonl" in changed
    assert "latest.json" in changed

    # pushed to origin, not just committed locally
    check = _clone_worktree(tmp_path, origin, "check")
    state = json.loads((check / "tickets" / "ticket-1" / "state.json").read_text())
    assert state["runs"][0]["run_id"] == "run-1"


def test_write_conflict_reapplies_and_keeps_both_changes(tmp_path):
    origin = _make_origin(tmp_path)
    wt1 = _clone_worktree(tmp_path, origin, "wt1")
    wt2 = _clone_worktree(tmp_path, origin, "wt2")
    store1 = GitJsonStateStore(wt1)
    store2 = GitJsonStateStore(wt2)

    # advance origin from the second clone, on a different ticket
    store2.write(lambda txn: txn.set_ticket("ticket-B", status="ACTIVE", pinned_comment_id=None))

    # wt1 is now stale relative to origin; write from it anyway
    store1.write(lambda txn: txn.set_ticket("ticket-A", status="ACTIVE", pinned_comment_id=None))

    check = _clone_worktree(tmp_path, origin, "check")
    assert (check / "tickets" / "ticket-A" / "state.json").exists()
    assert (check / "tickets" / "ticket-B" / "state.json").exists()


def test_duplicate_event_id_appended_twice_is_one_line(tmp_path):
    origin = _make_origin(tmp_path)
    worktree = _clone_worktree(tmp_path, origin, "wt1")
    store = GitJsonStateStore(worktree)
    event = {"event_id": "evt-dup", "kind": "run.queued", "ticket_id": "ticket-1", "run_id": "run-1"}

    store.write(lambda txn: txn.append_event("ticket-1", dict(event)))
    store.write(lambda txn: txn.append_event("ticket-1", dict(event)))

    lines = (worktree / "tickets" / "ticket-1" / "events.jsonl").read_text().splitlines()
    assert lines == [json.dumps(event)]

    log = _git("log", "--oneline", BRANCH, cwd=worktree).strip().splitlines()
    assert len(log) == 2  # seed commit + only the first (non-duplicate) write


def test_claim_run_queued_running_and_immutable_deadline(tmp_path):
    origin = _make_origin(tmp_path)
    worktree = _clone_worktree(tmp_path, origin, "wt1")
    store = GitJsonStateStore(worktree)

    def setup(txn: Txn) -> None:
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None)
        txn.put_run("ticket-1", dict(RUN))

    store.write(setup)

    assert store.claim_run("ticket-1", "run-1", "2026-07-18T00:00:00Z", 30) is True
    run = store.read_state("ticket-1")["runs"][0]
    assert run["state"] == "RUNNING"
    assert run["deadline"] == "2026-07-18T00:30:00Z"
    assert run["attempt_started_at"] == "2026-07-18T00:00:00Z"

    # already RUNNING: second claim is a no-op
    assert store.claim_run("ticket-1", "run-1", "2026-07-18T00:05:00Z", 30) is False

    # simulate a sweep resetting the run back to QUEUED for a fresh attempt
    store.write(lambda txn: txn.update_run("ticket-1", "run-1", state="QUEUED"))

    assert store.claim_run("ticket-1", "run-1", "2026-07-18T00:10:00Z", 30) is True
    run = store.read_state("ticket-1")["runs"][0]
    assert run["deadline"] == "2026-07-18T00:30:00Z"  # unchanged across re-claim
    assert run["attempt_started_at"] == "2026-07-18T00:10:00Z"  # refreshed


def test_missing_origin_raises(tmp_path):
    plain = tmp_path / "plain"
    _git("init", str(plain))
    _git("config", "user.email", "test@example.com", cwd=plain)
    _git("config", "user.name", "Test", cwd=plain)

    with pytest.raises(RuntimeError):
        GitJsonStateStore(plain)


def test_racing_claims_only_one_wins(tmp_path):
    """A claim that loses the push race must return False after its retry
    re-runs against fresh state (regression: stale nonlocal claimed=True)."""
    origin = _make_origin(tmp_path)
    wt_a = _clone_worktree(tmp_path, origin, "wt_a")
    wt_b = _clone_worktree(tmp_path, origin, "wt_b")
    store_a = GitJsonStateStore(wt_a)
    store_b = GitJsonStateStore(wt_b)

    def setup(txn: Txn) -> None:
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None)
        txn.put_run("ticket-1", dict(RUN))

    store_a.write(setup)
    # bring B up to date so both see the QUEUED run
    _git("pull", cwd=wt_b)

    # B claims first (wins the race); A's local view is now stale
    assert store_b.claim_run("ticket-1", "run-1", "2026-07-18T00:00:00Z", 30) is True

    check_before = _clone_worktree(tmp_path, origin, "check_before")
    log_before = _git("log", "--oneline", BRANCH, cwd=check_before).strip().splitlines()

    # A's first attempt sees stale QUEUED, push is rejected, retry sees RUNNING
    # and declines -- a declined mutation after replay must commit nothing.
    assert store_a.claim_run("ticket-1", "run-1", "2026-07-18T00:01:00Z", 30) is False

    check_after = _clone_worktree(tmp_path, origin, "check_after")
    log_after = _git("log", "--oneline", BRANCH, cwd=check_after).strip().splitlines()
    assert log_after == log_before  # no phantom commit landed on origin

    check = _clone_worktree(tmp_path, origin, "check")
    run = json.loads((check / "tickets" / "ticket-1" / "state.json").read_text())["runs"][0]
    assert run["attempt_started_at"] == "2026-07-18T00:00:00Z"  # B's claim stands


def test_artifact_round_trip(tmp_path):
    origin = _make_origin(tmp_path)
    worktree = _clone_worktree(tmp_path, origin, "wt1")
    store = GitJsonStateStore(worktree)

    store.write(
        lambda txn: txn.write_artifact("ticket-1", "run-1", "specs/ticket-1/spec.md", "hello")
    )

    assert store.artifacts_dir("ticket-1", "run-1") == (
        worktree / "tickets" / "ticket-1" / "artifacts" / "run-1"
    )
    assert store.read_artifact("ticket-1", "run-1", "specs/ticket-1/spec.md") == "hello"
    assert store.read_artifact("ticket-1", "run-1", "missing.md") is None

    # pushed to origin, not just written locally
    check = _clone_worktree(tmp_path, origin, "check")
    path = check / "tickets" / "ticket-1" / "artifacts" / "run-1" / "specs" / "ticket-1" / "spec.md"
    assert path.read_text() == "hello"


def test_pending_handoffs_and_block_persist(tmp_path):
    origin = _make_origin(tmp_path)
    worktree = _clone_worktree(tmp_path, origin, "wt1")
    store = GitJsonStateStore(worktree)

    def setup(txn: Txn) -> None:
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None)
        txn.put_run("ticket-1", dict(RUN))

    store.write(setup)

    handoff = {"key": "impl", "target_task": "implement", "reason": "ready", "source_run_id": "run-1"}
    store.write(lambda txn: txn.set_pending_handoffs("ticket-1", "run-1", [handoff]))

    state = store.read_state("ticket-1")
    assert state["runs"][0]["pending_handoffs"] == [handoff]

    store.write(
        lambda txn: txn.set_block(
            "ticket-1", reason="issue closed", source="issue_closed", interrupted_run="run-1"
        )
    )

    state = store.read_state("ticket-1")
    assert state["status"] == "BLOCKED"
    assert state["block_reason"] == "issue closed"
    assert state["block_source"] == "issue_closed"
    assert state["interrupted_run_id"] == "run-1"


def test_rejected_push_replay_converges_within_bounded_attempts(tmp_path, monkeypatch):
    origin = _make_origin(tmp_path)
    worktree = _clone_worktree(tmp_path, origin, "wt1")
    store = GitJsonStateStore(worktree)

    real_push = store._push
    calls = {"n": 0}
    rejected = subprocess.CompletedProcess(
        args=["git", "push", "--porcelain"],
        returncode=1,
        stdout=(
            "To origin\n"
            "!\trefs/heads/agent-hq-state:refs/heads/agent-hq-state\t"
            "[rejected] (non-fast-forward)\n"
            "Done\n"
        ),
        stderr="",
    )

    def flaky_push():
        calls["n"] += 1
        if calls["n"] < 3:
            return rejected
        return real_push()

    monkeypatch.setattr(store, "_push", flaky_push)

    store.write(lambda txn: txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None))

    assert calls["n"] == 3  # two simulated rejections, converges on the third
    check = _clone_worktree(tmp_path, origin, "check")
    assert (check / "tickets" / "ticket-1" / "state.json").exists()


def test_push_failure_that_is_not_a_rejection_fails_fast(tmp_path, monkeypatch):
    """Auth/network/server errors are not CAS contention -- fail immediately,
    no fetch/reset/replay."""
    origin = _make_origin(tmp_path)
    worktree = _clone_worktree(tmp_path, origin, "wt1")
    store = GitJsonStateStore(worktree)

    calls = {"n": 0}

    def failing_push():
        calls["n"] += 1
        return subprocess.CompletedProcess(
            args=["git", "push", "--porcelain"],
            returncode=128,
            stdout="",
            stderr="fatal: could not read Username for 'https://github.com': terminal prompts disabled",
        )

    monkeypatch.setattr(store, "_push", failing_push)

    with pytest.raises(RuntimeError):
        store.write(lambda txn: txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None))

    assert calls["n"] == 1
