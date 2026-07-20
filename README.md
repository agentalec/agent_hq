# agent_hq

agent_hq is a configuration-driven task engine that runs autonomous
engineering work — tickets flow through spec, plan, implement, review, and
merge-ready PRs — as agents inside GitHub Actions, orchestrated entirely from
YAML task and config files rather than bespoke workflow code. Every human
decision (spec approval, architecture approval, merge) is an explicit gate;
nothing auto-merges. This repository holds the P0 pilot.

## The P0 pipeline

```
GitHub issue (hq:intake label)
  -> intake            records the ticket, enqueues `spec`
  -> spec              writes specs/<ticket>/spec.md          [gate: product-owners]
  -> arch-plan         writes specs/<ticket>/plan.md           [gate: architects, beyond-crud only]
  -> breakdown         writes specs/<ticket>/tasks.md
  -> implement         code + tests, opens a draft PR
  -> review            writes specs/<ticket>/review.md
  -> finalize          posts closing summary, undrafts PR, requests reviewers
  -> human merge                                                [gate: always human]
```

Each arrow is a task definition (`tasks/<id>/task.yml`); `dispatch.yml`
sweeps queued/running work every 15 minutes and triggers `run.yml`, which
executes one task phase (prepare/execute/collect) inside the project
devcontainer. State lives on an orphan `agent-hq-state` branch, serialized
through an Actions concurrency group. A static dashboard (`pages.yml`)
reports ticket/run state.

## Quickstart

```bash
pip install -e '.[dev]'
pytest
agent-hq config validate
agent-hq tasks validate
```

## Config-only binding swap

Every side effect the engine performs crosses a **port** (tracker, executor,
agent-session, messaging, gate, ...); task definitions and engine code bind
to a port by name, never to a concrete adapter class. `config/components.yml`
selects which adapter backs each port, and `engine.registry.build_adapter`
resolves that selection at runtime. Swapping an adapter — including a
task-specific override such as the `spec` task's `spec-approval` gate
binding — is a one-line config change; it touches zero task-definition and
zero engine code (`tests/test_config_swap.py` proves this end to end).

**Note:** `config/` ships `example-*` placeholder org/repo/username values
pending the real pilot values (requirements §12); replace them before the
first real intake. See `docs/operations.md` §4.

## Extending the pipeline

- **New task type:** add `tasks/<id>/task.yml` (+ its `prompts/` and
  `checklists/` skills) per `schemas/task.schema.json`, point a parent task's
  `on_success.enqueue` at it, merge via PR — zero engine changes.
  `agent-hq tasks validate` and `tests/test_task_library.py` gate it in CI.
  The P1 tasks (`clinical`, `poll`, `qa`, `docs`) are already defined but
  unwired; each task.yml header names its one-line activation edit.
- **New adapter:** implement the port's Protocol from `engine/ports.py`,
  register the class in `engine/registry.py`, select it in
  `config/components.yml`. Prompts/skills and task definitions never change.

## Docs

- [`docs/architecture.md`](docs/architecture.md) — the P0 flow, ports/adapters, credential boundary, retry semantics
- [`docs/operations.md`](docs/operations.md) — day-to-day operation of the GitHub Actions surface
- [`docs/roadmap.md`](docs/roadmap.md) — deferred work and restore triggers
- [`docs/ports/README.md`](docs/ports/README.md) — the port/adapter contract
- [`constitution.md`](constitution.md) — conventions every task and agent run follows
