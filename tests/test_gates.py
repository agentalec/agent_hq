import pytest

from engine.adapters import _github, github_issue_comment_gate, pr_review
from engine.adapters.github_issue_comment_gate import GithubIssueCommentGate
from engine.adapters.pr_review import PrReviewGate, add_working_hours
from engine.models import GateStatus

APPROVERS = {
    "groups": {
        "product-owners": {"members": ["example-alice"]},
        "architects": {"members": ["example-bob"]},
    },
    "working_hours": {
        "timezone": "Asia/Kolkata",
        "start": 9,
        "end": 17,
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
    },
}


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


def _gate(**settings):
    return PrReviewGate({"repo": "o/r", "approvers": APPROVERS, **settings})


# -- request -------------------------------------------------------------


def test_request_reuses_existing_open_pr_for_branch(monkeypatch):
    fake = _install(
        monkeypatch,
        [
            FakeResponse(200, [{"number": 5}]),
            FakeResponse(200, {}),
        ],
    )
    gate = _gate()
    result = gate.request(
        "product-owners",
        {"repo": "o/r", "ticket_id": "1", "branch": "agent-hq/1", "title": "t", "body": "b"},
    )
    assert result.request_id == "5"
    assert len(fake.calls) == 2  # GET pulls + POST reviewers, no create POST
    assert fake.calls[0]["method"] == "GET"
    assert fake.calls[0]["params"]["head"] == "o:agent-hq/1"
    assert fake.calls[1]["method"] == "POST"
    assert fake.calls[1]["url"].endswith("/repos/o/r/pulls/5/requested_reviewers")
    assert fake.calls[1]["json"]["reviewers"] == ["example-alice"]


def test_request_creates_draft_pr_when_none_exists(monkeypatch):
    fake = _install(
        monkeypatch,
        [
            FakeResponse(200, []),
            FakeResponse(200, {"number": 7}),
            FakeResponse(200, {}),
        ],
    )
    gate = _gate()
    result = gate.request(
        "architects",
        {"repo": "o/r", "ticket_id": "9", "branch": "agent-hq/9", "title": "t", "body": "b"},
    )
    assert result.request_id == "7"
    create_call = fake.calls[1]
    assert create_call["method"] == "POST"
    assert create_call["url"].endswith("/repos/o/r/pulls")
    assert create_call["json"]["head"] == "agent-hq/9"
    assert create_call["json"]["base"] == "main"
    assert create_call["json"]["draft"] is True


def test_request_tolerates_422_on_reviewer_request(monkeypatch):
    fake = _install(
        monkeypatch,
        [
            FakeResponse(200, []),
            FakeResponse(200, {"number": 9}),
            FakeResponse(422, text="review cannot be requested from pull request author"),
        ],
    )
    gate = _gate()
    result = gate.request(
        "product-owners",
        {"repo": "o/r", "ticket_id": "2", "branch": "agent-hq/2", "title": "t", "body": "b"},
    )
    assert result.request_id == "9"
    assert len(fake.calls) == 3


# -- status ----------------------------------------------------------------


def test_status_latest_per_reviewer_supersedes_changes_requested_with_approval(monkeypatch):
    fake = _install(
        monkeypatch,
        [
            FakeResponse(
                200,
                [
                    {
                        "user": {"login": "example-alice"},
                        "state": "CHANGES_REQUESTED",
                        "submitted_at": "2026-07-15T10:00:00Z",
                        "body": "please fix",
                    },
                    {
                        "user": {"login": "example-alice"},
                        "state": "APPROVED",
                        "submitted_at": "2026-07-16T10:00:00Z",
                        "body": "",
                    },
                ],
            )
        ],
    )
    gate = _gate()
    decision = gate.status(
        {
            "gate_request_id": "5",
            "gate_requested_at": "2026-07-16T09:00:00Z",
            "approver_group": "product-owners",
        }
    )
    assert decision.status == GateStatus.APPROVED
    assert fake.calls[0]["url"].endswith("/repos/o/r/pulls/5/reviews")


