# AGENTS.md

Guidance for Codex sessions working in this repository.

## What this is

agent_hq: a configuration-driven task engine that runs autonomous engineering
work as agents inside GitHub Actions — tickets flow intake → spec → plan →
implement → review → merge-ready PR, with every human decision an explicit
gate. This repo is the P0 pilot. `docs/architecture.md` is the map;
`docs/roadmap.md` lists deferred work and its restore triggers; the
requirements source document is maintained outside this repo.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # once
.venv/bin/pytest -q                  # full suite (~15s; state tests use real temp git repos)
.venv/bin/ruff check .               # lint (line length 100, config in pyproject.toml)
.venv/bin/agent-hq config validate   # config/ against schemas/
.venv/bin/agent-hq tasks validate    # tasks/ library
docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:1.7.7 -color   # workflow lint
```

CI (`.github/workflows/ci.yml`) runs all five; a change isn't done until all pass.

## Layout

- `engine/` — the engine: `cli` (argparse entrypoint), `config` (registry
  loader + `resolve_binding`), `taskdefs`, `models` (dataclasses mirroring
  `schemas/`), `state` (git-JSON store on the orphan `agent-hq-state`
  branch), `engine` (enqueue, guards, dispatch/sweep), `runner` (three-phase
  prepare/execute/collect + intake), `predicates`, `registry`, `ports`
  (Protocols), `dashboard`, `adapters/` (the only modules naming concrete
  integrations).
- `schemas/` — JSON Schemas (draft 2020-12), validated in CI.
- `tasks/` — the task library, validated generically — no fixed chain, no
  task-name special case. Each `task.yml` declares `handoff.allowed`/`max`;
  what actually happens next is the agent's own `.agent-hq/control.json`
  for that run, validated and applied by the engine
  (`docs/task-authoring.md`). `spec`/`arch-plan`/`arch-approval`/
  `breakdown`/`implement`/`review`/`finalize` are wired; `clinical`/`poll`/
  `qa`/`docs` are defined but unwired — each task.yml header names its
  activation edit. `intake` is engine entry logic
  (`engine/runner.py:intake_ticket`), not a task file —
  `config.projects["initial_task"]` names what a newly accepted ticket
  enqueues.
- `config/` — pilot config; ships `example-*` placeholders (see
  `docs/operations.md` §4). `projects.yml`'s `engine_repo` is the engine's
  own issue tracker (intake, pinned comments, escalations, gate comments) —
  distinct from the work repos in `repos.yml` that `resolve_target_repo`
  selects for code and PRs.
- `.github/workflows/` + `scripts/` — the Actions surface (`docs/operations.md`).

## Invariants (test-enforced — don't break them)

- Engine code never names a concrete adapter outside `engine/registry.py`;
  `tasks/**/task.yml` must contain zero concrete adapter names
  (`tests/test_task_library.py`). Adapter selection is pure config
  (`tests/test_config_swap.py`).
- Every external side effect is idempotent, keyed by an `event_id`
  (`{run_id}:{kind}`); GitHub comments dedupe via `<!--hq:evt:<id>-->`
  markers. Re-delivery must never duplicate a comment, PR, or state entry.
  A handoff-spawned run's own identity is `(source_run_id, handoff_key,
  attempt)` — the target task id is deliberately not part of it, so a
  re-delivered handoff key always resolves to the same run id regardless of
  payload (`engine/models.py:compute_handoff_run_id`).
- State writes go through `GitJsonStateStore.write(fn)`. Writers are
  serialized by the `agent-hq-state` Actions concurrency group; the store's
  bounded (`_MAX_WRITE_ATTEMPTS`) fetch/reset/replay retry fires only on a
  confirmed non-fast-forward push rejection (parsed from `git push
  --porcelain`, not stderr) and is a safety net, not the concurrency model —
  auth/network/server errors fail fast instead.
- The agent child process env is an allowlist built from scratch (PD-5) —
  never pass `AGENT_HQ_TOKEN`/`GITHUB_TOKEN`/`GH_TOKEN` into it, and tokens
  never appear in git argv (env-var credential helper only). The default
  `copilot-cli` child carries ONLY `COPILOT_GITHUB_TOKEN` (a dedicated
  no-repo-access bot seat) — never the engine's own `AGENT_HQ_TOKEN` PAT.
  Copilot's premium-request billing has no per-run USD metering (runs record
  `cost_usd: 0.0`), so per-ticket USD budget caps don't bind under this
  binding — `budget.retries`, the loop guard, in-flight cap, and runtime
  deadlines still do (see `docs/architecture.md` deviation 9).
- `run_id` is causal (`compute_run_id`) for the intake root run; `enqueue`
  is idempotent by run_id. A handoff-spawned run instead derives its id via
  `compute_handoff_run_id` (see above).
- Every completed run emits exactly one control outcome
  (`schemas/control.schema.json`, `additionalProperties:false`) —
  `handoff`/`complete`/`blocked` — schema-validated
  (`engine/handoff.py:validate_handoffs`) before anything in it is trusted;
  a schema-invalid document fails the run, it is never silently ignored.
  Declared `outputs.artifacts` are ledger artifacts
  (`tickets/<id>/artifacts/<run_id>/`, `engine/state.py`
  `write_artifact`/`read_artifact`) — persisted per producing run, restored
  into a child only from its source (parent) run's namespace, and excluded
  from the work-repo patch/commit. Every artifact path a handoff proposes is
  containment-checked (no absolute path, `..`, or symlink escape) before
  it's trusted (`engine/handoff.py`).
- `schemas/state.schema.json`/`event.schema.json`/`control.schema.json`/
  `execute-result.schema.json` and the dataclasses in `engine/models.py`
  must stay in sync (`tests/test_models.py`, `tests/test_schemas_valid.py`
  pin it).
- Deviations from the requirements are ledgered in `docs/architecture.md`
  ("Deviation ledger"); deferred machinery lives in `docs/roadmap.md` with a
  restore trigger — don't re-add it without one.

## Gotchas

- `.hyperclaude/` is gitignored (local planning artifacts, including the
  scope-cut decision doc the deviation ledger summarizes).
- Never commit directly to `main`; work on a feature branch. Merge is a human
  action here too.
- `git add -A` is safe only from a clean tree — check `git status` first.
