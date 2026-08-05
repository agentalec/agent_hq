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


def _criterion(**over):
    base = {
        "id": "dropdown",
        "title": "Service point dropdown opens",
        "verdict": "pass",
        "evidence_kind": "live-flow",
        "blocker": None,
        "blocker_category": None,
        "plan_steps_run": ["1", "2"],
        "videos": ["specs/7/videos/dropdown.webm"],
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


def test_schema_accepts_a_minimal_honest_pass():
    schema = json.loads((SCHEMAS_DIR / "qa-report.schema.json").read_text())
    Draft202012Validator(schema).validate(_report([_criterion()]))


def test_resolve_qa_media_defaults_video_on():
    assert resolve_qa_media({}) == {
        "video": True,
        "screenshots": False,
        "video_max_seconds": 30,
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
    ledger = {"specs/7/videos/dropdown.webm", "specs/7/qa-report.json"}
    assert validate_qa_report(_raw(doc), ledger=ledger) is None

    assert "live-flow" in validate_qa_report(
        _raw(_report([_criterion(evidence_kind="code-inspection")])),
        ledger=ledger,
    )
    assert "≥1 video" in validate_qa_report(
        _raw(_report([_criterion(videos=[])])),
        ledger=ledger,
    )
    assert "not in ledger" in validate_qa_report(
        _raw(doc),
        ledger={"specs/7/qa-report.json"},
    )


def test_screenshots_escape_hatch_when_video_off():
    doc = _report(
        [
            _criterion(
                videos=[],
                screenshots=["specs/7/screenshots/dropdown.png"],
            )
        ]
    )
    ledger = {"specs/7/screenshots/dropdown.png"}
    media = {"video": False, "screenshots": True, "video_max_seconds": 30}
    assert validate_qa_report(_raw(doc), ledger=ledger, media=media) is None
    assert "≥1 screenshot" in validate_qa_report(
        _raw(_report([_criterion(videos=[], screenshots=[])])),
        ledger=ledger,
        media=media,
    )


def test_not_exercised_requires_blocker_category():
    doc = _report(
        [
            _criterion(
                verdict="not-exercised",
                evidence_kind="unreachable",
                blocker="no facility selected",
                blocker_category="missing-facility-context",
                videos=[],
            )
        ]
    )
    assert validate_qa_report(_raw(doc), ledger=set()) is None
    bad = _report(
        [
            _criterion(
                verdict="not-exercised",
                evidence_kind="unreachable",
                blocker="blocked",
                blocker_category=None,
                videos=[],
            )
        ]
    )
    assert "blocker_category" in validate_qa_report(_raw(bad), ledger=set())


def test_all_passed_cannot_claim_full_pass_with_gaps():
    criteria = [
        _criterion(),
        _criterion(
            id="other",
            verdict="not-exercised",
            evidence_kind="unreachable",
            blocker="missing role",
            blocker_category="missing-permission",
            videos=[],
        ),
    ]
    doc = _report(criteria, all_passed=True)
    assert "all_passed" in validate_qa_report(
        _raw(doc),
        ledger={"specs/7/videos/dropdown.webm"},
    )


def test_summary_counts_must_match_verdicts():
    doc = _report([_criterion()], **{"pass": 2})
    assert "summary counts" in validate_qa_report(
        _raw(doc),
        ledger={"specs/7/videos/dropdown.webm"},
    )


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
                videos=[],
            ),
        ]
    )
    assert format_qa_summary_footer(_raw(doc)) == "1 pass / 0 fail / 1 not-exercised"
    assert format_qa_summary_footer(None) is None
