"""Domain models for the agent-hq engine.

TaskRun and Event mirror schemas/state.schema.json ($defs/run) and
schemas/event.schema.json respectively -- keep these in sync with the
schema files when either changes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, fields
from enum import Enum


def _to_dict_omit_none_optionals(obj) -> dict:
    """asdict(), but drop optional (default=None) fields whose value is None.

    Required fields keep their key even when the value is None (some, like
    cost_usd, are required-but-nullable per the schema).
    """
    d = {}
    for f in fields(obj):
        value = getattr(obj, f.name)
        if f.default is None and value is None:
            continue
        d[f.name] = value
    return d


class RunState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_GATE = "WAITING_GATE"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    # A QUEUED entry removed from the queue before it ran. Terminal, and in
    # neither NON_TERMINAL nor EXCLUSIVE_STATES: it holds no in_flight slot and
    # does not keep a ticket from completing. Runs are never deleted -- `runs`
    # is the audit trail -- so removal is a state, not an erasure.
    CANCELLED = "CANCELLED"


class GateStatus(str, Enum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"


class TicketStatus(str, Enum):
    ACTIVE = "ACTIVE"
    # Queue drained and the closing summary posted, but the work PRs are not
    # resolved yet -- the issue stays OPEN and the sweep watches the PRs
    # (engine.engine.resolve_awaiting_merge). No run is exclusive here, so an
    # AWAITING_MERGE ticket holds no in_flight_cap slot.
    AWAITING_MERGE = "AWAITING_MERGE"
    BLOCKED = "BLOCKED"
    DONE = "DONE"


@dataclass
class GateDecision:
    status: GateStatus
    comments: str
    # Audit metadata a comment-based gate (github_issue_comment_gate) attaches
    # to its decision; unused (None) by a PR-review-style gate. The adapter
    # only reports this -- the engine appends the deduped audit event.
    comment_id: str | int | None = None
    actor: str | None = None
    decided_at: str | None = None


@dataclass
class GateRequest:
    request_id: str


@dataclass(frozen=True)
class TicketDetails:
    """A tracker-fetched view of a ticket (title/body/labels).

    Distinct from `Ticket`, which mirrors the persisted state.schema.json
    ticket document and carries no source-tracker content.
    """

    ticket_id: str
    title: str
    body: str
    labels: list[str]


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    pinned_comment_id: str | int | None
    status: TicketStatus
    block_reason: str | None = None
    block_source: str | None = None
    interrupted_run_id: str | None = None
    # Watermark for the engine-issue comment poll (ticket-level control
    # surface); the per-work_repo field of the same name tracks each PR thread.
    comments_polled_at: str | None = None
    work_repos: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "pinned_comment_id": self.pinned_comment_id,
            "status": self.status.value,
            "block_reason": self.block_reason,
            "block_source": self.block_source,
            "interrupted_run_id": self.interrupted_run_id,
            "comments_polled_at": self.comments_polled_at,
            "work_repos": list(self.work_repos),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Ticket:
        return cls(
            ticket_id=data["ticket_id"],
            pinned_comment_id=data.get("pinned_comment_id"),
            status=TicketStatus(data["status"]),
            block_reason=data.get("block_reason"),
            block_source=data.get("block_source"),
            interrupted_run_id=data.get("interrupted_run_id"),
            comments_polled_at=data.get("comments_polled_at"),
            work_repos=data.get("work_repos", []),
        )


@dataclass(frozen=True)
class Budget:
    max_cost_usd: float
    max_runtime_min: float
    retries: int


@dataclass(frozen=True)
class Handoff:
    """A proposed child run, mirroring schemas/state.schema.json $defs/handoff.

    Identity for a spawned run is (source_run_id, key, attempt) -- task_id is
    not part of it, so a re-delivered key with a different target yields the
    same run id (see PLAN.md handoff-identity note).
    """

    key: str
    target_task: str
    reason: str
    repo: str | None = None
    artifacts: list[str] | None = None
    source_run_id: str | None = None

    def to_dict(self) -> dict:
        return _to_dict_omit_none_optionals(self)

    @classmethod
    def from_dict(cls, data: dict) -> Handoff:
        return cls(**data)


@dataclass(frozen=True)
class TaskRun:
    run_id: str
    task_id: str
    task_version: int
    ticket_id: str
    state: RunState
    attempt: int
    bindings: dict[str, str]
    cost_usd: float | None
    tokens: int | None
    usage_known: bool
    artifacts: list[str]
    chain_depth: int
    deadline: str | None = None
    attempt_started_at: str | None = None
    gate_requested_at: str | None = None
    gate_request_id: str | int | None = None
    base_commit: str | None = None
    output_commit: str | None = None
    pr_ref: str | None = None
    parent_run_id: str | None = None
    source_event_id: str | None = None
    enqueue_index: int | None = None
    # The run whose recorded artifacts this run consumed -- resolved and
    # recorded at claim (nearest SUCCEEDED run ahead of it in the queue, else
    # the enqueuer). NOT parent_run_id: a run may declare several queue entries
    # at once, so whoever enqueued `review` need not be who produced its input.
    input_from_run_id: str | None = None
    # Queue position (schemas/state.schema.json queue_seq). Dispatch orders
    # QUEUED runs by it; absent on runs written before it existed, where
    # readers fall back to array index -- the order dispatch used then.
    queue_seq: int | None = None
    handoff_key: str | None = None
    repo: str | None = None
    input_artifacts: list[str] | None = None
    pending_handoffs: list[Handoff] | None = None

    def to_dict(self) -> dict:
        d = _to_dict_omit_none_optionals(self)
        d["state"] = self.state.value
        if self.pending_handoffs is not None:
            d["pending_handoffs"] = [h.to_dict() for h in self.pending_handoffs]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> TaskRun:
        d = dict(data)
        d["state"] = RunState(d["state"])
        if d.get("pending_handoffs") is not None:
            d["pending_handoffs"] = [Handoff.from_dict(h) for h in d["pending_handoffs"]]
        return cls(**d)


@dataclass(frozen=True)
class Event:
    event_id: str
    kind: str
    ticket_id: str
    run_id: str
    task_id: str | None = None
    task_version: int | None = None
    state: RunState | None = None
    duration_seconds: float | None = None
    tokens: int | None = None
    cost_usd: float | None = None
    bindings: dict[str, str] | None = None
    run_url: str | None = None
    artifacts: list[str] | None = None
    detail: str | None = None
    # Audit provenance. `actor` is a tracker login for a human decision, or
    # "engine" where the engine decided autonomously and that IS the audit
    # fact (auto-approved gate); omitted for mechanical engine bookkeeping,
    # so absence is the answer rather than a gap. `source` names what carried
    # the cause -- comment id, intake event key, run id -- so a decision is
    # traceable without parsing `detail`.
    actor: str | None = None
    source: str | None = None

    def to_dict(self) -> dict:
        d = _to_dict_omit_none_optionals(self)
        if self.state is not None:
            d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Event:
        d = dict(data)
        if d.get("state") is not None:
            d["state"] = RunState(d["state"])
        return cls(**d)


def compute_run_id(parent_or_source: str, enqueue_index: int, task_id: str, attempt: int) -> str:
    """Deterministic run id: sha1 of the component tuple, first 16 hex chars.

    repr() of the tuple is unambiguous — a "|" (or any separator) embedded in a
    string component cannot collide with the component boundary.
    """
    joined = repr((parent_or_source, enqueue_index, task_id, attempt))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def compute_handoff_run_id(source_run_id: str, handoff_key: str, attempt: int) -> str:
    """Deterministic run id for a handoff-spawned run: (source_run_id,
    handoff_key, attempt) only -- task_id is deliberately NOT part of it, so
    a re-delivered key with a different target still yields the SAME run id
    (the first accepted run wins; the mutation is a no-op). Retries of the
    same handoff reuse `handoff_key` at a higher `attempt`.
    """
    joined = repr((source_run_id, handoff_key, attempt))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]
