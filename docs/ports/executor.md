# `executor` (`engine.ports.Executor`)

Canonical (P0): `claude-code-headless`. `start`/`result` are thin, unused
stubs in P0 -- the runner drives the actual work through the `agent-session`
port's isolated prepare/execute/collect methods instead (`docs/ports/
agent-session.md`, hardening plan Task 12); this Protocol documents the
shape a future async dispatch model would use.

## Ops

- `start(run_ctx: TaskRun)` -- launch the run (e.g. dispatch a workflow run)
  for a `TaskRun` already claimed (`QUEUED -> RUNNING`) in the state store.
  Keyed by `run_ctx.run_id`; starting an already-started run is a no-op.
- `result(run_ctx: TaskRun) -> dict | None` -- poll for the run's outcome
  (cost, tokens, artifacts, `output_commit`/`pr_ref`); `None` while still in
  flight.
- `healthcheck() -> bool`

## Error semantics

`start`/`result` raise on transport failure; the caller treats that as
"unknown", never as a run failure. A run whose deadline passed with no
result is handled by the sweep (stale `RUNNING` -> retry or `BLOCKED`), not
by this adapter.
