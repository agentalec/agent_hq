"""Honesty checks for specs/{ticket}/qa-report.json + media policy."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from engine.config import ConfigError, load_config
from engine.qa_report import (
    format_qa_summary_footer,
    resolve_qa_media,
    validate_qa_media_combo,
    validate_qa_report,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"
CONFIG_DIR = REPO_ROOT / "config"

TICKET = "7"


def _criterion(**over):
    base = {
        "id": "dropdown",
        "title": "Service point dropdown opens",
        "verdict": "pass",
        "evidence_kind": "live-flow",
        "blocker": None,
        "blocker_category": None,
        "plan_steps_run": ["1", "2"],
        "videos": [f"specs/{TICKET}/videos/dropdown.webm"],
        "screenshots": [],
    }
    base.update(over)
    return base


def _report(criteria, **summary_over):
    counts = {"pass": 0, "fail": 0, "not_exercised": 0}
    for c in criteria:
        key = "not_exercised" if c["verdict"] == "not-exercised" else c["verdict"]
        counts[key] += 1
    summary = {
        "all_passed": bool(criteria) and counts["fail"] == 0 and counts["not_exercised"] == 0,
        "pass": counts["pass"],
        "fail": counts["fail"],
        "not_exercised": counts["not_exercised"],
    }
    summary.update(summary_over)
    return {"criteria": criteria, "summary": summary}


def _raw(doc) -> bytes:
    return (json.dumps(doc) + "\n").encode()


def _pass_ledger(*extra: str) -> set[str]:
    return {
        f"specs/{TICKET}/videos/dropdown.webm",
        f"specs/{TICKET}/qa-drivers/dropdown.mjs",
        f"specs/{TICKET}/qa-logs/dropdown.log",
        f"specs/{TICKET}/qa-report.json",
        *extra,
    }


def _pass_contents(**over: bytes) -> dict[str, bytes]:
    base = {
        f"specs/{TICKET}/qa-logs/dropdown.log": b"playwright ok\n",
    }
    base.update(over)
    return base


def _validate(doc, *, ledger=None, media=None, contents=None):
    return validate_qa_report(
        _raw(doc),
        ledger=ledger if ledger is not None else _pass_ledger(),
        media=media,
        ticket_id=TICKET,
        contents=contents if contents is not None else _pass_contents(),
    )


def test_schema_accepts_a_minimal_honest_pass():
    schema = json.loads((SCHEMAS_DIR / "qa-report.schema.json").read_text())
    Draft202012Validator(schema).validate(_report([_criterion()]))


def test_resolve_qa_media_defaults_video_on():
    assert resolve_qa_media({}) == {
        "video": True,
        "screenshots": False,
        "video_max_seconds": 120,
    }
    assert resolve_qa_media({"qa": {"video": False, "screenshots": True}})["video"] is False


def test_validate_qa_media_combo_rejects_all_off():
    assert validate_qa_media_combo("org/fe", {"qa": {"video": False}}) is not None
    assert validate_qa_media_combo("org/fe", {"qa": {"video": False, "screenshots": True}}) is None
    assert validate_qa_media_combo("org/fe", {}) is None


def test_load_config_rejects_video_and_screenshots_both_false(tmp_path):
    bad = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, bad)
    repos = (bad / "repos.yml").read_text()
    # Force an invalid combo on the sole repo entry.
    repos = repos.replace(
        "video: true\n    screenshots: false",
        "video: false\n    screenshots: false",
    )
    (bad / "repos.yml").write_text(repos)
    with pytest.raises(ConfigError) as excinfo:
        load_config(bad, SCHEMAS_DIR)
    assert any("video" in e and "screenshots" in e for e in excinfo.value.errors)


def test_pass_requires_live_flow_video_in_ledger():
    doc = _report([_criterion()])
    assert _validate(doc) is None

    assert "live-flow" in _validate(_report([_criterion(evidence_kind="code-inspection")]))
    assert "≥1 video" in _validate(_report([_criterion(videos=[])]))
    assert "not in ledger" in _validate(
        doc,
        ledger={
            f"specs/{TICKET}/qa-drivers/dropdown.mjs",
            f"specs/{TICKET}/qa-logs/dropdown.log",
            f"specs/{TICKET}/qa-report.json",
        },
    )


def test_pass_requires_canonical_video_name():
    doc = _report([_criterion(videos=[f"specs/{TICKET}/videos/dropdown-desktop.webm"])])
    assert "exactly" in _validate(
        doc,
        ledger=_pass_ledger(f"specs/{TICKET}/videos/dropdown-desktop.webm"),
    )


def test_pass_rejects_shared_video_across_criteria():
    """Two criteria cannot list the same video path (ticket-13 rename swap)."""
    shared = f"specs/{TICKET}/videos/dropdown.webm"
    doc = _report(
        [
            _criterion(id="dropdown", videos=[shared]),
            _criterion(id="other", videos=[shared]),
        ]
    )
    ledger = _pass_ledger(
        f"specs/{TICKET}/qa-drivers/other.mjs",
        f"specs/{TICKET}/qa-logs/other.log",
    )
    contents = {
        **_pass_contents(),
        f"specs/{TICKET}/qa-logs/other.log": b"other\n",
    }
    err = _validate(doc, ledger=ledger, contents=contents)
    assert err is not None
    assert "claimed by" in err


def test_pass_requires_driver_and_nonempty_log():
    doc = _report([_criterion()])
    assert "driver" in _validate(
        doc,
        ledger={
            f"specs/{TICKET}/videos/dropdown.webm",
            f"specs/{TICKET}/qa-logs/dropdown.log",
            f"specs/{TICKET}/qa-report.json",
        },
    )
    assert "log" in _validate(
        doc,
        ledger={
            f"specs/{TICKET}/videos/dropdown.webm",
            f"specs/{TICKET}/qa-drivers/dropdown.mjs",
            f"specs/{TICKET}/qa-report.json",
        },
    )
    assert "non-empty" in _validate(
        doc,
        contents={f"specs/{TICKET}/qa-logs/dropdown.log": b"   \n"},
    )


def test_screenshots_escape_hatch_when_video_off():
    doc = _report(
        [
            _criterion(
                videos=[],
                screenshots=[f"specs/{TICKET}/screenshots/dropdown.png"],
            )
        ]
    )
    ledger = {f"specs/{TICKET}/screenshots/dropdown.png"}
    media = {"video": False, "screenshots": True, "video_max_seconds": 120}
    assert _validate(doc, ledger=ledger, media=media, contents={}) is None
    assert "≥1 screenshot" in _validate(
        _report([_criterion(videos=[], screenshots=[])]),
        ledger=ledger,
        media=media,
        contents={},
    )


def test_not_exercised_requires_blocker_category():
    doc = _report(
        [
            _criterion(
                verdict="not-exercised",
                evidence_kind="unreachable",
                blocker="no facility selected",
                blocker_category="missing-facility-context",
                plan_steps_run=[],
                videos=[],
            )
        ]
    )
    assert _validate(doc, ledger=set(), contents={}) is None
    bad = _report(
        [
            _criterion(
                verdict="not-exercised",
                evidence_kind="unreachable",
                blocker="blocked",
                blocker_category=None,
                plan_steps_run=[],
                videos=[],
            )
        ]
    )
    assert "blocker_category" in _validate(bad, ledger=set(), contents={})


def _seed_attempt(method: str = "ui") -> dict:
    return {
        "method": method,
        "summary": (
            f"tried {method}: UI create on settings then "
            "POST /api/v1/facility/{id}/activity_definition/ → 403"
        ),
    }


def _seed_ledger(*extra: str) -> set[str]:
    return {
        f"specs/{TICKET}/qa-drivers/dropdown.mjs",
        f"specs/{TICKET}/qa-logs/dropdown.log",
        f"specs/{TICKET}/qa-report.json",
        *extra,
    }


def _seed_contents(**over: bytes) -> dict[str, bytes]:
    base = {
        f"specs/{TICKET}/qa-logs/dropdown.log": (
            b"fixture lookup miss\nUI create failed\nAPI POST -> 403\n"
        ),
    }
    base.update(over)
    return base


def test_missing_test_data_requires_seed_attempt():
    """not-exercised + missing-test-data without a real seed attempt fails collect."""
    bare = _report(
        [
            _criterion(
                verdict="not-exercised",
                evidence_kind="unreachable",
                blocker="complex UI would exceed budget",
                blocker_category="missing-test-data",
                plan_steps_run=[],
                videos=[],
            )
        ]
    )
    err = _validate(bare, ledger=set(), contents={})
    assert err is not None
    assert "seed_attempt" in err

    for method in ("ui", "api", "both"):
        ok = _report(
            [
                _criterion(
                    verdict="not-exercised",
                    evidence_kind="unreachable",
                    blocker="create failed after seed ladder",
                    blocker_category="missing-test-data",
                    plan_steps_run=["fixture lookup", "UI create", "API POST"],
                    videos=[],
                    seed_attempt=_seed_attempt(method),
                )
            ]
        )
        assert _validate(ok, ledger=_seed_ledger(), contents=_seed_contents()) is None

    none_method = _report(
        [
            _criterion(
                verdict="not-exercised",
                evidence_kind="unreachable",
                blocker="no data",
                blocker_category="missing-test-data",
                plan_steps_run=["tried UI"],
                videos=[],
                seed_attempt={"method": "none", "summary": "skipped"},
            )
        ]
    )
    err_none = _validate(none_method, ledger=_seed_ledger(), contents=_seed_contents())
    assert err_none is not None
    assert "seed_attempt.method" in err_none

    blank_summary = _report(
        [
            _criterion(
                verdict="not-exercised",
                evidence_kind="unreachable",
                blocker="no data",
                blocker_category="missing-test-data",
                plan_steps_run=["tried UI"],
                videos=[],
                seed_attempt={"method": "ui", "summary": "   \n"},
            )
        ]
    )
    err_summary = _validate(blank_summary, ledger=_seed_ledger(), contents=_seed_contents())
    assert err_summary is not None
    assert "seed_attempt.summary" in err_summary


def test_missing_test_data_requires_plan_steps_and_receipts():
    """missing-test-data needs executed steps plus canonical driver/log evidence."""
    base_kwargs = {
        "verdict": "not-exercised",
        "evidence_kind": "unreachable",
        "blocker": "create failed after seed ladder",
        "blocker_category": "missing-test-data",
        "videos": [],
        "seed_attempt": _seed_attempt(),
    }

    no_steps = _report([_criterion(**base_kwargs, plan_steps_run=[])])
    err_steps = _validate(no_steps, ledger=_seed_ledger(), contents=_seed_contents())
    assert err_steps is not None
    assert "plan_steps_run" in err_steps

    with_steps = _criterion(**base_kwargs, plan_steps_run=["UI create", "API POST"])
    doc = _report([with_steps])
    assert "driver" in _validate(
        doc,
        ledger={f"specs/{TICKET}/qa-logs/dropdown.log", f"specs/{TICKET}/qa-report.json"},
        contents=_seed_contents(),
    )
    assert "log" in _validate(
        doc,
        ledger={f"specs/{TICKET}/qa-drivers/dropdown.mjs", f"specs/{TICKET}/qa-report.json"},
        contents={},
    )
    assert "non-empty" in _validate(
        doc,
        ledger=_seed_ledger(),
        contents={f"specs/{TICKET}/qa-logs/dropdown.log": b"  \n"},
    )
    assert _validate(doc, ledger=_seed_ledger(), contents=_seed_contents()) is None


def test_attempted_fail_and_not_exercised_require_receipts():
    """Non-empty plan_steps_run on fail/not-exercised requires driver + non-empty log."""
    fail_doc = _report(
        [
            _criterion(
                verdict="fail",
                evidence_kind="live-flow",
                blocker="assertion failed: dropdown empty",
                blocker_category="validation-error",
                plan_steps_run=["open settings", "click dropdown"],
                videos=[],
            )
        ]
    )
    assert "driver" in _validate(fail_doc, ledger=set(), contents={})
    assert "log" in _validate(
        fail_doc,
        ledger={f"specs/{TICKET}/qa-drivers/dropdown.mjs"},
        contents={},
    )
    assert "non-empty" in _validate(
        fail_doc,
        ledger=_seed_ledger(),
        contents={f"specs/{TICKET}/qa-logs/dropdown.log": b""},
    )
    assert (
        _validate(
            fail_doc,
            ledger=_seed_ledger(),
            contents={f"specs/{TICKET}/qa-logs/dropdown.log": b"clicked; empty\n"},
        )
        is None
    )

    auth_doc = _report(
        [
            _criterion(
                verdict="not-exercised",
                evidence_kind="unreachable",
                blocker="token refresh then re-login both failed",
                blocker_category="auth-failure",
                plan_steps_run=["load storageState", "refresh JWT", "UI login"],
                videos=[],
            )
        ]
    )
    assert "driver" in _validate(auth_doc, ledger=set(), contents={})
    assert (
        _validate(
            auth_doc,
            ledger=_seed_ledger(),
            contents={
                f"specs/{TICKET}/qa-logs/dropdown.log": b"refresh 401; login failed\n",
            },
        )
        is None
    )


def test_pre_execution_blocker_remains_log_free():
    """Empty plan_steps_run (e.g. no-qa-plan) stays free of driver/log requirements."""
    doc = _report(
        [
            _criterion(
                verdict="not-exercised",
                evidence_kind="unreachable",
                blocker="no qa-plan.md in the input artifacts",
                blocker_category="no-qa-plan",
                plan_steps_run=[],
                videos=[],
            )
        ]
    )
    assert _validate(doc, ledger=set(), contents={}) is None


def test_all_passed_cannot_claim_full_pass_with_gaps():
    criteria = [
        _criterion(),
        _criterion(
            id="other",
            verdict="not-exercised",
            evidence_kind="unreachable",
            blocker="missing role",
            blocker_category="missing-permission",
            plan_steps_run=[],
            videos=[],
        ),
    ]
    doc = _report(criteria, all_passed=True)
    assert "all_passed" in _validate(doc, ledger=_pass_ledger())


def test_summary_counts_must_match_verdicts():
    doc = _report([_criterion()], **{"pass": 2})
    assert "summary counts" in _validate(doc, ledger=_pass_ledger())


def test_format_qa_summary_footer():
    doc = _report(
        [
            _criterion(),
            _criterion(
                id="b",
                verdict="not-exercised",
                evidence_kind="unreachable",
                blocker="x",
                blocker_category="other",
                plan_steps_run=[],
                videos=[],
            ),
        ]
    )
    assert format_qa_summary_footer(_raw(doc)) == "1 pass / 0 fail / 1 not-exercised"
    assert format_qa_summary_footer(None) is None
