import shutil
from pathlib import Path

import pytest

from engine.config import Config, ConfigError, load_config, resolve_binding

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
SCHEMAS_DIR = REPO_ROOT / "schemas"


def test_pilot_config_loads_clean():
    config = load_config(CONFIG_DIR, SCHEMAS_DIR)
    assert config.components["executor"]["adapter"] == "copilot-cli"
    assert "example-org/product-be" in config.repos
    assert config.projects["intake_label"] == "hq:intake"
    assert config.projects["engine_repo"] == "example-org/agent-hq"
    assert "product-owners" in config.approvers["groups"]
    assert config.budgets["ticket_cap_usd"] == 25


def test_invalid_config_reports_violations_from_every_file(tmp_path):
    bad_config = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, bad_config)

    # repos.yml: role must be a string enum, not an integer
    (bad_config / "repos.yml").write_text(
        "example-org/product-be:\n  role: 1\n  branch_prefix: agent-hq\n  product_area: backend\n"
    )
    # budgets.yml: ticket_cap_usd must be a number, not a string
    (bad_config / "budgets.yml").write_text(
        "ticket_cap_usd: nope\nin_flight_cap: 3\nloop_guard: {max_runs: 25, max_depth: 12}\n"
    )

    with pytest.raises(ConfigError) as excinfo:
        load_config(bad_config, SCHEMAS_DIR)

    errors = excinfo.value.errors
    assert any("repos.yml" in e for e in errors)
    assert any("budgets.yml" in e for e in errors)


def _config(components: dict) -> Config:
    return Config(components=components, repos={}, projects={}, approvers={}, budgets={})


def test_resolve_binding_defaults_to_port_adapter():
    config = _config({"executor": {"adapter": "claude-code-headless"}, "label_overrides": []})
    assert resolve_binding(config, "executor", "default", []) == "claude-code-headless"
    assert resolve_binding(config, "executor", None, []) == "claude-code-headless"


def test_resolve_binding_gate_named_logical_binding():
    config = _config(
        {
            "gate": {"adapter": "pr-review", "named": {"spec-approval": "human-review"}},
            "label_overrides": [],
        }
    )
    assert resolve_binding(config, "gate", "spec-approval", []) == "human-review"
    assert resolve_binding(config, "gate", "default", []) == "pr-review"


def test_resolve_binding_allowlisted_label_override_wins():
    config = _config(
        {"executor": {"adapter": "claude-code-headless"}, "label_overrides": ["hq:executor="]}
    )
    assert resolve_binding(config, "executor", "default", ["hq:executor=codex"]) == "codex"


def test_resolve_binding_non_allowlisted_label_is_ignored():
    config = _config({"executor": {"adapter": "claude-code-headless"}, "label_overrides": []})
    assert resolve_binding(config, "executor", "default", ["hq:executor=codex"]) == "claude-code-headless"
