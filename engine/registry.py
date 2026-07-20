"""Adapter registry (PA-2): resolves a (port, adapter_name) config binding to
a live adapter instance.

Adapter modules (`engine/adapters/*`) land in later tasks; entries below are
"module:ClassName" import paths, resolved lazily via `importlib` so this
registry -- and code/tests that depend only on it -- work before those
modules exist.
"""

from __future__ import annotations

import importlib

# (port, adapter_name) -> "module.path:ClassName"
_ADAPTERS: dict[tuple[str, str], str] = {
    ("tracker", "github-issues"): "engine.adapters.github_issues:GithubIssuesTracker",
    ("messaging", "github-comment"): "engine.adapters.github_comment:GithubCommentMessaging",
    ("gate", "pr-review"): "engine.adapters.pr_review:PrReviewGate",
    ("executor", "claude-code-headless"): (
        "engine.adapters.claude_code_headless:ClaudeCodeHeadless"
    ),
    ("agent-session", "claude-code-headless"): (
        "engine.adapters.claude_code_headless:ClaudeCodeHeadless"
    ),
    ("executor", "copilot-cli"): "engine.adapters.copilot_cli:CopilotCli",
    ("agent-session", "copilot-cli"): "engine.adapters.copilot_cli:CopilotCli",
}


def build_adapter(port: str, adapter_name: str, settings: dict):
    """Construction contract: every adapter class takes exactly one positional
    dict argument (its components.yml `settings`); credentials come from env,
    never settings."""
    key = (port, adapter_name)
    if key not in _ADAPTERS:
        known = sorted(name for p, name in _ADAPTERS if p == port)
        raise ValueError(
            f"no adapter '{adapter_name}' registered for port '{port}' "
            f"(known adapters for '{port}': {known or 'none'})"
        )
    module_path, class_name = _ADAPTERS[key].split(":")
    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)
    return adapter_cls(settings)
