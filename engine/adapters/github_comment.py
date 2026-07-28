"""`messaging` port adapter (D4): `github-comment`, PAT auth.

Settings: `{"repo": "org/repo"}` -- the repo whose issues carry notifications.
`audience` is `{"ticket_id": <issue number>, "mentions": [<login>, ...]}`.
"""

from __future__ import annotations

from engine.adapters._github import GitHubClient


def _event_marker(event_id: str) -> str:
    return f"<!--hq:evt:{event_id}-->"


class GithubCommentMessaging:
    def __init__(self, settings: dict):
        self.settings = settings
        self.repo = settings.get("repo")
        if not self.repo:
            raise ValueError("github-comment messaging requires settings['repo']")
        self._client = GitHubClient()

    def notify(self, audience: dict, message: str, links: list[str], event_id: str) -> None:
        repo = self.repo
        ticket_id = audience.get("ticket_id")
        if not ticket_id:
            raise ValueError("notify audience requires 'ticket_id'")
        marker = _event_marker(event_id)
        # ponytail: first 100 comments only; Link-header pagination if a ticket outgrows it
        comments = (
            self._client.get(
                f"/repos/{repo}/issues/{ticket_id}/comments", params={"per_page": 100}
            )
            or []
        )
        if any(marker in c.get("body", "") for c in comments):
            return

        parts = [marker]
        mentions = audience.get("mentions") or []
        if mentions:
            parts.append(" ".join(f"@{m}" for m in mentions))
        parts.append(message)
        if links:
            parts.append("\n".join(f"- {link}" for link in links))
        body = "\n\n".join(parts)

        self._client.post(f"/repos/{repo}/issues/{ticket_id}/comments", json={"body": body})

    def healthcheck(self) -> bool:
        try:
            self._client.get("/rate_limit")
            return True
        except Exception:  # noqa: BLE001 -- any failure means unhealthy, by design
            return False
