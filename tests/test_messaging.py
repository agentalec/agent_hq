import pytest

from engine.adapters import _github
from engine.adapters.github_comment import GithubCommentMessaging


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text or (str(json_body) if json_body is not None else "")
        self.content = b"x" if (json_body is not None or text) else b""

    def json(self):
        return self._json_body


class FakeRequests:
    """Records calls and dequeues canned responses in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, headers=None, json=None, params=None):
        self.calls.append(
            {"method": method, "url": url, "headers": headers, "json": json, "params": params}
        )
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def token_env(monkeypatch):
    monkeypatch.setenv("AGENT_HQ_TOKEN", "test-token")


def _install(monkeypatch, responses):
    fake = FakeRequests(responses)
    monkeypatch.setattr(_github.requests, "request", fake.request)
    return fake


def test_notify_posts_comment_with_mentions_message_and_links(monkeypatch):
    fake = _install(
        monkeypatch,
        [
            FakeResponse(200, []),
            FakeResponse(200, {"id": 1}),
        ],
    )
    messaging = GithubCommentMessaging({"repo": "o/r"})
    messaging.notify(
        {"ticket_id": "123", "mentions": ["alice", "bob"]},
        "run finished",
        ["https://example.com/a", "https://example.com/b"],
        "evt-1",
    )
    post_call = fake.calls[1]
    assert post_call["method"] == "POST"
    body = post_call["json"]["body"]
    assert "@alice @bob" in body
    assert "run finished" in body
    assert "- https://example.com/a" in body
    assert "- https://example.com/b" in body
    assert "<!--hq:evt:evt-1-->" in body


def test_notify_dedupes_by_event_marker(monkeypatch):
    fake = _install(
        monkeypatch,
        [FakeResponse(200, [{"id": 9, "body": "<!--hq:evt:evt-1-->\nold"}])],
    )
    messaging = GithubCommentMessaging({"repo": "o/r"})
    messaging.notify(
        {"ticket_id": "123", "mentions": ["alice"]}, "run finished", [], "evt-1"
    )
    assert len(fake.calls) == 1  # only the GET, no POST


def test_healthcheck_true_on_success(monkeypatch):
    _install(monkeypatch, [FakeResponse(200, {"rate": {}})])
    messaging = GithubCommentMessaging({"repo": "o/r"})
    assert messaging.healthcheck() is True


def test_healthcheck_false_on_failure(monkeypatch):
    _install(monkeypatch, [FakeResponse(500, text="boom")])
    messaging = GithubCommentMessaging({"repo": "o/r"})
    assert messaging.healthcheck() is False
