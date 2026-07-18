# `agent-session` (`engine.ports.AgentSession`)

Canonical (P0): `claude-code-headless`.

## Ops

- `prepare_worktree(run_id, repo, base_commit) -> Path` -- checkout `repo`
  at `base_commit` into an isolated worktree for `run_id`. Fixes artifact
  lineage: every output is traceable to the exact commit the run started
  from.
- `run(bundle, tools, deadline) -> dict` -- execute the prompt/context
  bundle with an allowlisted tool set (PD-5: the agent never holds
  credentials the host process doesn't hand it) until it finishes or
  `deadline` passes.
- `collect_outputs(worktree, declared) -> list[str]` -- verify and return the artifact
  paths the task definition declared as outputs; missing declared artifacts
  is a failure, not a partial success.
- `build_pr_branch(run_id, worktree, base_commit) -> str` -- push the worktree's
  changes as a branch off `base_commit` and return the PR ref.
- `healthcheck() -> bool`

## Error semantics

No checkpoint/resume in P0 (D1): a killed session is retried from scratch
by the dispatcher, bounded by `budget.retries`. `run` never partially
succeeds from the caller's point of view -- it returns a complete result or
raises/times out.
