import pytest

from engine.adapters import _github
from engine.adapters.claude_code_headless import ClaudeCodeHeadless
from engine.adapters.github_issues import GithubIssuesTracker


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

    def request(self, method, url, headers=None, json=None, params=None, timeout=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "params": params,
                "timeout": timeout,
            }
        )
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def token_env(monkeypatch):
    monkeypatch.setenv("AGENT_HQ_TOKEN", "test-token")


def _install(monkeypatch, responses):
    fake = FakeRequests(responses)
    monkeypatch.setattr(_github.requests, "request", fake.request)
    return fake


# -- GitHubClient ------------------------------------------------------------


def test_bearer_header_comes_from_env(monkeypatch):
    fake = _install(monkeypatch, [FakeResponse(200, {"ok": True})])
    client = _github.GitHubClient()
    client.get("/whatever")
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer test-token"
    assert fake.calls[0]["headers"]["Accept"] == "application/vnd.github+json"
    assert fake.calls[0]["headers"]["X-GitHub-Api-Version"] == "2026-03-10"
    assert fake.calls[0]["timeout"] == 30


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("AGENT_HQ_TOKEN", raising=False)
    client = _github.GitHubClient()
    with pytest.raises(RuntimeError, match="AGENT_HQ_TOKEN"):
        client.get("/whatever")


def test_non_2xx_raises_with_status_and_body(monkeypatch):
    _install(monkeypatch, [FakeResponse(404, text="issue not found")])
    client = _github.GitHubClient()
    with pytest.raises(RuntimeError, match="404") as exc:
        client.get("/repos/o/r/issues/999")
    assert "issue not found" in str(exc.value)


def test_204_returns_none(monkeypatch):
    _install(monkeypatch, [FakeResponse(204)])
    client = _github.GitHubClient()
    assert client.patch("/repos/o/r/issues/comments/1") is None


def test_combined_check_status_returns_state(monkeypatch):
    _install(monkeypatch, [FakeResponse(200, {"state": "success"})])
    client = _github.GitHubClient()
    assert client.combined_check_status("o/r", "abc123") == "success"


def test_list_workflow_runs_filters_by_name(monkeypatch):
    _install(
        monkeypatch,
        [
            FakeResponse(
                200,
                {
                    "workflow_runs": [
                        {"id": 1, "name": "ci"},
                        {"id": 2, "name": "dispatch"},
                    ]
                },
            )
        ],
    )
    client = _github.GitHubClient()
    runs = client.list_workflow_runs("o/r", "dispatch")
    assert [r["id"] for r in runs] == [2]


def test_list_workflow_runs_matches_display_title_over_workflow_name(monkeypatch):
    # Realistic payload: the workflow file's `name` stays "Run" for every
    # dispatch: the custom run-name ("agent-hq/<run_id>") only shows up in
    # `display_title`.
    _install(
        monkeypatch,
        [
            FakeResponse(
                200,
                {
                    "workflow_runs": [
                        {"id": 1, "name": "Run", "display_title": "agent-hq/run-1"},
                        {"id": 2, "name": "Run", "display_title": "agent-hq/run-2"},
                    ]
                },
            )
        ],
    )
    client = _github.GitHubClient()
    runs = client.list_workflow_runs("o/r", "agent-hq/run-1")
    assert [r["id"] for r in runs] == [1]


def test_git_credential_args_with_and_without_env(monkeypatch):
    monkeypatch.setenv("AGENT_HQ_TOKEN", "tok")
    args = _github.git_credential_args()
    assert args == [
        "-c",
        (
            "credential.helper=!f(){ echo username=x-access-token; "
            'echo "password=$AGENT_HQ_TOKEN"; };f'
        ),
    ]
    monkeypatch.delenv("AGENT_HQ_TOKEN", raising=False)
    assert _github.git_credential_args() == []


def test_mark_pr_ready_uses_graphql_mutation(monkeypatch):
    fake = _install(
        monkeypatch,
        [
            FakeResponse(200, {"draft": True, "node_id": "PR_node"}),
            FakeResponse(
                200,
                {
                    "data": {
                        "markPullRequestReadyForReview": {"pullRequest": {"isDraft": False}}
                    }
                },
            ),
        ],
    )

    ClaudeCodeHeadless({}).mark_pr_ready("o/r#12")

    assert fake.calls[0]["url"].endswith("/repos/o/r/pulls/12")
    assert fake.calls[1]["url"].endswith("/graphql")
    assert fake.calls[1]["json"]["variables"] == {"id": "PR_node"}


