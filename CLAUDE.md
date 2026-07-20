# CLAUDE.md

Guidance for Claude Code sessions working in this repository.

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
- `tasks/` — the task library. The P0 chain is wired; `clinical`/`poll`/
  `qa`/`docs` are defined but unwired — each task.yml header names its
  activation edit.
- `config/` — pilot config; ships `example-*` placeholders (see
  `docs/operations.md` §4).
- `.github/workflows/` + `scripts/` — the Actions surface (`docs/operations.md`).

## Invariants (test-enforced — don't break them)

- Engine code never names a concrete adapter outside `engine/registry.py`;
  `tasks/**/task.yml` must contain zero concrete adapter names
  (`tests/test_task_library.py`). Adapter selection is pure config
  (`tests/test_config_swap.py`).
- Every external side effect is idempotent, keyed by an `event_id`
  (`{run_id}:{kind}`); GitHub comments dedupe via `<!--hq:evt:<id>-->`
  markers. Re-delivery must never duplicate a comment, PR, or state entry.
- State writes go through `GitJsonStateStore.write(fn)`. Writers are
  serialized by the `agent-hq-state` Actions concurrency group; the store's
  fetch/reset/reapply retry is a safety net, not the concurrency model.
- The agent child process env is an allowlist built from scratch (PD-5) —
  never pass `AGENT_HQ_TOKEN`/`GITHUB_TOKEN`/`GH_TOKEN` into it, and tokens
  never appear in git argv (env-var credential helper only). The default
  `copilot-cli` child carries ONLY `COPILOT_GITHUB_TOKEN` (a dedicated
  no-repo-access bot seat) — never the engine's own `AGENT_HQ_TOKEN` PAT.
  Copilot's premium-request billing has no per-run USD metering (runs record
  `cost_usd: 0.0`), so per-ticket USD budget caps don't bind under this
  binding — `budget.retries`, the loop guard, in-flight cap, and runtime
  deadlines still do (see `docs/architecture.md` deviation 9).
- `run_id` is causal (`compute_run_id`); `enqueue` is idempotent by run_id.
- `schemas/state.schema.json`/`event.schema.json` and the dataclasses in
  `engine/models.py` must stay in sync (`tests/test_models.py` pins it).
- Deviations from the requirements are ledgered in `docs/architecture.md`
  ("Deviation ledger"); deferred machinery lives in `docs/roadmap.md` with a
  restore trigger — don't re-add it without one.

## Gotchas

- `.hyperclaude/` is gitignored (local planning artifacts, including the
  scope-cut decision doc the deviation ledger summarizes).
- Never commit directly to `main`; work on a feature branch. Merge is a human
  action here too.
- `git add -A` is safe only from a clean tree — check `git status` first.
