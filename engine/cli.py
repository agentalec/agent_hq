"""agent-hq command line entrypoint.

Subcommands are stubs for now -- each raises SystemExit until its phase of
the P0 plan lands.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.config import ConfigError, load_config, validate_task_bindings
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
    parser.add_argument("--state", help="Path to the state-store worktree")


def _load(repo_root: Path):
    """Load config + task library for a runtime command, exiting with the
    collected validation errors on failure."""
    try:
        config = load_config(repo_root / "config", repo_root / "schemas")
        taskdefs = load_all(repo_root / "tasks", repo_root / "schemas")
    except (ConfigError, TaskDefError) as exc:
        for error in exc.errors:
            print(error)
        raise SystemExit(1) from exc
    return config, taskdefs


def _store(args: argparse.Namespace):
    from engine.state import GitJsonStateStore

    if not args.state:
        raise SystemExit("--state (state-store worktree path) is required")
    return GitJsonStateStore(args.state)


def _intake(args: argparse.Namespace, repo_root: Path) -> None:
    from engine.runner import intake_ticket

    config, taskdefs = _load(repo_root)
    result = intake_ticket(args.issue, args.event_key, config, taskdefs, _store(args))
    print(result)


def _dispatch(args: argparse.Namespace, repo_root: Path) -> None:
    from engine.engine import dispatch
    from engine.runner import GithubWorkflowApi

    config, taskdefs = _load(repo_root)
    triggered = dispatch(config, taskdefs, _store(args), GithubWorkflowApi(), issue=args.issue)
    print(f"triggered: {triggered}")


def _run(args: argparse.Namespace, repo_root: Path) -> None:
    from engine.runner import run_task

    config, taskdefs = _load(repo_root)
    result = run_task(
        args.run_id, args.phase, config, taskdefs, _store(args),
        execute_outcome=args.execute_outcome,
    )
    if args.phase == "prepare":
        # scripts/run-phases.sh greps the last stdout line for this; keep it
        # a single deterministic token, not the (multiline) prompt bundle.
        print(f"claimed={'true' if result.get('claimed') else 'false'}")
    else:
        print(json.dumps(result))


def _dashboard(args: argparse.Namespace, repo_root: Path) -> None:
    """Rebuild `dashboard.json` from a state worktree.

    The engine emits this on every state write; this is the manual path, for
    inspecting the projection or repairing a branch whose copy went missing.
    The page itself is static (`dashboard/`) and is deployed from source.
    """
    from engine.dashboard import document, write_document

    if not args.state:
        raise SystemExit("--state (state-store worktree path) is required")
    print(write_document(document(args.state), args.out or args.state))


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
        config = load_config(repo_root / "config", repo_root / "schemas")
    except (TaskDefError, ConfigError) as exc:
        for error in exc.errors:
            print(error)
        raise SystemExit(1) from exc
    errors = validate_library(taskdefs)
    errors += validate_task_bindings(taskdefs, config)
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

    intake_parser = subparsers.add_parser("intake", help="Intake a new ticket")
    _add_common_args(intake_parser)
    intake_parser.add_argument(
        "--issue", required=True, help="Issue number in the configured engine_repo"
    )
    intake_parser.add_argument("--event-key", required=True, help="Source-stable event key")
    intake_parser.set_defaults(func=_intake)

    dispatch_parser = subparsers.add_parser("dispatch", help="Sweep and trigger queued work")
    _add_common_args(dispatch_parser)
    dispatch_parser.add_argument(
        "--issue",
        help="Scan only this ticket (fast path for a wake-up producer); omit for a full scan",
    )
    dispatch_parser.set_defaults(func=_dispatch)

    run_parser = subparsers.add_parser("run", help="Run a task phase")
    _add_common_args(run_parser)
    run_parser.add_argument(
        "--phase",
        choices=["prepare", "execute", "collect"],
        required=True,
        help="Phase of the run to execute",
    )
    run_parser.add_argument("--run-id", required=True, help="Run identifier")
    run_parser.add_argument("--execute-outcome", help="Outcome recorded by the execute phase")
    run_parser.set_defaults(func=_run)

    dashboard_parser = subparsers.add_parser(
        "dashboard", help="Rebuild dashboard.json from a state worktree"
    )
    _add_common_args(dashboard_parser)
    dashboard_parser.add_argument("--out", help="Output directory (default: the state worktree)")
    dashboard_parser.set_defaults(func=_dashboard)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = resolve_repo_root(getattr(args, "repo_root", None))
    args.func(args, repo_root)


if __name__ == "__main__":
    main()
