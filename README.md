# agent_hq

agent_hq is a configuration-driven task engine that runs autonomous
engineering work — tickets flow through spec, plan, implement, review, and
merge-ready PRs — as agents inside GitHub Actions, orchestrated entirely from
YAML task and config files rather than bespoke workflow code. Every human
decision (spec approval, architecture approval, merge) is an explicit gate;
nothing auto-merges. This repository holds the P0 pilot.

## The wired task graph

There is no fixed chain in the engine -- every task declares which task ids
it may hand off to (`handoff.allowed`) and how many handoffs it may propose
per run (`handoff.max`); the agent itself chooses among those options at
runtime by writing `.agent-hq/control.json`, and the engine validates and
applies the choice (`docs/task-authoring.md`). The pilot's task library
happens to wire up a linear graph:

```
GitHub issue (hq:intake label, in config.projects["engine_repo"])
  -> intake            engine entry logic (no task file); enqueues
                        config.projects["initial_task"] (`spec`)
  -> spec               writes specs/<ticket>/spec.md          [gate: product-owners]
  -> arch-plan          writes specs/<ticket>/plan.md
  -> arch-approval      confirms the plan artifacts             [gate: architects, beyond-crud only]
  -> breakdown          writes specs/<ticket>/tasks.md; hands off one
                        `implement` per configured repo the ticket touches
  -> implement          code + tests, opens a draft PR
  -> review             writes specs/<ticket>/review.md
  -> finalize           posts closing summary, undrafts PR, requests reviewers
  -> human merge                                                [gate: always human]
```

Each arrow after intake is one task definition (`tasks/<id>/task.yml`)
proposing a handoff to the next; `dispatch.yml` sweeps queued/running work
every 15 minutes and triggers `run.yml`, which executes one task phase
(prepare/execute/collect) inside the project devcontainer. The issue is the
control plane, produced work lives on target-repo branches and selected
draft PRs, and orchestration memory lives on an orphan `agent-hq-state`
branch. A static dashboard (`pages.yml`) reports ticket/run state. See
[where work and memory live](docs/architecture.md#where-work-and-memory-live)
for the exact lifecycle and storage paths, and
[`docs/task-authoring.md`](docs/task-authoring.md) for the generic task
model (handoffs, control outcomes, artifact namespace, gates, budgets).

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/agent-hq config validate
.venv/bin/agent-hq tasks validate
```

See [`docs/local-testing.md`](docs/local-testing.md) for workflow lint,
devcontainer/Copilot smoke tests, live sandbox checks, and credential needs.

## Config-only binding swap

Every side effect the engine performs crosses a **port** (tracker, executor,
agent-session, messaging, gate, ...); task definitions and engine code bind
to a port by name, never to a concrete adapter class. `config/components.yml`
selects which adapter backs each port, and `engine.registry.build_adapter`
resolves that selection at runtime. Swapping an adapter — including a
task-specific override such as the `spec` task's `spec-approval` gate
binding — is a one-line config change; it touches zero task-definition and
zero engine code (`tests/test_config_swap.py` proves this end to end).

Agent runs are billed through GitHub Copilot by default (`executor`/
`agent-session` bind to `copilot-cli`, Claude Sonnet 4.5) — swap the binding
to `claude-code-headless` for direct Anthropic API billing instead.

**Note:** `config/` ships `example-*` placeholder org/repo/username values
pending the real pilot values (requirements §12); replace them before the
first real intake. See `docs/operations.md` §4.

## Extending the pipeline

- **New task type:** add `tasks/<id>/task.yml` (+ its `prompts/` and
  `checklists/` skills) per `schemas/task.schema.json`, add it to a parent
  task's `handoff.allowed` (bump that parent's `handoff.max` if needed),
  merge via PR — zero engine changes. `agent-hq tasks validate` and
  `tests/test_task_library.py` gate it in CI. The P1 tasks (`clinical`,
  `poll`, `qa`, `docs`) are already defined but unwired; each task.yml
  header names its one-line activation edit
  (`docs/task-authoring.md` "Dispositions").
- **New adapter:** implement the port's Protocol from `engine/ports.py`,
  register the class in `engine/registry.py`, select it in
  `config/components.yml`. Prompts/skills and task definitions never change.

## Docs

- [`docs/architecture.md`](docs/architecture.md) — the P0 flow, ports/adapters, credential boundary, retry semantics
- [`docs/task-authoring.md`](docs/task-authoring.md) — writing a task: generic fields, handoffs, control outcomes, artifact namespace, gates, budgets
- [`docs/operations.md`](docs/operations.md) — day-to-day operation of the GitHub Actions surface
- [`docs/local-testing.md`](docs/local-testing.md) — offline, container, and live sandbox validation
- [`docs/project-review.md`](docs/project-review.md) — review findings and the GitHub Agentic Workflows migration recommendation
- [`docs/roadmap.md`](docs/roadmap.md) — deferred work and restore triggers
- [`docs/ports/README.md`](docs/ports/README.md) — the port/adapter contract
- [`constitution.md`](constitution.md) — conventions every task and agent run follows
