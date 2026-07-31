---
name: hq-task-graph
description: Render what the agent_hq task library can do and what tickets actually route through — per-task facts from tasks/ and config/, plus the observed route from the state branch. Use for "task graph", "what triggers X", "show the route", "which tasks are actually used", "what can queue what". Read-only analysis; to add or change a task use hq-add-task, to change config use hq-config.
argument-hint: "[task-id]"
---
# hq-task-graph

**There is no declared route to render.** A `task.yml` says what a task *is*,
never what may follow it: `handoff.allowed`/`max` are gone, and any task in the
library may be queued by any run (bounded by `budgets.max_queue_length`). The
route is the queue a run declares in its own `control.json`, revisable by any
later run.

So this skill reports two things and never conflates them:

- **Capability** — the per-task facts, from the files on disk.
- **The observed route** — what runs have actually queued, from the state
  branch. That is the only honest answer to "what does a ticket do".

## Steps

1. Read the sources. Every `tasks/*/task.yml` (one directory per task), plus:
   - `config/projects.yml` — `initial_task` (the intake root)
   - `config/budgets.yml` — `max_queue_length` (the per-declaration cap)
   - `config/approvers.yml` — `groups.<name>.members` for each gate's group
   - `config/components.yml` — `gate.adapter` and `gate.named` for gate resolution
2. Build per-task facts from the YAML — never from memory of the pilot route:
   - **gate**: each `gates.post` entry as `approvers` group (list its members
     from `approvers.yml`) -> logical `adapter` name -> concrete adapter,
     resolved the way `engine/config.py:resolve_binding` does: a non-`default`
     name looks up `components.yml` `gate.named[<name>]`; `default` (or a name
     absent from `named`) falls back to `gate.adapter`. Include
     `timeout_working_hours` and `auto_approve`.
   - **outputs**: declared `outputs.artifacts`.
   - **inputs**: declared `inputs.artifacts` — this is a real dispatch gate
     (`engine.engine._inputs_ready`), so a task declaring inputs will not start
     until the run ahead of it in the queue has recorded them.
   - **opens_pr**, **writes_code**, **budget**, **tools**.
   - **queued by**: grep `tasks/*/prompts/*.md` for the task id. A task nothing
     mentions is defined but nothing will ever queue it — that, not a missing
     graph edge, is what "unwired" means now.
3. Read the observed route (read-only, no checkout):
   ```
   git -C <engine-repo> fetch origin agent-hq-state
   git show origin/agent-hq-state:tickets/<n>/state.json
   ```
   Order each ticket's `runs` by `queue_seq` (fall back to array index for runs
   written before that field). Report the actual task sequence per ticket, and
   mark `CANCELLED` runs — a cancelled entry is a route that was planned and
   then dropped, which is exactly the interesting part.
4. Output:
   - A **capability table**: task, gate (group -> concrete adapter), inputs,
     outputs, opens_pr, budget, and which prompts mention it.
   - An **observed-route** section: one line per ticket, `queue_seq` order, with
     cancellations shown (e.g. `spec → implement → review → ~~qa~~(cancelled by
     review) → implement`).
   - A mermaid flowchart of the **observed** transitions only — edges aggregated
     across tickets, labelled with how many times each was taken. Never draw an
     edge the library merely permits; every task pair is permitted.
   - With a `[task-id]` argument: that task's card in full (gate members,
     inputs/outputs, budget, prompts that mention it) plus every observed run of
     it and what each queued next.
5. Flag anomalies (each a finding line, not an error):
   - A task no prompt mentions — defined, but nothing will queue it.
   - A `gates.post` `adapter` name that is neither `default` nor a key of
     `components.yml` `gate.named`, so it silently falls through to the port
     default — flag it so a typo'd logical name is visible.
   - A task declaring `inputs.artifacts` that no other task declares as an
     output — it can be queued but will never pass `_inputs_ready`.
   - A ticket whose observed route ends on a run that is not `CANCELLED` and did
     not produce the closing summary — a queue that ran dry early.
   - Repeated cancellation of the same task across tickets — a prompt queueing
     work that later runs consistently decide is wrong.
6. If asked why the route looks wrong or how to fix it: diagnosis belongs to
   `hq-doctor`, ticket state to `hq-ticket`, edits to `hq-add-task` (tasks) or
   `hq-config` (config). Run `.venv/bin/agent-hq tasks validate` first if the
   YAML itself is suspect.

## Hard rules

- Read-only: this skill edits nothing — no file writes, no CLI mutations.
- Never present a permitted transition as a route. Every task may queue every
  task; only the state branch says what actually happened.
- Derive facts from the files and the state branch every time; never assert the
  pilot route from memory.
