# agent_hq

agent_hq is a configuration-driven task engine that runs autonomous
engineering work — tickets flow through spec, plan, implement, review, and
merge-ready PRs — as agents inside GitHub Actions, orchestrated entirely from
YAML task and config files rather than bespoke workflow code. Where a human
decides is an explicit gate a task declares (`gates.post`), and merge is
always one: nothing auto-merges. This repository holds the P0 pilot.

## The route

There is no fixed chain, and no task declares one. A `task.yml` says what a
task *is*; what the ticket does next is the queue a run writes in its own
`.agent-hq/control.json`, which the engine validates and applies
(`docs/task-authoring.md`). Every task in the library is queueable by every
other, bounded only by `budgets.max_queue_length` — so "unwired" means no
prompt currently queues it, not that an edge is missing.

The route the pilot's prompts actually take:

```
GitHub issue (hq:intake label, in config.projects["engine_repo"])
  -> intake      engine entry logic (no task file); enqueues
                 config.projects["initial_task"] (`spec`)
  -> spec        writes specs/<ticket>/spec.md; queues one `implement` per
                 repo with real work    [gate: product-owners, auto_approve:
                                         true -- declared, engine-decided]
  -> implement   code + tests, opens a draft PR; queues `review`
  -> review      writes specs/<ticket>/review.md; queues `implement` again
                 while blockers remain (<=3 rounds), else `qa`
  -> qa          runs the app, screenshots each acceptance criterion onto
                 the PR; writes specs/<ticket>/qa.md; queues `finalize`
  -> finalize    config.projects["final_task"]: writes summary.md and queues
                 nothing, which is what completes the ticket
  -> human merge                                          [always human]
```

An authorized comment on the engine issue interjects at the front of that
queue — `triage` by default (`comment_default_task`), or any task via
`/agent-hq do <task>`; it is also the only thing that clears `BLOCKED`.
`arch-plan`, `arch-approval`, `breakdown`, `clinical`, `poll` and `docs` are
defined and queueable, but no prompt names them yet.

`dispatch.yml` sweeps queued/running work every 15 minutes and triggers
`run.yml`, which executes one task phase (prepare/execute/collect) inside the
project devcontainer. The issue is the control plane, produced work lives on
target-repo branches and selected draft PRs, and orchestration memory lives on
an orphan `agent-hq-state` branch. A static operator dashboard (`dashboard/`,
deployed by `pages.yml`) reports the gate queue, ticket board, run chains,
spend and adapter health. See
[where work and memory live](docs/architecture.md#where-work-and-memory-live)
for the exact lifecycle and storage paths, and
[`docs/task-authoring.md`](docs/task-authoring.md) for the generic task model
(queue declarations, control outcomes, artifact namespace, gates, budgets).

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
  `checklists/` skills) per `schemas/task.schema.json` and merge via PR —
  zero engine changes, and no activation edit anywhere, since the new task is
  queueable the moment it loads and lists itself in the queueable-task menu
  every prompt receives. To put it on the route, have some prompt queue it.
  `agent-hq tasks validate` and `tests/test_task_library.py` gate it in CI.
- **New adapter:** implement the port's Protocol from `engine/ports.py`,
  register the class in `engine/registry.py`, select it in
  `config/components.yml`. Prompts/skills and task definitions never change.

## Docs

- [`docs/architecture.md`](docs/architecture.md) — the P0 flow, ports/adapters, credential boundary, retry semantics
- [`docs/task-authoring.md`](docs/task-authoring.md) — writing a task: generic fields, queue declarations, control outcomes, artifact namespace, gates, budgets
- [`docs/operations.md`](docs/operations.md) — day-to-day operation of the GitHub Actions surface
- [`docs/local-testing.md`](docs/local-testing.md) — offline, container, and live sandbox validation
- [`docs/project-review.md`](docs/project-review.md) — review findings and the GitHub Agentic Workflows migration recommendation
- [`docs/roadmap.md`](docs/roadmap.md) — deferred work and restore triggers
- [`docs/ports/README.md`](docs/ports/README.md) — the port/adapter contract
- [`constitution.md`](constitution.md) — conventions every task and agent run follows
