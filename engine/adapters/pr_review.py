"""`gate` port adapter (D2): `pr-review`, the only P0 gate -- and, per D2,
every P0 gate is a post-gate (no native-approval dual path; see
`docs/ports/gate.md`).

Settings: `{"repo": "org/repo", "approvers": <approvers.yml dict>,
"default_base": "main"}` -- `approvers` carries `groups` (group name ->
`{"members": [...]}`) and `working_hours` (timezone/start/end/days), used by
`request` to resolve reviewers and by `status` to compute the working-hours
expiry deadline.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from engine.adapters._github import GitHubClient, open_draft_pr, request_reviewers
from engine.models import GateDecision, GateRequest, GateStatus

_DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_working_moment(
    cur: datetime, start_hour: int, end_hour: int, days: set[str]
) -> datetime:
    """`cur` (already in the schedule's timezone) rolled forward to the next
    instant that falls inside a working day's [start, end) window."""
    while True:
        if _DAY_ABBR[cur.weekday()] in days:
            day_start = cur.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            day_end = cur.replace(hour=end_hour, minute=0, second=0, microsecond=0)
            if cur < day_start:
                return day_start
            if cur < day_end:
                return cur
        cur = (cur + timedelta(days=1)).replace(
            hour=start_hour, minute=0, second=0, microsecond=0
        )


def add_working_hours(start_iso: str, hours: float, schedule: dict) -> str:
    """Deadline `hours` working-hours after `start_iso`, counting only hours
    inside `schedule`'s [start, end) window on its listed days, in its
    timezone. A start outside that window rolls forward to the next working
    moment before counting begins. Returns a UTC ISO deadline.
    """
    tz = ZoneInfo(schedule["timezone"])
    start_hour = schedule["start"]
    end_hour = schedule["end"]
    days = set(schedule["days"])
    if not days or start_hour >= end_hour:
        raise ValueError(
            f"degenerate working_hours schedule (days={sorted(days)}, "
            f"start={start_hour}, end={end_hour}): no working time can ever elapse"
        )

    start_dt = datetime.strptime(start_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    cur = _next_working_moment(start_dt.astimezone(tz), start_hour, end_hour, days)

    remaining = hours
    while remaining > 0:
        day_end = cur.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        available = (day_end - cur).total_seconds() / 3600
        if remaining <= available:
            cur += timedelta(hours=remaining)
            remaining = 0
        else:
            remaining -= available
            nxt = (cur + timedelta(days=1)).replace(
                hour=start_hour, minute=0, second=0, microsecond=0
            )
            cur = _next_working_moment(nxt, start_hour, end_hour, days)

    return cur.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PrReviewGate:
    def __init__(self, settings: dict):
        self.settings = settings
        self.repo = settings.get("repo")
        self.default_base = settings.get("default_base", "main")
        self.approvers = settings.get("approvers") or {}
        self._client = GitHubClient()

    def request(self, group: str, subject: dict) -> GateRequest:
        repo = subject.get("repo") or self.repo
        if not repo:
            raise ValueError("pr-review request needs subject['repo'] or settings['repo']")
        branch = subject["branch"]
        pr = open_draft_pr(
            self._client,
            repo,
            branch,
            self.default_base,
            subject.get("title") or f"hq: {subject.get('ticket_id', '')}",
            subject.get("body", ""),
        )

        members = self.approvers.get("groups", {}).get(group, {}).get("members", [])
        request_reviewers(self._client, repo, pr["number"], members)

        return GateRequest(request_id=str(pr["number"]))

    def status(self, run: dict) -> GateDecision:
        pr_number = run["gate_request_id"]
        reviews = self._client.get(f"/repos/{self.repo}/pulls/{pr_number}/reviews") or []

        # Only the configured approver group may authorize this gate --
        # anyone else's review is discarded before the decision is made.
        approver_group = run.get("approver_group")
        members = set(
            self.approvers.get("groups", {}).get(approver_group, {}).get("members", [])
        )

        latest: dict[str, dict] = {}
        for review in reviews:
            user = review["user"]["login"]
            if user not in members:
                continue
            submitted_at = review.get("submitted_at") or ""
            if user not in latest or submitted_at >= (latest[user].get("submitted_at") or ""):
                latest[user] = review
        latest_reviews = list(latest.values())

        changes_requested = [r for r in latest_reviews if r["state"] == "CHANGES_REQUESTED"]
        if changes_requested:
            comments = "\n\n".join(r.get("body") or "" for r in changes_requested)
            return GateDecision(GateStatus.CHANGES_REQUESTED, comments)
        if any(r["state"] == "APPROVED" for r in latest_reviews):
            return GateDecision(GateStatus.APPROVED, "")

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
