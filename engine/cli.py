"""agent-hq command line entrypoint.

Subcommands are stubs for now -- each raises SystemExit until its phase of
the P0 plan lands.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from engine.config import ConfigError, load_config
from engine.taskdefs import TaskDefError, load_all, validate_library


def resolve_repo_root(repo_root_arg: str | None) -> Path:
    """Resolve the repo root once per invocation.

    Uses --repo-root if given, otherwise the package's parent dir if that
    looks like a repo checkout, otherwise the current working directory.
    """
    if repo_root_arg:
        return Path(repo_root_arg).resolve()
    pkg_parent = Path(__file__).resolve().parent.parent
    if (pkg_parent / ".git").exists():
        return pkg_parent
    return Path.cwd()


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", help="Path to the repo root (default: auto-detected)")
    parser.add_argument("--state", help="Path to the engine state file")


def _not_implemented(args: argparse.Namespace, repo_root: Path) -> None:
    raise SystemExit("not yet implemented")


def _config_validate(args: argparse.Namespace, repo_root: Path) -> None:
    try:
        load_config(repo_root / "config", repo_root / "schemas")
    except ConfigError as exc:
        for error in exc.errors:
            print(error)
        raise SystemExit(1) from exc
    print("config OK")


def _tasks_validate(args: argparse.Namespace, repo_root: Path) -> None:
    tasks_dir = repo_root / "tasks"
    if not tasks_dir.exists():
        print("no tasks/ directory")
        return
    try:
        taskdefs = load_all(tasks_dir, repo_root / "schemas")
    except TaskDefError as exc:
        for error in exc.errors:
            print(error)
        raise SystemExit(1) from exc
    errors = validate_library(taskdefs)
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)
    print("tasks OK")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-hq")
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("config", help="Config-related commands")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_validate = config_sub.add_parser("validate", help="Validate engine config")
    _add_common_args(config_validate)
    config_validate.set_defaults(func=_config_validate)

    tasks_parser = subparsers.add_parser("tasks", help="Task-related commands")
    tasks_sub = tasks_parser.add_subparsers(dest="tasks_command", required=True)
    tasks_validate = tasks_sub.add_parser("validate", help="Validate task definitions")
    _add_common_args(tasks_validate)
    tasks_validate.set_defaults(func=_tasks_validate)

    intake_parser = subparsers.add_parser("intake", help="Intake a new task")
    _add_common_args(intake_parser)
    intake_parser.set_defaults(func=_not_implemented)

    pr_merged_parser = subparsers.add_parser("pr-merged", help="Handle a merged PR event")
    _add_common_args(pr_merged_parser)
    pr_merged_parser.set_defaults(func=_not_implemented)

    dispatch_parser = subparsers.add_parser("dispatch", help="Dispatch queued work")
    _add_common_args(dispatch_parser)
    dispatch_parser.set_defaults(func=_not_implemented)

    health_parser = subparsers.add_parser("health", help="Report engine health")
    _add_common_args(health_parser)
    health_parser.set_defaults(func=_not_implemented)

    run_parser = subparsers.add_parser("run", help="Run a task phase")
    _add_common_args(run_parser)
    run_parser.add_argument(
        "--phase",
        choices=["register", "prepare", "execute", "collect"],
        help="Phase of the run to execute",
    )
    run_parser.add_argument("--run-id", help="Run identifier")
    run_parser.add_argument("--execute-outcome", help="Outcome recorded by the execute phase")
    run_parser.add_argument("--gate-passed", help="Whether the review gate passed")
    run_parser.add_argument("--workflow-run-id", help="GitHub Actions workflow run id")
    run_parser.set_defaults(func=_not_implemented)

    dashboard_parser = subparsers.add_parser("dashboard", help="Render the status dashboard")
    _add_common_args(dashboard_parser)
    dashboard_parser.set_defaults(func=_not_implemented)

    mint_token_parser = subparsers.add_parser("mint-token", help="Mint a GitHub App token")
    _add_common_args(mint_token_parser)
    mint_token_parser.set_defaults(func=_not_implemented)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = resolve_repo_root(getattr(args, "repo_root", None))
    args.func(args, repo_root)


if __name__ == "__main__":
    main()
