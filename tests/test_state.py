import json
import subprocess
from pathlib import Path

import pytest

from engine import state
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
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
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


def test_write_of_unchanged_values_is_a_no_op_not_an_error(tmp_path):
    """Dirtiness is declared by the mutators, not computed -- rewriting a
    field its current value still marks the ticket dirty. `git commit` fails
    outright on an empty tree, so without the staged-diff check any caller
    that re-writes an unchanged value (the sweep's PR-comment watermark, on a
    pass that found nothing new) would raise every time."""
    origin = _make_origin(tmp_path)
    worktree = _clone_worktree(tmp_path, origin, "wt-noop")
    store = GitJsonStateStore(worktree)

    def fn(txn: Txn) -> None:
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None)

    store.write(fn)
    before = _git("log", "--oneline", BRANCH, cwd=worktree).strip().splitlines()

    store.write(fn)  # identical values -- must not raise

    assert _git("log", "--oneline", BRANCH, cwd=worktree).strip().splitlines() == before


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


def test_claim_run_two_queued_runs_same_ticket_only_one_claims(tmp_path):
    """Two concurrent claim attempts for different QUEUED runs on the SAME
    ticket: only the one that lands first may claim -- per-ticket
    exclusivity refuses the second inside claim_run's own transaction (the
    real CAS enforcement), not just via the push-race retry."""
    origin = _make_origin(tmp_path)
    wt_a = _clone_worktree(tmp_path, origin, "wt_a")
    wt_b = _clone_worktree(tmp_path, origin, "wt_b")
    store_a = GitJsonStateStore(wt_a)
    store_b = GitJsonStateStore(wt_b)

    def setup(txn: Txn) -> None:
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None)
        txn.put_run("ticket-1", {**RUN, "run_id": "run-1"})
        txn.put_run("ticket-1", {**RUN, "run_id": "run-2"})

    store_a.write(setup)
    _git("pull", cwd=wt_b)

    assert store_a.claim_run("ticket-1", "run-1", "2026-07-18T00:00:00Z", 30) is True
    # B's local view is stale (both still QUEUED); B's push loses the race,
    # replay re-reads fresh state and refuses on per-ticket exclusivity
    # (run-1 is now RUNNING on the same ticket).
    assert store_b.claim_run("ticket-1", "run-2", "2026-07-18T00:01:00Z", 30) is False

    check = _clone_worktree(tmp_path, origin, "check")
    state = json.loads((check / "tickets" / "ticket-1" / "state.json").read_text())
    states = {r["run_id"]: r["state"] for r in state["runs"]}
    assert states == {"run-1": "RUNNING", "run-2": "QUEUED"}


def test_claim_run_cap_excludes_queued_no_deadlock(tmp_path):
    """The global in-flight cap counts only OTHER tickets with a
    RUNNING/WAITING_GATE run. Other tickets that are merely QUEUED must
    never count -- else a batch of tickets already queued up to the cap
    would permanently deadlock every future claim."""
    origin = _make_origin(tmp_path)
    worktree = _clone_worktree(tmp_path, origin, "wt1")
    store = GitJsonStateStore(worktree)

    def setup(txn: Txn) -> None:
        for i in (1, 2, 3):
            tid = f"ticket-{i}"
            txn.set_ticket(tid, status="ACTIVE", pinned_comment_id=None)
            txn.put_run(tid, {**RUN, "run_id": f"run-{i}", "ticket_id": tid, "state": "QUEUED"})

    store.write(setup)

    # cap=2, but ticket-1/ticket-2 are only QUEUED -- not in-flight.
    assert store.claim_run(
        "ticket-3", "run-3", "2026-07-18T00:00:00Z", 30, in_flight_cap=2
    ) is True