def test_pr_state_reports_merged_separately_from_closed(monkeypatch):
    """`state` is "closed" for both a merge and an abandonment, and the sweep
    routes those to opposite ends (DONE vs BLOCKED) -- so `merged` has to be
    read off `merged_at`, not inferred."""
    cases = [
        ({"state": "open", "merged_at": None}, {"state": "open", "merged": False}),
        (
            {"state": "closed", "merged_at": "2026-07-29T10:00:00Z"},
            {"state": "closed", "merged": True},
        ),
        ({"state": "closed", "merged_at": None}, {"state": "closed", "merged": False}),
    ]
    for payload, expected in cases:
        fake = _install(monkeypatch, [FakeResponse(200, payload)])
        assert ClaudeCodeHeadless({}).pr_state("o/r#12") == expected
        assert fake.calls[0]["url"].endswith("/repos/o/r/pulls/12")


# -- GithubIssuesTracker ------------------------------------------------------


def test_fetch_ticket_uses_settings_repo(monkeypatch):
    _install(
        monkeypatch,
        [
            FakeResponse(
                200,
                {
                    "number": 123,
                    "title": "Fix the thing",
                    "body": "details",
                    "labels": [{"name": "bug"}],
                },
            )
        ],
    )
    tracker = GithubIssuesTracker({"repo": "o/r"})
    ticket = tracker.fetch_ticket("123")
    assert ticket.ticket_id == "123"
    assert ticket.title == "Fix the thing"
    assert ticket.body == "details"
    assert ticket.labels == ["bug"]


def test_fetch_ticket_ref_with_explicit_repo(monkeypatch):
    fake = _install(
        monkeypatch,
        [FakeResponse(200, {"number": 5, "title": "t", "body": None, "labels": []})],
    )
    tracker = GithubIssuesTracker({})
    ticket = tracker.fetch_ticket("other-org/other-repo#5")
    assert ticket.body == ""
    assert fake.calls[0]["url"].endswith("/repos/other-org/other-repo/issues/5")


def test_parse_event_returns_none_without_issue():
    tracker = GithubIssuesTracker({"repo": "o/r"})
    assert tracker.parse_event({"action": "labeled"}, "evt-1") is None


def test_parse_event_builds_event_from_issue():
    tracker = GithubIssuesTracker({"repo": "o/r"})
    event = tracker.parse_event({"issue": {"number": 42}}, "delivery-1")
    assert event.event_id == "intake:delivery-1"
    assert event.kind == "ticket.event"
    assert event.ticket_id == "42"


def test_set_status_labels_removes_stale_hq_labels_only(monkeypatch):
    fake = _install(
        monkeypatch,
        [
            FakeResponse(
                200,
                {
                    "labels": [
                        {"name": "hq:status/active"},
                        {"name": "hq:blocked"},
                        {"name": "priority:high"},
                    ]
                },
            ),
            FakeResponse(200, {"labels": []}),
        ],
    )
    tracker = GithubIssuesTracker({"repo": "o/r"})
    tracker.set_status_labels("123", "active", ["hq:status/active"])
    patch_call = fake.calls[1]
    assert patch_call["method"] == "PATCH"
    assert sorted(patch_call["json"]["labels"]) == ["hq:status/active", "priority:high"]


def test_set_status_labels_noop_when_already_matching(monkeypatch):
    fake = _install(
        monkeypatch,
        [FakeResponse(200, {"labels": [{"name": "hq:status/active"}]})],
    )
    tracker = GithubIssuesTracker({"repo": "o/r"})
    tracker.set_status_labels("123", "active", ["hq:status/active"])
    assert len(fake.calls) == 1  # only the GET, no PATCH


def test_upsert_pinned_comment_creates_when_no_marker_comment(monkeypatch):
    fake = _install(
        monkeypatch,
        [
            FakeResponse(200, []),
            FakeResponse(200, {"id": 99}),
        ],
    )
    tracker = GithubIssuesTracker({"repo": "o/r"})
    comment_id = tracker.upsert_pinned_comment("123", "status body", "evt-1")
    assert comment_id == 99
    assert fake.calls[1]["method"] == "POST"
    assert "<!--hq:pinned-->" in fake.calls[1]["json"]["body"]
    assert "<!--hq:evt:evt-1-->" in fake.calls[1]["json"]["body"]