def test_status_ignores_approval_from_non_group_member(monkeypatch):
    _install(
        monkeypatch,
        [
            FakeResponse(
                200,
                [
                    {
                        "user": {"login": "some-random-user"},
                        "state": "APPROVED",
                        "submitted_at": "2026-07-16T10:00:00Z",
                        "body": "",
                    }
                ],
            )
        ],
    )
    gate = _gate()
    decision = gate.status(
        {
            "gate_request_id": "5",
            "gate_requested_at": "2026-07-16T09:00:00Z",
            "approver_group": "product-owners",
        }
    )
    assert decision.status == GateStatus.PENDING


def test_status_changes_requested_carries_review_body(monkeypatch):
    _install(
        monkeypatch,
        [
            FakeResponse(
                200,
                [
                    {
                        "user": {"login": "example-bob"},
                        "state": "CHANGES_REQUESTED",
                        "submitted_at": "2026-07-16T10:00:00Z",
                        "body": "please rework the migration",
                    }
                ],
            )
        ],
    )
    gate = _gate()
    decision = gate.status(
        {
            "gate_request_id": "5",
            "gate_requested_at": "2026-07-16T09:00:00Z",
            "approver_group": "architects",
        }
    )
    assert decision.status == GateStatus.CHANGES_REQUESTED
    assert "please rework the migration" in decision.comments


def test_status_pending_when_no_reviews_and_not_expired(monkeypatch):
    _install(monkeypatch, [FakeResponse(200, [])])
    monkeypatch.setattr(pr_review, "_now_iso", lambda: "2026-07-16T09:30:00Z")
    gate = _gate()
    decision = gate.status(
        {
            "gate_request_id": "5",
            "gate_requested_at": "2026-07-16T09:00:00Z",
            "timeout_working_hours": 2,
        }
    )
    assert decision.status == GateStatus.PENDING


def test_status_expiry_friday_16_00_ist_plus_2_working_hours(monkeypatch):
    # Friday 2026-07-17 16:00 IST = 2026-07-17T10:30:00Z; +2 working hours
    # (1h left Friday, 1h Monday morning) = Monday 2026-07-20 10:00 IST.
    run = {
        "gate_request_id": "5",
        "gate_requested_at": "2026-07-17T10:30:00Z",
        "timeout_working_hours": 2,
    }

    _install(monkeypatch, [FakeResponse(200, [])])
    monkeypatch.setattr(pr_review, "_now_iso", lambda: "2026-07-20T04:00:00Z")  # before deadline
    gate = _gate()
    assert gate.status(run).status == GateStatus.PENDING

    _install(monkeypatch, [FakeResponse(200, [])])
    monkeypatch.setattr(pr_review, "_now_iso", lambda: "2026-07-20T05:00:00Z")  # after deadline
    gate = _gate()
    assert gate.status(run).status == GateStatus.EXPIRED


def test_status_healthcheck_true_and_false(monkeypatch):
    _install(monkeypatch, [FakeResponse(200, {"rate": {}})])
    assert _gate().healthcheck() is True

    _install(monkeypatch, [FakeResponse(500, text="boom")])
    assert _gate().healthcheck() is False


# -- add_working_hours -------------------------------------------------------


def test_add_working_hours_friday_afternoon_rolls_into_monday():
    schedule = APPROVERS["working_hours"]
    deadline = add_working_hours("2026-07-17T10:30:00Z", 2, schedule)
    assert deadline == "2026-07-20T04:30:00Z"  # Monday 2026-07-20 10:00 IST


def test_add_working_hours_weekend_start_rolls_to_monday():
    schedule = APPROVERS["working_hours"]
    # Saturday 2026-07-18 12:00 IST = 2026-07-18T06:30:00Z
    deadline = add_working_hours("2026-07-18T06:30:00Z", 1, schedule)
    # rolls to Monday 09:00 IST, +1h = Monday 10:00 IST = 04:30:00Z
    assert deadline == "2026-07-20T04:30:00Z"


