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
  task-name special case, and **no declared route**: a `task.yml` says what a
  task *is*, never what may follow it. What happens next is the queue a run
  declares in its own `.agent-hq/control.json`, validated and applied by the
  engine (`docs/task-authoring.md`), bounded only by
  `budgets.max_queue_length`. Every task in the library is queueable, so a
  task is "unwired" only in the sense that no prompt currently tells a run to
  queue it — there is no activation edit. `spec`/`implement`/`review`/`qa`/
  `finalize` are what the pilot's prompts actually route through (with an
  `implement`↔`review` loop);
  `arch-plan`/`arch-approval`/`breakdown`/`clinical`/`poll`/`docs` are defined
  but nothing queues them yet. `intake` is engine entry logic
  (`engine/runner.py:intake_ticket`), not a task file —
  `config.projects["initial_task"]` names what a newly accepted ticket
  enqueues, and `final_task` names the run whose completion finishes the
  ticket — a queue draining on any other task stopped early and BLOCKs.
- `config/` — pilot config; ships `example-*` placeholders (see
  `docs/operations.md` §4). `projects.yml`'s `engine_repo` is the engine's
  own issue tracker (intake, pinned comments, escalations, gate comments) —
  distinct from the work repos in `repos.yml` that `resolve_target_repo`
  selects for code and PRs. `repos.yml`'s `setup` map (task id → shell
  command, `default` for the rest) is run in the worktree before the agent
  starts — structured setup is config, never a prompt (`docs/task-authoring.md`).
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
- State writes go through `GitJsonStateStore.write(fn)`. The store's bounded
  (`_MAX_WRITE_ATTEMPTS`) fetch/reset/replay retry is the concurrency model —
  a rejected push is the CAS that serializes concurrent writers across
  tickets (`docs/operations.md` §11). It fires only on a confirmed
  non-fast-forward push rejection (parsed from `git push --porcelain`, not
  stderr) — auth/network/server errors fail fast instead. No Actions
  concurrency group backs it up: `run.yml`/`intake.yml` are keyed per
  run/issue, because one shared group made bursts cancel each other's pending
  runs (`docs/operations.md` §11).
- The agent child process env is an allowlist built from scratch (PD-5) —
  never pass `AGENT_HQ_TOKEN`/`GITHUB_TOKEN`/`GH_TOKEN` into it, and tokens
  never appear in git argv (env-var credential helper only). The default
  `copilot-cli` child carries ONLY `COPILOT_GITHUB_TOKEN` (a dedicated
  no-repo-access bot seat) — never the engine's own `AGENT_HQ_TOKEN` PAT.
  Copilot bills tokens as AI credits, and the CLI prints a session's credits
  and token counts on stderr, so a run's `cost_usd` is the billed figure
  (`_parse_usage`, 1 credit = $0.01) and the USD caps in `budgets.yml` do
  bind — alongside `budget.retries`, `loop_guard.max_runs` (the only
  structural ceiling; there is no depth guard, and `CANCELLED` runs don't
  count), the in-flight cap, and runtime deadlines (see
  `docs/architecture.md` deviation 9).
- `run_id` is causal (`compute_run_id`) for the intake root run; `enqueue`
  is idempotent by run_id. A handoff-spawned run instead derives its id via
  `compute_handoff_run_id` (see above).
- Every completed run emits exactly one control outcome
  (`schemas/control.schema.json`, `additionalProperties:false`) —
  `queue`/`blocked` — schema-validated
  (`engine/handoff.py:validate_queue`) before anything in it is trusted;
  a schema-invalid document fails the run, it is never silently ignored. An
  empty `queue` is how a run says "nothing further"; there is no `complete`.
- A ticket's queue is explicit: `QUEUED` runs ordered by `queue_seq`
  (`engine.engine.queue_positions` falls back to array index for runs written
  before the field). Any run may revise the remaining route at collect —
  entries are added in declared order, and removal is explicit (`cancel` by
  key, or `cancel_pending`). **Omission never cancels**, so a fan-out branch
  cannot drop its sibling by saying nothing; a removed entry becomes a
  `CANCELLED` run with a `run.cancelled` event, never a deletion, and
  `CANCELLED` runs don't count against `loop_guard.max_runs`. A retry inherits
  the `queue_seq` of the attempt it replaces.
- `parent_run_id` is who *enqueued* a run (identity + provenance; immutable —
  `reenqueue_same` recomputes retry ids from it). `input_from_run_id` is whose
  output it *reads*, resolved and recorded at claim
  (`engine.engine.resolve_input_source`: nearest `SUCCEEDED` run ahead of it in
  the queue, else the enqueuer). Don't conflate them — with a multi-entry
  queue, whoever enqueued `review` need not be who produced its input.
- Declared `outputs.artifacts` are ledger artifacts
  (`tickets/<id>/artifacts/<run_id>/`, `engine/state.py`
  `write_artifact`/`read_artifact`) — persisted per producing run as **bytes**
  (not all artifacts are text), restored into a run only from its
  `input_from_run_id` namespace, and excluded from the work-repo patch/commit. An
  entry ending in `/` is a directory artifact: the engine collects whatever
  files it holds, zero or more, for output a task can't name in advance
  (`engine/runner.py:_expand_declared`); plain entries stay required. Every
  artifact path a handoff proposes is containment-checked (no absolute path,
  `..`, or symlink escape) before it's trusted (`engine/handoff.py`).
- `schemas/state.schema.json`/`event.schema.json`/`control.schema.json`/
  `execute-result.schema.json` and the dataclasses in `engine/models.py`
  must stay in sync (`tests/test_models.py`, `tests/test_schemas_valid.py`
  pin it).
- Deviations from the requirements are ledgered in `docs/architecture.md`
  ("Deviation ledger"); deferred machinery lives in `docs/roadmap.md` with a
  restore trigger — don't re-add it without one.
- Every new feature gets a row in `ROADMAP.md` ("Shipped") in the same
  change that ships it — one line, what it is and where it lives. If it was
  listed under "Planned" there (or deferred in `docs/roadmap.md`), drop that
  entry in the same change. New planned work goes under "Planned".

## Gotchas

- `.hyperclaude/` is gitignored (local planning artifacts, including the
  scope-cut decision doc the deviation ledger summarizes).
- Never commit directly to `main`; work on a feature branch. Merge is a human
  action here too.
- `git add -A` is safe only from a clean tree — check `git status` first.
