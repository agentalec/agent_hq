"""The `/agent-hq` comment grammar (`docs/architecture.md` "Approval and
reopen commands").

Engine-owned, not tracker-owned: the same command decides a gate on the
engine issue (`github-issue-comment`) and sends work back from a work-repo
PR (`engine.engine.poll_pr_feedback`). It lives here rather than in either
caller because engine code may not import a concrete adapter
(`tests/test_config_swap.py`), and duplicating a security-relevant parser is
how the two copies drift.
"""

from __future__ import annotations

import re

from engine.models import GateStatus

DECISION_RE = re.compile(r"^/agent-hq (approve|request-changes|reject)(?:\s+(.*))?$")
# `compute_run_id` is sha1[:16] -- what tells an explicit target apart from
# the first word of a reason.
RUN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
STATUS_BY_COMMAND = {
    "approve": GateStatus.APPROVED,
    "request-changes": GateStatus.CHANGES_REQUESTED,
    "reject": GateStatus.REJECTED,
}


def parse_decision(body: str, run_id: str) -> tuple[str, str] | None:
    """First `/agent-hq <command> [<run-id>] [reason]` line in `body`, as
    `(command, reason)`, or None if no line decides THIS run.

    The run id is optional: a bare `/agent-hq approve` targets whatever gate
    is currently open, since per-ticket exclusivity means at most one run is
    WAITING_GATE at a time. What makes that safe is the caller's
    `gate_requested_at` cutoff -- without it, a bare approval left in the
    thread would silently satisfy every future gate on the ticket.

    An explicit id that isn't this run's is a decision about a different
    gate, so that line is skipped rather than read as a bare command whose
    reason happens to start with an id.

    A caller with no run to decide (the PR-comment poll) passes `run_id=""`:
    a bare command then applies, and an id-qualified one is skipped -- right,
    because an id-qualified decision is about an issue-thread gate.
    """
    for line in body.splitlines():
        match = DECISION_RE.match(line.strip())
        if not match:
            continue
        command, rest = match.group(1), (match.group(2) or "").strip()
        head, _, tail = rest.partition(" ")
        if head == run_id:
            return command, tail.strip()
        if RUN_ID_RE.match(head):
            continue
        return command, rest
    return None
