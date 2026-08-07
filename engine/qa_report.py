"""Collect-time honesty checks for `specs/{ticket}/qa-report.json`.

Filename convention only — the engine does not special-case the `qa` task id.
When that path is among a run's ledger artifacts, collect validates schema +
media policy and refuses a dishonest report (retry via ordinary failure path).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "qa-report.schema.json"

_DEFAULT_MEDIA = {
    "video": True,
    "screenshots": False,
    "video_max_seconds": 120,
}


def resolve_qa_media(repo_meta: dict | None) -> dict:
    """Per-repo evidence policy with defaults (video on, screenshots optional)."""
    qa = (repo_meta or {}).get("qa") or {}
    return {
        "video": qa.get("video", _DEFAULT_MEDIA["video"]),
        "screenshots": qa.get("screenshots", _DEFAULT_MEDIA["screenshots"]),
        "video_max_seconds": qa.get("video_max_seconds", _DEFAULT_MEDIA["video_max_seconds"]),
    }


def validate_qa_media_combo(repo: str, repo_meta: dict | None) -> str | None:
    """Reject a repo that disables every evidence mode after defaults apply."""
    media = resolve_qa_media(repo_meta)
    if not media["video"] and not media["screenshots"]:
        return (
            f"repos.yml: {repo}/qa: at least one of video or screenshots must be true "
            "(defaults are video=true, screenshots=false)"
        )
    return None


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text())


def _canonical_video(ticket_id: str, criterion_id: str) -> str:
    return f"specs/{ticket_id}/videos/{criterion_id}.webm"


def _driver_path(ticket_id: str, criterion_id: str) -> str:
    return f"specs/{ticket_id}/qa-drivers/{criterion_id}.mjs"


def _log_path(ticket_id: str, criterion_id: str) -> str:
    return f"specs/{ticket_id}/qa-logs/{criterion_id}.log"


def _has_plan_steps(criterion: Mapping[str, Any]) -> bool:
    return any((step or "").strip() for step in (criterion.get("plan_steps_run") or []))


def _require_driver_and_log(
    cid: str,
    ticket_id: str,
    ledger: set[str],
    contents: Mapping[str, bytes] | None,
    *,
    context: str,
) -> str | None:
    """Canonical qa-drivers/{id}.mjs + non-empty qa-logs/{id}.log in the ledger."""
    driver = _driver_path(ticket_id, cid)
    if driver not in ledger:
        return (
            f"qa-report.json: criterion '{cid}': {context} requires driver {driver} in the ledger"
        )
    log = _log_path(ticket_id, cid)
    if log not in ledger:
        return f"qa-report.json: criterion '{cid}': {context} requires log {log} in the ledger"
    if contents is not None:
        log_bytes = contents.get(log, b"")
        if not log_bytes.strip():
            return f"qa-report.json: criterion '{cid}': log {log} must be non-empty"
    return None


def validate_qa_report(
    raw: bytes | str,
    *,
    ledger: set[str],
    media: dict | None = None,
    ticket_id: str,
    contents: Mapping[str, bytes] | None = None,
) -> str | None:
    """None if the report is honest and consistent; else a rejection reason.

    `media` is the resolved policy from `resolve_qa_media`. Default policy:
    `pass` requires `evidence_kind: live-flow`, empty blocker fields, and the
    canonical video `specs/{ticket}/videos/{id}.webm` present in the ledger,
    owned by that criterion alone, plus matching `qa-drivers/{id}.mjs` and a
    non-empty `qa-logs/{id}.log`. Escape hatch (`video: false`,
    `screenshots: true`): ≥1 screenshot in the ledger instead.

    `fail` / `not-exercised` with non-empty `plan_steps_run` also require the
    canonical driver and non-empty log. `missing-test-data` additionally
    requires a valid `seed_attempt` and non-empty `plan_steps_run`. Genuine
    pre-execution blockers (empty `plan_steps_run`) remain log-free.
    """
    media = media or dict(_DEFAULT_MEDIA)
    try:
        if isinstance(raw, bytes):
            text = raw.decode("utf-8")
        else:
            text = raw
        doc: dict[str, Any] = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return f"qa-report.json: not valid JSON: {exc}"

    validator = Draft202012Validator(_load_schema())
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        json_path = "/".join(str(p) for p in first.path) or "<root>"
        return f"qa-report.json schema violation: {json_path}: {first.message}"

    criteria = doc["criteria"]
    counts = {"pass": 0, "fail": 0, "not-exercised": 0}
    for c in criteria:
        counts[c["verdict"]] += 1

    summary = doc["summary"]
    if (
        summary["pass"] != counts["pass"]
        or summary["fail"] != counts["fail"]
        or summary["not_exercised"] != counts["not-exercised"]
    ):
        return (
            "qa-report.json: summary counts do not match criteria verdicts "
            f"(got pass={summary['pass']} fail={summary['fail']} "
            f"not_exercised={summary['not_exercised']}; "
            f"criteria have pass={counts['pass']} fail={counts['fail']} "
            f"not_exercised={counts['not-exercised']})"
        )

    # all_passed means every criterion passed. Zero criteria → false (nothing proven).
    if criteria:
        expected_all = counts["fail"] == 0 and counts["not-exercised"] == 0
    else:
        expected_all = False
    if summary["all_passed"] != expected_all:
        return (
            "qa-report.json: summary.all_passed is inconsistent with criteria "
            f"(all_passed={summary['all_passed']}, expected {expected_all})"
        )

    video_owners: dict[str, str] = {}

    for c in criteria:
        cid = c["id"]
        if c["verdict"] == "pass":
            if c["evidence_kind"] != "live-flow":
                return (
                    f"qa-report.json: criterion '{cid}': pass requires "
                    f"evidence_kind live-flow, got {c['evidence_kind']}"
                )
            if c["blocker"] is not None or c["blocker_category"] is not None:
                return (
                    f"qa-report.json: criterion '{cid}': pass must have "
                    "blocker and blocker_category null"
                )
            if media.get("video", True):
                videos = c.get("videos") or []
                if not videos:
                    return (
                        f"qa-report.json: criterion '{cid}': pass requires ≥1 video "
                        "when qa.video is true"
                    )
                expected = _canonical_video(ticket_id, cid)
                for v in videos:
                    owner = video_owners.get(v)
                    if owner is not None:
                        return (
                            f"qa-report.json: video {v} is claimed by criteria "
                            f"'{owner}' and '{cid}'"
                        )
                    video_owners[v] = cid
                    if v != expected:
                        return (
                            f"qa-report.json: criterion '{cid}': video path must be "
                            f"exactly {expected}, got {v}"
                        )
                missing = [v for v in videos if v not in ledger]
                if missing:
                    return f"qa-report.json: criterion '{cid}': video not in ledger: " + ", ".join(
                        missing
                    )
                receipt_err = _require_driver_and_log(
                    cid, ticket_id, ledger, contents, context="pass"
                )
                if receipt_err is not None:
                    return receipt_err
            else:
                # Escape hatch: screenshots-only mode.
                shots = c.get("screenshots") or []
                if not shots:
                    return (
                        f"qa-report.json: criterion '{cid}': pass requires ≥1 screenshot "
                        "when qa.video is false and qa.screenshots is true"
                    )
                missing = [s for s in shots if s not in ledger]
                if missing:
                    return (
                        f"qa-report.json: criterion '{cid}': screenshot not in ledger: "
                        + ", ".join(missing)
                    )
        else:
            # not-exercised, or fail (including a live-flow assertion failure).
            if not (c.get("blocker") or "").strip():
                return (
                    f"qa-report.json: criterion '{cid}': {c['verdict']} requires "
                    "a non-empty blocker"
                )
            if c.get("blocker_category") is None:
                return (
                    f"qa-report.json: criterion '{cid}': {c['verdict']} requires blocker_category"
                )
            attempted = _has_plan_steps(c)
            if c["verdict"] == "not-exercised" and c.get("blocker_category") == "missing-test-data":
                seed = c.get("seed_attempt")
                if not isinstance(seed, dict):
                    return (
                        f"qa-report.json: criterion '{cid}': not-exercised with "
                        "missing-test-data requires seed_attempt "
                        "(method ui|api|both plus a non-empty summary of what was tried)"
                    )
                method = seed.get("method")
                seed_summary = (seed.get("summary") or "").strip()
                if method == "none" or method not in ("ui", "api", "both"):
                    return (
                        f"qa-report.json: criterion '{cid}': missing-test-data "
                        "seed_attempt.method must be ui, api, or both "
                        f"(got {method!r}; none means no seed was attempted)"
                    )
                if not seed_summary:
                    return (
                        f"qa-report.json: criterion '{cid}': missing-test-data "
                        "seed_attempt.summary must be non-empty"
                    )
                if not attempted:
                    return (
                        f"qa-report.json: criterion '{cid}': missing-test-data "
                        "requires non-empty plan_steps_run"
                    )
                receipt_err = _require_driver_and_log(
                    cid,
                    ticket_id,
                    ledger,
                    contents,
                    context="missing-test-data",
                )
                if receipt_err is not None:
                    return receipt_err
            elif attempted:
                # fail / not-exercised with attempted live steps need ledger receipts.
                receipt_err = _require_driver_and_log(
                    cid,
                    ticket_id,
                    ledger,
                    contents,
                    context="attempted fail/not-exercised",
                )
                if receipt_err is not None:
                    return receipt_err

    return None


def format_qa_summary_footer(raw: bytes | str | None) -> str | None:
    """PR comment footer like `3 pass / 2 not-exercised`, or None if unreadable."""
    if raw is None:
        return None
    try:
        if isinstance(raw, bytes):
            doc = json.loads(raw.decode("utf-8"))
        else:
            doc = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    summary = doc.get("summary") or {}
    try:
        n_pass = int(summary["pass"])
        n_fail = int(summary["fail"])
        n_ne = int(summary["not_exercised"])
    except (KeyError, TypeError, ValueError):
        return None
    parts = [f"{n_pass} pass", f"{n_fail} fail", f"{n_ne} not-exercised"]
    return " / ".join(parts)
