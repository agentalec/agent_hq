"""`tracker` port adapter (D4): `github-issues`, PAT auth.

Settings: `{"repo": "org/repo"}` -- the intake repo, used for every op except
`fetch_ticket`, whose `ref` may name its own repo (`"org/repo#123"`).
"""

from __future__ import annotations

from engine.adapters._github import GitHubClient
from engine.models import Event, TicketDetails

PINNED_MARKER = "<!--hq:pinned-->"
HQ_LABEL_PREFIX = "hq:"


def _event_marker(event_id: str) -> str:
    return f"<!--hq:evt:{event_id}-->"


class GithubIssuesTracker:
    def __init__(self, settings: dict):
        self.settings = settings
        self.repo = settings.get("repo")
        self._client = GitHubClient()
        self._applied_events: set[str] = set()

    def _require_repo(self) -> str:
        if not self.repo:
            raise ValueError("settings missing 'repo' (intake repo full name)")
        return self.repo

    def _split_ref(self, ref: str) -> tuple[str, str]:
        if "#" in ref:
            repo, number = ref.split("#", 1)
            return repo, number
        return self._require_repo(), ref

    def fetch_ticket(self, ref: str) -> TicketDetails:
        repo, number = self._split_ref(ref)
        issue = self._client.get(f"/repos/{repo}/issues/{number}")
        return TicketDetails(
            ticket_id=str(issue["number"]),
            title=issue["title"],
            body=issue.get("body") or "",
            labels=[label["name"] for label in issue.get("labels", [])],
        )

    def parse_event(self, payload: dict, event_key: str) -> Event | None:
        issue = payload.get("issue")
        if not issue:
            return None
        return Event(
            event_id=f"intake:{event_key}",
            kind="ticket.event",
            ticket_id=str(issue["number"]),
            run_id="",
        )

    def set_status_labels(self, ticket_id: str, status: str, labels: list[str]) -> None:
        # ponytail: `status` isn't consulted -- `labels` already carries the
        # full desired hq:-owned set; kept for Tracker protocol parity.
        repo = self._require_repo()
        issue = self._client.get(f"/repos/{repo}/issues/{ticket_id}")
        current = [label["name"] for label in issue.get("labels", [])]
        human = [name for name in current if not name.startswith(HQ_LABEL_PREFIX)]
        current_hq = sorted(name for name in current if name.startswith(HQ_LABEL_PREFIX))
        desired_hq = sorted(name for name in labels if name.startswith(HQ_LABEL_PREFIX))
        if current_hq == desired_hq:
            return
        self._client.patch(
            f"/repos/{repo}/issues/{ticket_id}", json={"labels": human + desired_hq}
        )

    def upsert_pinned_comment(self, ticket_id: str, body: str, event_id: str) -> str | int:
        repo = self._require_repo()
        marker = _event_marker(event_id)
        # ponytail: first 100 comments only; Link-header pagination if a ticket outgrows it
        comments = (
            self._client.get(
                f"/repos/{repo}/issues/{ticket_id}/comments", params={"per_page": 100}
            )
            or []
        )
        pinned = next((c for c in comments if PINNED_MARKER in c.get("body", "")), None)

        if pinned and (event_id in self._applied_events or marker in pinned["body"]):
            self._applied_events.add(event_id)
            return pinned["id"]

        full_body = f"{PINNED_MARKER}\n{marker}\n{body}"
        if pinned:
            result = self._client.patch(
                f"/repos/{repo}/issues/comments/{pinned['id']}", json={"body": full_body}
            )
        else:
            result = self._client.post(
                f"/repos/{repo}/issues/{ticket_id}/comments", json={"body": full_body}
            )
        self._applied_events.add(event_id)
        return result["id"]

    def post_closing_summary(self, ticket_id: str, body: str, event_id: str) -> None:
        repo = self._require_repo()
        marker = _event_marker(event_id)
        if event_id in self._applied_events:
            return
        comments = (
            self._client.get(
                f"/repos/{repo}/issues/{ticket_id}/comments", params={"per_page": 100}
            )
            or []
        )
        if any(marker in c.get("body", "") for c in comments):
            self._applied_events.add(event_id)
            return
        self._client.post(
            f"/repos/{repo}/issues/{ticket_id}/comments", json={"body": f"{marker}\n{body}"}
        )
        self._applied_events.add(event_id)

    def healthcheck(self) -> bool:
        try:
            self._client.get("/rate_limit")
            return True
        except Exception:
            return False
