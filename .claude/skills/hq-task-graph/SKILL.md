---
name: hq-task-graph
description: Render the agent_hq task graph from tasks/ and config/ — what triggers each task, what handoffs it emits, its gates, and wired/unwired status. Use for "task graph", "what triggers X", "what handoffs does X emit", "show the route", "which tasks are wired". Read-only analysis; to add or change a task use hq-add-task, to change config use hq-config.
argument-hint: "[task-id]"
---
# hq-task-graph

Derive and render the live task graph — triggers, handoffs, gates, wiredness — entirely from the files on disk.

## Steps

1. Read the sources. Every `tasks/*/task.yml` (one directory per task), plus:
   - `config/projects.yml` — `initial_task` (the intake root) and `repos`
   - `config/repos.yml` — count its top-level keys (the configured repo count)
   - `config/approvers.yml` — `groups.<name>.members` for each gate's approver group
   - `config/components.yml` — `gate.adapter` and `gate.named` for gate resolution
2. Build per-task facts from the YAML — never from memory of the pilot route:
   - **triggered-by**: every task whose `handoff.allowed` names this task (in-edges); the task named by `projects.initial_task` is additionally triggered by "intake (initial_task)". Note: `intake` is engine entry logic (`engine/runner.py:intake_ticket`), not a task — there is no `tasks/intake/`.
   - **emits**: its own `handoff.allowed` list plus `handoff.max` (fan-out cap). Absent `handoff` = terminal.
   - **gate**: each `gates.post` entry as `approvers` group (list its members from `approvers.yml`) -> logical `adapter` name -> concrete adapter, resolved the way `engine/config.py:resolve_binding` does for the static graph: a non-`default` name looks up `components.yml` `gate.named[<name>]`; `default` (or a name absent from `named`) falls back to `gate.adapter`. Include `timeout_working_hours`. (Only if `components.yml` `label_overrides` contains `hq:gate=` — today it lists only `hq:executor=` — note that a `hq:gate=` ticket label can override at runtime; don't resolve it. Absent from the allowlist, the label is inert — say nothing.)
   - **outputs**: declared `outputs.artifacts`.
   - **opens_pr**, **budget** (`max_cost_usd` / `max_runtime_min` / `retries`).
   - **wired/unwired**: wired = reachable from `initial_task` by following `handoff.allowed` edges transitively. Everything else is unwired (staged), matching the dispositions table in `docs/task-authoring.md`.
3. Output:
   - A mermaid flowchart: `intake` as the entry node -> `initial_task`, one edge per `handoff.allowed` entry. Annotate edges where `max > 1` (e.g. `breakdown -->|max 2| implement`), mark gated tasks (e.g. a `gate: product-owners` suffix in the node label), and style unwired nodes dashed or in their own subgraph.
   - A compact per-task table: task, triggered-by, emits (with max), gate (group -> concrete adapter), artifacts, opens_pr, budget, wired?.
   - With a `[task-id]` argument: skip the full graph and print only that task's card with every fact above in full, including gate members and both in- and out-edges.
4. Flag anomalies (each is a finding line, not an error):
   - An unreachable task whose `task.yml` has no header comment naming its activation edit (the staged tasks — `clinical`, `poll`, `qa`, `docs` — all carry one; a new unwired task without one is unaccounted for).
   - A task with no `handoff.allowed` that does not declare `specs/{ticket}/summary.md` in `outputs.artifacts` — a route dead-end: queue-empty completion only closes the ticket off a terminal run whose artifacts include that path (`docs/task-authoring.md` "Terminal-summary convention").
   - A `handoff.max` exceeding the configured repo count from `config/repos.yml`.
   - A `handoff.allowed` target that is itself unwired (informational — the edge only goes live with its target).
   - A `gates.post` `adapter` name that is neither `default` nor a key of `components.yml` `gate.named` and so falls through to the port default — flag it so a typo'd logical name is visible.
   - A `handoff.allowed` target with no `tasks/<id>/task.yml` directory (broken edge).
5. If asked why the graph looks wrong or how to fix it: diagnosis belongs to `hq-doctor`, edits to `hq-add-task` (tasks) or `hq-config` (config). Run `.venv/bin/agent-hq tasks validate` first if the YAML itself is suspect.

## Hard rules

- Read-only: this skill edits nothing — no file writes, no CLI mutations.
- Derive wiredness and edges from the files every time; never assert the pilot route from memory.
- Resolve gates exactly as `resolve_binding` does; don't invent adapter names.
- `intake` is not a task — never render it as one, only as the entry arrow into `initial_task`.

## References

- `docs/task-definition.md` — field reference (`handoff`, `gates.post`, `outputs.artifacts`, `budget`)
- `docs/building-tasks.md` — "Design the graph before the tasks", terminal-route guidance
- `docs/task-authoring.md` — "Dispositions" table (wired vs. staged), "Terminal-summary convention"
