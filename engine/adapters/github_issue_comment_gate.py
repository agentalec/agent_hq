"""`gate` port adapter: `github-issue-comment` -- the default/spec-approval
P0 binding (D2 still holds: every P0 gate is a post-gate). Approval happens
as an authorized comment on the parent (engine-repository) issue, per the
`/agent-hq approve|request-changes|reject <run-id> [reason]` grammar
(`docs/architecture.md` "Approval and reopen commands").

Settings: `{"issue_repo": "org/engine-repo", "approvers": <approvers.yml
dict>}` -- `issue_repo` is injected by `engine.engine.build_port_adapter`
from `intake_repo(config)`, distinct from the (ignored, work-repo) `repo`
key `pr-review` uses. `request`/`status` write no state -- `status` only
REPORTS a decision's audit metadata (comment id, actor, time) on the
returned `GateDecision`; the engine appends the deduped approval event
itself, in the same write that advances the run.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from engine.adapters._github import GitHubClient
from engine.adapters.pr_review import add_working_hours
from engine.models import GateDecision, GateRequest, GateStatus

_MARKER = "<!--hq:gate:{run_id}-->"
# A spec is a few KB; the cap is a guard against a runaway artifact blowing
# GitHub's 65536-char comment limit, not an expected path.
_MAX_EMBED_CHARS = 20000
# Where the ledger copy of an artifact is readable from. The state branch is
# a fixed name across the engine (scripts/checkout-state.sh creates it).
_STATE_BRANCH = "agent-hq-state"
_DECISION_RE = re.compile(r"^/agent-hq (approve|request-changes|reject)(?:\s+(.*))?$")
# `compute_run_id` is sha1[:16] -- what tells an explicit target apart from
# the first word of a reason.
_RUN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_STATUS_BY_COMMAND = {
    "approve": GateStatus.APPROVED,
    "request-changes": GateStatus.CHANGES_REQUESTED,
    "reject": GateStatus.REJECTED,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_decision(body: str, run_id: str) -> tuple[str, str] | None:
    """First `/agent-hq <command> [<run-id>] [reason]` line in `body`, as
    `(command, reason)`, or None if no line decides THIS run.

    The run id is optional: a bare `/agent-hq approve` targets whatever gate
    is currently open, since per-ticket exclusivity means at most one run is
    WAITING_GATE at a time. What makes that safe is the caller's
    `gate_requested_at` cutoff -- without it, a bare approval left in the
    thread would silently satisfy every future gate on the ticket.

    An explicit id that isn't this run's is a decision about a different
    gate, so that line is skipped rather than read as a bare command whose
    reason happens to start with an id."""
    for line in body.splitlines():
        match = _DECISION_RE.match(line.strip())
        if not match:
            continue
        command, rest = match.group(1), (match.group(2) or "").strip()
        head, _, tail = rest.partition(" ")
        if head == run_id:
            return command, tail.strip()
        if _RUN_ID_RE.match(head):
            continue
        return command, rest
    return None


def _artifact_sections(artifacts: dict, issue_repo: str) -> list[str]:
    """Inline every artifact the gated run produced, each in a collapsed
    block over a link to its ledger copy. An approver has to be able to read
    what they are approving from the issue thread itself -- a run id and a
    ticket title are not a reviewable subject. The link sits OUTSIDE the
    collapsed block, and is always present rather than only on truncation:
    it is the only way to read the rest of an artifact too big to inline,
    and a permanent reference to the exact copy this gate was asked about."""
    lines: list[str] = []
    for path, entry in sorted(artifacts.items()):
        content = entry.get("content") or ""
        if len(content) > _MAX_EMBED_CHARS:
            content = (
                content[:_MAX_EMBED_CHARS]
                + f"\n\n_[truncated at {_MAX_EMBED_CHARS} characters — read the rest "
                "via the link below]_"
            )
        lines += [
            "",
            f"<details><summary><b>{path}</b></summary>",
            "",  # blank line required, else GitHub renders the body as raw text
            content,
            "",
            "</details>",
        ]
        ledger_path = entry.get("ledger_path")
        if ledger_path:
            lines.append(
                f"[`{path}` on the `{_STATE_BRANCH}` branch]"
                f"(https://github.com/{issue_repo}/blob/{_STATE_BRANCH}/{ledger_path})"
            )
    return lines


class GithubIssueCommentGate:
    def __init__(self, settings: dict):
        self.settings = settings
        self.issue_repo = settings.get("issue_repo")
        self.approvers = settings.get("approvers") or {}
        self._client = GitHubClient()

    def _require_issue_repo(self) -> str:
        if not self.issue_repo:
            raise ValueError("settings missing 'issue_repo' (engine issue repo)")
        return self.issue_repo

    def _list_comments(self, repo: str, ticket_id: str) -> list[dict]:
        """All issue comments, paginated -- a dedupe marker or decision can
        land on any page once an issue accumulates more than one page of
        comments (GitHubClient exposes no Link header, so pagination stops
        the standard way: a short page is the last page)."""
        comments: list[dict] = []
        page = 1
        while True:
            batch = (
                self._client.get(
                    f"/repos/{repo}/issues/{ticket_id}/comments",
                    params={"per_page": 100, "page": page},
                )
                or []
            )
            comments.extend(batch)
            if len(batch) < 100:
                return comments
            page += 1

    def request(self, group: str, subject: dict) -> GateRequest:
        repo = self._require_issue_repo()
        ticket_id = subject["ticket_id"]
        run_id = subject["run_id"]
        marker = _MARKER.format(run_id=run_id)

        comments = self._list_comments(repo, ticket_id)
        existing = next((c for c in comments if marker in (c.get("body") or "")), None)
        if existing:
            return GateRequest(request_id=str(existing["id"]))

        members = self.approvers.get("groups", {}).get(group, {}).get("members", [])
        mentions = " ".join(f"@{m}" for m in members)
        auto = bool(subject.get("auto_approved"))

        # An auto-approved gate posts the same comment -- it is where the run's
        # artifacts become readable -- but as a record, not a request: no
        # decision grammar, and no @-mention of a group with nothing to decide.
        if auto:
            heading = f"### Gate auto-approved: `{subject.get('task_id', '')}` ({run_id})"
            footer = [
                "",
                f"_Decided by task config (`auto_approve`), not by a human. Would "
                f"otherwise have asked `{group}`. No action needed._",
            ]
        else:
            heading = f"### Approval requested: `{subject.get('task_id', '')}` ({run_id})"
            footer = [
                "",
                mentions,
                "",
                "Reply on this issue:",
                "- `/agent-hq approve`",
                "- `/agent-hq request-changes <reason>`",
                "- `/agent-hq reject <reason>`",
                "",
                f"<sub>Decides the gate open on this ticket. Add the run id "
                f"(`/agent-hq approve {run_id}`) to be explicit.</sub>",
            ]

        body = "\n".join(
            [marker, heading, "", subject.get("title", "")]
            + _artifact_sections(subject.get("artifacts") or {}, repo)
            + footer
        )
        result = self._client.post(f"/repos/{repo}/issues/{ticket_id}/comments", json={"body": body})
        return GateRequest(request_id=str(result["id"]))

    def status(self, run: dict) -> GateDecision:
        repo = self._require_issue_repo()
        ticket_id = run["ticket_id"]
        run_id = run["run_id"]
        approver_group = run.get("approver_group")
        members = set(self.approvers.get("groups", {}).get(approver_group, {}).get("members", []))

        # Only comments from this gate's request onward can decide it. This is
        # what lets the run id be optional: every sweep re-reads the whole
        # thread, so without the cutoff a decision left behind by an earlier
        # gate on this ticket (a reworked spec, an earlier task's approval)
        # would silently satisfy this one -- approving something no human read.
        requested_at = run.get("gate_requested_at")

        comments = self._list_comments(repo, ticket_id)
        decisions = []
        for comment in comments:
            created_at = comment.get("created_at") or ""
            if requested_at and created_at < requested_at:
                continue
            parsed = _parse_decision(comment.get("body") or "", run_id)
            if not parsed:
                continue
            command, reason = parsed
            if comment["user"]["login"] not in members:
                continue
            decisions.append((created_at, command, reason, comment))

        if decisions:
            decisions.sort(key=lambda d: d[0])
            _, command, reason, comment = decisions[-1]
            return GateDecision(
                _STATUS_BY_COMMAND[command],
                reason,
                comment_id=comment["id"],
                actor=comment["user"]["login"],
                decided_at=comment.get("created_at"),
            )

        timeout_hours = run.get("timeout_working_hours")
        if timeout_hours is not None and run.get("gate_requested_at"):
            schedule = self.approvers.get("working_hours") or {}
            deadline = add_working_hours(run["gate_requested_at"], timeout_hours, schedule)
            if _now_iso() >= deadline:
                return GateDecision(GateStatus.EXPIRED, "")

        return GateDecision(GateStatus.PENDING, "")

    def healthcheck(self) -> bool:
        try:
            self._client.get("/rate_limit")
            return True
        except Exception:
            return False
