import pytest

from engine.adapters import _github, pr_review
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
        {"gate_request_id": "5", "gate_requested_at": "2026-07-16T09:00:00Z"}
    )
    assert decision.status == GateStatus.APPROVED
    assert fake.calls[0]["url"].endswith("/repos/o/r/pulls/5/reviews")


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
        {"gate_request_id": "5", "gate_requested_at": "2026-07-16T09:00:00Z"}
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