# -- GithubIssueCommentGate ---------------------------------------------------


def _issue_gate(**settings):
    return GithubIssueCommentGate({"issue_repo": "engine-org/engine-repo", "approvers": APPROVERS, **settings})


def _run(**over):
    run = {
        "ticket_id": "9",
        "run_id": "run-abc123",
        "gate_request_id": "555",
        "gate_requested_at": "2026-07-16T09:00:00Z",
        "approver_group": "product-owners",
    }
    run.update(over)
    return run


def test_issue_gate_request_creates_comment_with_marker_and_grammar(monkeypatch):
    fake = _install(
        monkeypatch,
        [FakeResponse(200, []), FakeResponse(200, {"id": 42})],
    )
    gate = _issue_gate()
    result = gate.request(
        "product-owners",
        {"ticket_id": "9", "run_id": "run-abc123", "task_id": "spec", "title": "Add backend endpoint"},
    )
    assert result.request_id == "42"
    assert fake.calls[0]["method"] == "GET"
    assert fake.calls[0]["url"].endswith("/repos/engine-org/engine-repo/issues/9/comments")
    create_call = fake.calls[1]
    assert create_call["method"] == "POST"
    body = create_call["json"]["body"]
    assert "<!--hq:gate:run-abc123-->" in body
    assert "@example-alice" in body
    assert "/agent-hq approve run-abc123" in body
    assert "/agent-hq request-changes run-abc123 <reason>" in body
    assert "/agent-hq reject run-abc123 <reason>" in body


def test_issue_gate_request_reuses_existing_marker_comment(monkeypatch):
    fake = _install(
        monkeypatch,
        [FakeResponse(200, [{"id": 7, "body": "<!--hq:gate:run-abc123-->\nalready asked"}])],
    )
    gate = _issue_gate()
    result = gate.request(
        "product-owners", {"ticket_id": "9", "run_id": "run-abc123", "task_id": "spec", "title": "t"}
    )
    assert result.request_id == "7"
    assert len(fake.calls) == 1  # only the GET, no duplicate POST


def test_issue_gate_request_finds_marker_beyond_first_page(monkeypatch):
    page1 = [{"id": i, "body": f"noise {i}"} for i in range(100)]
    page2 = [{"id": 999, "body": "<!--hq:gate:run-abc123-->\nalready asked"}]
    fake = _install(monkeypatch, [FakeResponse(200, page1), FakeResponse(200, page2)])
    gate = _issue_gate()
    result = gate.request(
        "product-owners", {"ticket_id": "9", "run_id": "run-abc123", "task_id": "spec", "title": "t"}
    )
    assert result.request_id == "999"
    assert len(fake.calls) == 2  # two GET pages, no duplicate POST
    assert fake.calls[0]["params"]["page"] == 1
    assert fake.calls[1]["params"]["page"] == 2


def test_issue_gate_status_approve_command_from_group_member(monkeypatch):
    _install(
        monkeypatch,
        [FakeResponse(200, [
            {"id": 1, "user": {"login": "example-alice"},
             "body": "/agent-hq approve run-abc123", "created_at": "2026-07-16T10:00:00Z"},
        ])],
    )
    decision = _issue_gate().status(_run())
    assert decision.status == GateStatus.APPROVED
    assert decision.comment_id == 1
    assert decision.actor == "example-alice"
    assert decision.decided_at == "2026-07-16T10:00:00Z"


def test_issue_gate_status_request_changes_carries_reason(monkeypatch):
    _install(
        monkeypatch,
        [FakeResponse(200, [
            {"id": 2, "user": {"login": "example-alice"},
             "body": "/agent-hq request-changes run-abc123 please fix the migration",
             "created_at": "2026-07-16T10:00:00Z"},
        ])],
    )
    decision = _issue_gate().status(_run())
    assert decision.status == GateStatus.CHANGES_REQUESTED
    assert decision.comments == "please fix the migration"


