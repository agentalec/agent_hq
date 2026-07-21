# `agent-session` (`engine.ports.AgentSession`)

Canonical (P0): `copilot-cli` (default binding, `config/components.yml`);
`claude-code-headless` is the one-line-swap fallback for direct Anthropic
API billing (`CopilotCli` subclasses `ClaudeCodeHeadless` and inherits its
git/PR plumbing unchanged).

## Ops

- `prepare_worktree(run_id, repo, base_commit) -> Path` -- checkout `repo`
  at `base_commit` into an isolated worktree for `run_id`. Fixes artifact
  lineage: every output is traceable to the exact commit the run started
  from. Also where `engine.runner._prepare` restores the run's
  `input_artifacts` (read from the source/parent run's ledger namespace,
  `docs/task-authoring.md` "Artifact namespace") and writes
  `.agent-hq/bundle.json` for the next phase.
- `run(bundle, tools, deadline) -> dict` -- execute the prompt/context
  bundle with an allowlisted tool set (PD-5: the agent never holds
  credentials the host process doesn't hand it) until it finishes or
  `deadline` passes.
- `collect_outputs(worktree, declared) -> list[str]` -- verify and return the artifact
  paths the task definition declared as outputs; missing declared artifacts
  is a failure, not a partial success.
- `build_pr_branch(run_id, worktree, base_commit) -> str` -- push the worktree's
  changes as a branch off `base_commit` and return the PR ref. The pushed
  diff excludes both the declared `outputs.artifacts` and any inherited
  `input_artifacts` -- collect strips both from the worktree before this
  call (`engine.runner._collect_success`), since neither is work-repo code.
- `healthcheck() -> bool`

## Control output and the three artifact payloads

A run's outcome and its handoff proposals are never returned from `run()`
directly -- the agent process itself writes them to disk inside the
worktree, and collect reads them back:

- **The working-tree patch** -- everything else the agent changed in the
  worktree, pushed via `build_pr_branch` as the run's commit/branch. This is
  the only payload that ever reaches the target work repo.
- **`.agent-hq/execute-result.json`** (`schemas/execute-result.schema.json`)
  -- `outcome` (`"success"`/`"failure"`), `usage_known`, nullable
  `cost_usd`/`tokens`. Collect records this unconditionally, before looking
  at anything else; on `"failure"` it runs only retry/failure accounting
  and reads no further payload.
- **`.agent-hq/control.json`** (`schemas/control.schema.json`) -- read only
  when `execute-result.json` reports `"success"`. One of the three control
  outcomes (`handoff`/`complete`/`blocked`,
  `docs/task-authoring.md` "Control outcomes"); validated by
  `engine.handoff.validate_handoffs` before anything in it is trusted.

`.agent-hq/bundle.json` (prepare's own manifest -- prompt, tools, deadline)
and the ledger staging produced by collect (`docs/task-authoring.md`
"Artifact namespace") round out the on-disk handoff between phases; none of
this crosses a job boundary as anything other than plain files in the
shared worktree in P0's single-job runner (`engine.runner.run_task`) --
Task 12 of the hardening plan splits prepare/execute/collect into isolated
Actions jobs and transports the same files as a validated Actions artifact.

## Error semantics

No checkpoint/resume in P0 (D1): a killed session is retried from scratch
by the dispatcher, bounded by `budget.retries`. `run` never partially
succeeds from the caller's point of view -- it returns a complete result or
raises/times out.
