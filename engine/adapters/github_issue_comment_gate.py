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
_DECISION_RE = re.compile(r"^/agent-hq (approve|request-changes|reject)\s+(\S+)(?:\s+(.*))?$")
_STATUS_BY_COMMAND = {
    "approve": GateStatus.APPROVED,
    "request-changes": GateStatus.CHANGES_REQUESTED,
    "reject": GateStatus.REJECTED,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_decision(body: str) -> tuple[str, str, str] | None:
    """First `/agent-hq <command> <run-id> [reason]` line in `body`, or None."""
    for line in body.splitlines():
        match = _DECISION_RE.match(line.strip())
        if match:
            command, run_id, reason = match.group(1), match.group(2), match.group(3) or ""
            return command, run_id, reason.strip()
    return None


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

    def request(self, group: str, subject: dict) -> GateRequest:
        repo = self._require_issue_repo()
        ticket_id = subject["ticket_id"]
        run_id = subject["run_id"]
        marker = _MARKER.format(run_id=run_id)

        comments = (
            self._client.get(
                f"/repos/{repo}/issues/{ticket_id}/comments", params={"per_page": 100}
            )
            or []
        )
        existing = next((c for c in comments if marker in (c.get("body") or "")), None)
        if existing:
            return GateRequest(request_id=str(existing["id"]))

        members = self.approvers.get("groups", {}).get(group, {}).get("members", [])
        mentions = " ".join(f"@{m}" for m in members)
        body = "\n".join(
            [
                marker,
                f"### Approval requested: `{subject.get('task_id', '')}` ({run_id})",
                "",
                subject.get("title", ""),
                "",
                mentions,
                "",
                "Reply on this issue:",
                f"- `/agent-hq approve {run_id}`",
                f"- `/agent-hq request-changes {run_id} <reason>`",
                f"- `/agent-hq reject {run_id} <reason>`",
            ]
        )
        result = self._client.post(f"/repos/{repo}/issues/{ticket_id}/comments", json={"body": body})
        return GateRequest(request_id=str(result["id"]))

    def status(self, run: dict) -> GateDecision:
        repo = self._require_issue_repo()
        ticket_id = run["ticket_id"]
        run_id = run["run_id"]
        approver_group = run.get("approver_group")
        members = set(self.approvers.get("groups", {}).get(approver_group, {}).get("members", []))

        comments = (
            self._client.get(
                f"/repos/{repo}/issues/{ticket_id}/comments", params={"per_page": 100}
            )
            or []
        )
        decisions = []
        for comment in comments:
            parsed = _parse_decision(comment.get("body") or "")
            if not parsed:
                continue
            command, target_run, reason = parsed
            if target_run != run_id:
                continue
            if comment["user"]["login"] not in members:
                continue
            decisions.append((comment.get("created_at") or "", command, reason, comment))

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