def test_issue_gate_status_reject_command(monkeypatch):
    _install(
        monkeypatch,
        [FakeResponse(200, [
            {"id": 3, "user": {"login": "example-alice"},
             "body": "/agent-hq reject run-abc123 not needed", "created_at": "2026-07-16T10:00:00Z"},
        ])],
    )
    decision = _issue_gate().status(_run())
    assert decision.status == GateStatus.REJECTED
    assert decision.comments == "not needed"


def test_issue_gate_status_ignores_non_member_commenter(monkeypatch):
    _install(
        monkeypatch,
        [FakeResponse(200, [
            {"id": 4, "user": {"login": "some-random-user"},
             "body": "/agent-hq approve run-abc123", "created_at": "2026-07-16T10:00:00Z"},
        ])],
    )
    decision = _issue_gate().status(_run())
    assert decision.status == GateStatus.PENDING


def test_issue_gate_status_ignores_comment_for_a_different_run(monkeypatch):
    _install(
        monkeypatch,
        [FakeResponse(200, [
            {"id": 5, "user": {"login": "example-alice"},
             "body": "/agent-hq approve some-other-run", "created_at": "2026-07-16T10:00:00Z"},
        ])],
    )
    decision = _issue_gate().status(_run())
    assert decision.status == GateStatus.PENDING


def test_issue_gate_status_latest_decision_wins(monkeypatch):
    _install(
        monkeypatch,
        [FakeResponse(200, [
            {"id": 6, "user": {"login": "example-alice"},
             "body": "/agent-hq request-changes run-abc123 wait", "created_at": "2026-07-16T09:00:00Z"},
            {"id": 7, "user": {"login": "example-alice"},
             "body": "/agent-hq approve run-abc123", "created_at": "2026-07-16T10:00:00Z"},
        ])],
    )
    decision = _issue_gate().status(_run())
    assert decision.status == GateStatus.APPROVED
    assert decision.comment_id == 7


def test_issue_gate_status_finds_decision_beyond_first_page(monkeypatch):
    page1 = [
        {"id": i, "user": {"login": "noise"}, "body": "chatter", "created_at": "2026-07-16T09:00:00Z"}
        for i in range(100)
    ]
    page2 = [
        {"id": 42, "user": {"login": "example-alice"},
         "body": "/agent-hq approve run-abc123", "created_at": "2026-07-16T10:00:00Z"},
    ]
    fake = _install(monkeypatch, [FakeResponse(200, page1), FakeResponse(200, page2)])
    decision = _issue_gate().status(_run())
    assert decision.status == GateStatus.APPROVED
    assert decision.comment_id == 42
    assert len(fake.calls) == 2


def test_issue_gate_status_pending_when_no_decision_and_not_expired(monkeypatch):
    # Friday 2026-07-17 16:00 IST = 2026-07-17T10:30:00Z; +2 working hours
    # (same fixture math as pr_review's equivalent test) expires Monday
    # 2026-07-20 10:00 IST = 2026-07-20T04:30:00Z.
    _install(monkeypatch, [FakeResponse(200, [])])
    monkeypatch.setattr(github_issue_comment_gate, "_now_iso", lambda: "2026-07-20T04:00:00Z")
    run = _run(gate_requested_at="2026-07-17T10:30:00Z", timeout_working_hours=2)
    assert _issue_gate().status(run).status == GateStatus.PENDING


def test_issue_gate_status_expires_after_timeout(monkeypatch):
    _install(monkeypatch, [FakeResponse(200, [])])
    monkeypatch.setattr(github_issue_comment_gate, "_now_iso", lambda: "2026-07-20T05:00:00Z")
    run = _run(gate_requested_at="2026-07-17T10:30:00Z", timeout_working_hours=2)
    assert _issue_gate().status(run).status == GateStatus.EXPIRED


def test_issue_gate_healthcheck_true_and_false(monkeypatch):
    _install(monkeypatch, [FakeResponse(200, {"rate": {}})])
    assert _issue_gate().healthcheck() is True

    _install(monkeypatch, [FakeResponse(500, text="boom")])
    assert _issue_gate().healthcheck() is False
