"""PA-2 acceptance test: adapter selection is pure configuration.

Resolves the `spec` task's `spec-approval` gate binding through the exact
path tasks use (`resolve_binding` -> `build_adapter`), once against the real
pilot config (-> `pr-review` / `PrReviewGate`) and once against the same
config with only `components.yml`'s `gate.named.spec-approval` value swapped
(-> a fake adapter registered under a different name). Neither the task
definition nor engine code changes between the two runs.
"""

from __future__ import annotations

import copy
import sys
import types
from pathlib import Path

import pytest

from engine.config import load_config, resolve_binding
from engine.registry import _ADAPTERS, build_adapter
from engine.taskdefs import load_task

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
SCHEMAS_DIR = REPO_ROOT / "schemas"


class FakeGate:
    def __init__(self, settings: dict):
        self.settings = settings


@pytest.fixture
def registered_fake_gate(monkeypatch):
    """Register ("gate", "fake-gate") in the adapter registry, the same way
    a real adapter module would, without a real module existing on disk."""
    module_path = "tests.test_config_swap"
    fake_module = types.ModuleType(module_path)
    fake_module.FakeGate = FakeGate
    monkeypatch.setitem(sys.modules, module_path, fake_module)
    monkeypatch.setitem(_ADAPTERS, ("gate", "fake-gate"), f"{module_path}:FakeGate")


def _resolve_and_build(config, taskdef, monkeypatch):
    gate_spec = taskdef["gates"]["post"][0]
    adapter_name = resolve_binding(config, "gate", gate_spec["adapter"], [])
    if adapter_name == "pr-review":
        # No network call at construction: PrReviewGate.__init__ only reads
        # settings and builds a client -- prove it by making any actual
        # network call fail loudly if one were attempted.
        monkeypatch.setattr(
            "requests.request",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("network call at init")),
        )
    settings = {
        "repo": next(iter(config.repos)),
        "approvers": config.approvers,
        "default_base": "main",
    }
    adapter = build_adapter("gate", adapter_name, settings)
    return adapter_name, adapter


def test_gate_binding_swaps_via_config_only(monkeypatch, registered_fake_gate):
    config = load_config(CONFIG_DIR, SCHEMAS_DIR)
    taskdef = load_task(REPO_ROOT / "tasks" / "spec", SCHEMAS_DIR)
    assert taskdef["gates"]["post"][0]["adapter"] == "spec-approval"

    real_name, real_adapter = _resolve_and_build(config, taskdef, monkeypatch)
    assert real_name == "pr-review"
    from engine.adapters.pr_review import PrReviewGate

    assert isinstance(real_adapter, PrReviewGate)

    swapped_config = copy.deepcopy(config)
    swapped_config.components["gate"]["named"]["spec-approval"] = "fake-gate"

    fake_name, fake_adapter = _resolve_and_build(swapped_config, taskdef, monkeypatch)
    assert fake_name == "fake-gate"
    assert isinstance(fake_adapter, FakeGate)

    assert type(real_adapter) is not type(fake_adapter)
