"""Workflow YAML that duplicates a Python constant, pinned against it.

The Actions surface is the one place engine facts get restated in a language
no test runs: `.github/workflows/intake.yml` filters out the engine's own
status labels, and it has to name them, because a GitHub `if:` cannot import
`engine.engine.STATUS_LABELS`. Same discipline as
`tests/test_dashboard_assets.py` (a JS invariant checked from Python) and
`tests/test_task_library.py` (task YAML checked against engine rules).
"""

import json
import re
from pathlib import Path

import yaml

from engine.engine import STATUS_LABELS

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def test_intake_ignores_exactly_the_engine_owned_status_labels():
    """Intake must skip a `labeled` event carrying a status label the engine
    wrote, or the engine re-admits its own blocked ticket in a loop (#20).

    Both directions matter. A label missing from the workflow list reopens the
    loop for that status; a label listed here that is NOT engine-owned would
    silently stop a human's relabel from re-admitting a ticket.
    """
    guard = yaml.safe_load((WORKFLOWS / "intake.yml").read_text())["jobs"]["intake"]["if"]

    listed = re.search(r"fromJSON\('(\[.*?\])'\)", guard)
    assert listed, f"no fromJSON label list in the intake guard: {guard}"
    assert set(json.loads(listed.group(1))) == set(STATUS_LABELS.values())

    # The list only applies to `labeled`; `opened` carries no `github.event.label`
    # at all, and an intake that skipped it would never admit a new ticket.
    assert "github.event.action != 'labeled'" in guard


def test_intake_still_wakes_for_the_admission_label():
    """`hq:intake` is the human gesture the whole workflow exists to catch, so
    it must never end up on the ignore list -- which `intake_label` moving in
    config could otherwise do unnoticed."""
    from engine.config import load_config

    root = Path(__file__).resolve().parent.parent
    config = load_config(root / "config", root / "schemas")
    guard = yaml.safe_load((WORKFLOWS / "intake.yml").read_text())["jobs"]["intake"]["if"]
    listed = json.loads(re.search(r"fromJSON\('(\[.*?\])'\)", guard).group(1))
    assert config.projects["intake_label"] not in listed