def test_upsert_pinned_comment_edits_when_pinned_comment_exists(monkeypatch):
    fake = _install(
        monkeypatch,
        [
            FakeResponse(
                200,
                [{"id": 7, "body": "<!--hq:pinned-->\n<!--hq:evt:evt-old-->\nold body"}],
            ),
            FakeResponse(200, {"id": 7}),
        ],
    )
    tracker = GithubIssuesTracker({"repo": "o/r"})
    comment_id = tracker.upsert_pinned_comment("123", "new body", "evt-new")
    assert comment_id == 7
    assert fake.calls[1]["method"] == "PATCH"
    assert "<!--hq:evt:evt-new-->" in fake.calls[1]["json"]["body"]


def test_upsert_pinned_comment_noops_when_event_marker_already_present(monkeypatch):
    fake = _install(
        monkeypatch,
        [
            FakeResponse(
                200,
                [{"id": 7, "body": "<!--hq:pinned-->\n<!--hq:evt:evt-1-->\nbody"}],
            )
        ],
    )
    tracker = GithubIssuesTracker({"repo": "o/r"})
    comment_id = tracker.upsert_pinned_comment("123", "body", "evt-1")
    assert comment_id == 7
    assert len(fake.calls) == 1  # only the GET, no write


def test_post_closing_summary_posts_once(monkeypatch):
    fake = _install(
        monkeypatch,
        [
            FakeResponse(200, []),
            FakeResponse(200, {"id": 1}),
        ],
    )
    tracker = GithubIssuesTracker({"repo": "o/r"})
    tracker.post_closing_summary("123", "closing", "evt-close")
    assert fake.calls[1]["method"] == "POST"
    assert "<!--hq:evt:evt-close-->" in fake.calls[1]["json"]["body"]


def test_post_closing_summary_collapses_the_body(monkeypatch):
    """A summary is a few KB of prose on a thread scrolled for the outcome, so
    it ships collapsed. The blank lines matter: GitHub renders markdown inside
    an unspaced <details> as raw text."""
    fake = _install(monkeypatch, [FakeResponse(200, []), FakeResponse(200, {"id": 1})])
    tracker = GithubIssuesTracker({"repo": "o/r"})
    tracker.post_closing_summary("123", "# Heading\n\nbody", "evt-close")
    body = fake.calls[1]["json"]["body"]
    assert "<details><summary><b>Closing summary</b></summary>\n\n# Heading" in body
    assert body.endswith("\n\n</details>")
    # The dedupe marker stays OUTSIDE the collapsed block -- a re-delivery scans
    # comment bodies for it, and a marker only the reader can expand still
    # matches, but keeping it visible in the raw body is what that scan reads.
    assert body.startswith("<!--hq:evt:evt-close-->")


def test_post_closing_summary_dedupes_by_event_marker(monkeypatch):
    fake = _install(
        monkeypatch,
        [FakeResponse(200, [{"id": 1, "body": "<!--hq:evt:evt-close-->\nclosing"}])],
    )
    tracker = GithubIssuesTracker({"repo": "o/r"})
    tracker.post_closing_summary("123", "closing", "evt-close")
    assert len(fake.calls) == 1  # only the GET, no POST


def test_post_closing_summary_second_call_short_circuits_via_local_cache(monkeypatch):
    fake = _install(
        monkeypatch,
        [
            FakeResponse(200, []),
            FakeResponse(200, {"id": 1}),
        ],
    )
    tracker = GithubIssuesTracker({"repo": "o/r"})
    tracker.post_closing_summary("123", "closing", "evt-close")
    tracker.post_closing_summary("123", "closing", "evt-close")
    assert len(fake.calls) == 2  # second call never hits the network


def test_close_issue_patches_state_closed(monkeypatch):
    fake = _install(monkeypatch, [FakeResponse(200, {"number": 123, "state": "closed"})])
    tracker = GithubIssuesTracker({"repo": "o/r"})
    tracker.close_issue("123")
    assert fake.calls[0]["method"] == "PATCH"
    assert fake.calls[0]["url"].endswith("/repos/o/r/issues/123")
    assert fake.calls[0]["json"] == {"state": "closed"}


def test_healthcheck_true_on_success(monkeypatch):
    _install(monkeypatch, [FakeResponse(200, {"rate": {}})])
    tracker = GithubIssuesTracker({"repo": "o/r"})
    assert tracker.healthcheck() is True


def test_healthcheck_false_on_failure(monkeypatch):
    _install(monkeypatch, [FakeResponse(500, text="boom")])
    tracker = GithubIssuesTracker({"repo": "o/r"})
    assert tracker.healthcheck() is False
