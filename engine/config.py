"""Config registry loader (§6).

Reads the five YAML registries (components, repos, projects, approvers,
budgets), schema-validates each, and resolves per-port adapter bindings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REGISTRIES = ("components", "repos", "projects", "approvers", "budgets")


class ConfigError(Exception):
    """Raised with every schema violation found across all registry files."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class Config:
    components: dict
    repos: dict
    projects: dict
    approvers: dict
    budgets: dict


def load_config(config_dir: str | Path, schemas_dir: str | Path) -> Config:
    config_dir = Path(config_dir)
    schemas_dir = Path(schemas_dir)

    errors: list[str] = []
    loaded: dict[str, dict] = {}
    for name in REGISTRIES:
        yml_path = config_dir / f"{name}.yml"
        schema = json.loads((schemas_dir / f"{name}.schema.json").read_text())
        try:
            instance = yaml.safe_load(yml_path.read_text()) or {}
        except FileNotFoundError:
            errors.append(f"{yml_path.name}: <root>: file is missing")
            continue
        except yaml.YAMLError as exc:
            errors.append(f"{yml_path.name}: <root>: YAML parse error: {exc}")
            continue
        validator = Draft202012Validator(schema)
        for error in validator.iter_errors(instance):
            json_path = "/".join(str(p) for p in error.path) or "<root>"
            errors.append(f"{yml_path.name}: {json_path}: {error.message}")
        loaded[name] = instance

    if errors:
        raise ConfigError(errors)
    return Config(**loaded)


def resolve_binding(
    config: Config,
    port: str,
    task_binding_name: str | None,
    ticket_labels: list[str],
) -> str:
    """Resolve the concrete adapter name for a port.

    Precedence: (1) an allowlisted `hq:<port>=<adapter>` ticket label, else
    (2) for the gate port, a non-"default" logical binding name resolved
    through components.gate.named, else (3) the port's configured adapter.
    """
    if port not in config.components:
        raise ConfigError([f"components.yml: no binding configured for port '{port}'"])
    binding = config.components[port]
    label_prefix = f"hq:{port}="
    # ponytail: allowlist gates only the port, not the adapter value; Task 7's
    # registry rejects unknown adapter names, which backstops a bogus label.
    if label_prefix in config.components.get("label_overrides", []):
        for label in ticket_labels:
            if label.startswith(label_prefix):
                return label[len(label_prefix) :]

    if port == "gate" and task_binding_name not in (None, "default"):
        named = binding.get("named", {})
        if task_binding_name in named:
            return named[task_binding_name]

    return binding["adapter"]


def validate_task_bindings(taskdefs: dict, config: Config) -> list[str]:
    """Reject a task-declared `components` port with no configured binding,
    and a `projects.initial_task` that doesn't resolve to a loaded task.

    A task's `components` map (port -> logical binding name) only makes
    sense for a port components.yml actually configures. A task that
    declares no `components` (e.g. qa) stays registered-but-unwired.
    """
    errors: list[str] = []
    for task_id, taskdef in taskdefs.items():
        for port in taskdef.get("components", {}):
            if port not in config.components:
                errors.append(
                    f"{task_id}: components.{port}: no binding configured in components.yml"
                )
    initial_task = config.projects.get("initial_task")
    if initial_task not in taskdefs:
        errors.append(
            f"projects.yml: initial_task: '{initial_task}' is not a loaded task"
        )
    return errors
