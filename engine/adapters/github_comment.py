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

    def react(self, comment_id: str | int, content: str) -> None:
        """Add a reaction to one issue/PR comment.

        Idempotent at the API: the same content from the same identity returns
        the existing reaction rather than adding a second. That is the whole
        reason the poller signals with reactions instead of replies -- the
        watermark is inclusive at the boundary second, so a comment can be
        re-read, and a reply would duplicate where a reaction cannot.
        """
        self._client.post(
            f"/repos/{self.repo}/issues/comments/{comment_id}/reactions",
            json={"content": content},
        )

    def list_comments(self, subject_id: str, since: str | None = None) -> list[dict]:
        """Comments on `subject_id` (an issue or PR number in this adapter's
        repo -- a PR is an issue), oldest first, as
        `{"id", "body", "author", "created_at"}`.

        The read half of the same work-repo pairing `notify` writes: the
        sweep polls a work PR for authorized `/agent-hq` commands, which is
        the only way review feedback reaches the engine (the engine
        repository cannot receive product-repo events).

        `since` is passed to GitHub, so an already-polled window costs one
        near-empty response rather than a full re-read. It is a watermark,
        not the dedupe -- the caller still dedupes by comment id, because
        `since` is inclusive at the boundary second.
        """
        params: dict = {"per_page": 100}
        if since:
            params["since"] = since
        comments = self._client.get(
            f"/repos/{self.repo}/issues/{subject_id}/comments", params=params
        ) or []
        return [
            {
                "id": c["id"],
                "body": c.get("body") or "",
                "author": (c.get("user") or {}).get("login") or "",
                "created_at": c.get("created_at") or "",
            }
            for c in comments
        ]

    def healthcheck(self) -> bool:
        try:
            self._client.get("/rate_limit")
            return True
        except Exception:  # noqa: BLE001 -- any failure means unhealthy, by design
            return False