def test_claim_run_cap_counts_only_running_and_waiting_gate(tmp_path):
    """Once other tickets are actually RUNNING/WAITING_GATE (in-flight, not
    just QUEUED), the global cap does refuse the claim."""
    origin = _make_origin(tmp_path)
    worktree = _clone_worktree(tmp_path, origin, "wt1")
    store = GitJsonStateStore(worktree)

    def setup(txn: Txn) -> None:
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None)
        txn.put_run("ticket-1", {**RUN, "run_id": "run-1", "ticket_id": "ticket-1", "state": "RUNNING"})
        txn.set_ticket("ticket-2", status="ACTIVE", pinned_comment_id=None)
        txn.put_run(
            "ticket-2",
            {**RUN, "run_id": "run-2", "ticket_id": "ticket-2", "state": "WAITING_GATE"},
        )
        txn.set_ticket("ticket-3", status="ACTIVE", pinned_comment_id=None)
        txn.put_run("ticket-3", {**RUN, "run_id": "run-3", "ticket_id": "ticket-3", "state": "QUEUED"})

    store.write(setup)

    assert store.claim_run(
        "ticket-3", "run-3", "2026-07-18T00:00:00Z", 30, in_flight_cap=2
    ) is False
    run3 = store.read_state("ticket-3")["runs"][0]
    assert run3["state"] == "QUEUED"


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
        lambda txn: txn.write_artifact("ticket-1", "run-1", "specs/ticket-1/spec.md", b"hello")
    )

    assert store.artifacts_dir("ticket-1", "run-1") == (
        worktree / "tickets" / "ticket-1" / "artifacts" / "run-1"
    )
    assert store.read_artifact("ticket-1", "run-1", "specs/ticket-1/spec.md") == b"hello"
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


def test_replay_gives_up_loudly_after_the_bounded_attempts(tmp_path, monkeypatch):
    """A writer that never wins the CAS raises rather than silently dropping
    its write. The bound is what makes the replay safe to lean on now that the
    credentialed jobs no longer pre-serialize themselves."""
    origin = _make_origin(tmp_path)
    store = GitJsonStateStore(_clone_worktree(tmp_path, origin, "wt1"))
    calls = {"n": 0}

    def always_rejected():
        calls["n"] += 1
        return subprocess.CompletedProcess(
            args=["git", "push", "--porcelain"],
            returncode=1,
            stdout=(
                "To origin\n"
                "!\trefs/heads/agent-hq-state:refs/heads/agent-hq-state\t"
                "[rejected] (non-fast-forward)\n"
                "Done\n"
            ),
            stderr="still contended",
        )

    monkeypatch.setattr(store, "_push", always_rejected)
    monkeypatch.setattr(state, "_retry_backoff_seconds", lambda attempt: 0)

    with pytest.raises(RuntimeError, match="rejected after"):
        store.write(lambda txn: txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None))

    assert calls["n"] == state._MAX_WRITE_ATTEMPTS


def test_replay_reruns_fn_so_a_losing_attempt_leaves_no_trace(tmp_path, monkeypatch):
    """The replay re-runs `fn` from scratch against fresh state, so anything
    `fn` records in an enclosing scope ACCUMULATES across attempts unless it
    clears first. Only the attempt that actually lands may decide anything.

    `claim_run` resets its `claimed` flag for exactly this reason, and so does
    `engine.engine.poll_pr_feedback`'s `result`. This is the contract for the
    next caller that closes over one: state written by an attempt that lost
    the push race must not outlive it."""
    origin = _make_origin(tmp_path)
    store = GitJsonStateStore(_clone_worktree(tmp_path, origin, "wt-replay"))
    real_push = store._push
    pushes = {"n": 0}

    def reject_first_push():
        pushes["n"] += 1
        if pushes["n"] > 1:
            return real_push()
        return subprocess.CompletedProcess(
            args=["git", "push", "--porcelain"],
            returncode=1,
            stdout=(
                "To origin\n"
                "!\trefs/heads/agent-hq-state:refs/heads/agent-hq-state\t"
                "[rejected] (non-fast-forward)\n"
                "Done\n"
            ),
            stderr="contended",
        )

    monkeypatch.setattr(store, "_push", reject_first_push)
    monkeypatch.setattr(state, "_retry_backoff_seconds", lambda attempt: 0)

    result: dict = {}
    attempts = {"n": 0}

    def fn(txn: Txn) -> None:
        result.clear()  # the discipline under test
        attempts["n"] += 1
        result[f"attempt-{attempts['n']}"] = True
        txn.set_ticket("ticket-1", status="ACTIVE", pinned_comment_id=None)

    store.write(fn)

    assert attempts["n"] == 2, "the rejected push must have replayed fn"
    assert result == {"attempt-2": True}, "the losing attempt left state behind"


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
