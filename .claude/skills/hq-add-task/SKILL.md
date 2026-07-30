---
name: hq-add-task
description: Scaffold a new agent_hq task definition under tasks/<id>/ — pick the right template, edit task.yml, write the prompt, make some run queue it, validate. Use when the user says "add a task", "new task", "create a task for X", "define a task", or "wire in the clinical task" (or any staged task like poll/qa/docs).
argument-hint: "[task-id]"
---
# hq-add-task

Scaffold a new task definition in `tasks/<id>/` so it validates, wires into the route graph, and terminates or hands off correctly.

## Steps

1. **Answer the three placement questions** (ask the user if not already known):
   - What artifact does the task produce? (Its `outputs.artifacts` entry, `specs/{ticket}/...` path.)
   - Which run should queue it, and what should it queue next? These are PROMPT decisions, not task.yml ones — a task declares no route (`handoff.allowed`/`max` no longer exist; any task may queue any task).
   - Is it gated, and by which approver group? (Decides `gates.post`.)

2. **Copy the closest template** per `docs/building-tasks.md` "Start from a copy":
   - `tasks/spec/` — produce a reviewed document (gated, checklist)
   - `tasks/implement/` — change code (`opens_pr: true`, no ledger artifacts)
   - `tasks/review/` — read and judge (restricted `tools`, writes findings)
   - `tasks/finalize/` — terminal summary (minimal: no prompts at all)

   `cp -r tasks/<template> tasks/<id>` — then edit down, don't build up.

3. **Edit `task.yml`**: set `id` to the directory name (convention — only uniqueness is enforced), `version: 1`, `description`, `outputs.artifacts`, `budget`. Do NOT add a `handoff` block — the field is gone from the schema and a leftover one is a hard load error. If gated, keep/add `gates.post` with the approver group and a **logical** adapter name (`default`, or a named variant like `spec-approval` from `components.yml`'s `gate.named` map — never a concrete adapter like `github-issue-comment`). Set `timeout_working_hours` deliberately: an expired gate blocks the ticket.

4. **Write the prompt** under `prompts/<id>.md` and reference it in `skills:`. Say only: which artifact to produce, what goes in it, what quality bar applies (add a `checklists/` file only if the bar is checkable). NEVER restate the control-output contract (`.agent-hq/control.json` shapes, the queueable task list, `max_queue_length`) or repo scoping — both are injected automatically by `engine.runner._assemble_prompt`, and a stale restatement is worse than silence.

5. **Wire the in-edge** — exactly one of:
   - Edit the prompt of whichever task should queue it, so some run actually declares it. That is the only wiring there is.
   - Root task: set `config/projects.yml` `initial_task` to it.
   - Deliberately staged: add a header comment in its own `task.yml` saying so. "Unwired" now means only that no prompt queues it — there is no activation edit to name. Staged tasks are valid library members.

6. **Validate**:
   ```
   .venv/bin/agent-hq tasks validate && .venv/bin/pytest -q tests/test_task_library.py
   ```
   The test pins the exact task set, so ANY new task requires adding its id to `EXPECTED_TASK_IDS` in `tests/test_task_library.py`. There is no expected graph to update any more. "No task-name special case" applies to engine behavior, not to that pinned set.

7. Before trusting the route live, dry-run it on a sandbox ticket (`docs/local-testing.md` §3). For visualizing the resulting graph, use `hq-task-graph`; for config-side edits (`projects.yml`, `components.yml`), see `hq-config`.

## Hard rules

- No concrete adapter names anywhere in `task.yml` — test-enforced (`test_no_concrete_adapter_name_leaks_into_task_defs`).
- A route-terminal task must declare `specs/{ticket}/summary.md` in `outputs.artifacts` and emit `complete` — otherwise the ticket never closes (queue-empty completion checks that exact artifact).
- Fan-out is a prompt decision now, capped globally by `budgets.max_queue_length`. A prompt that fans out per repo should say "one entry per affected repo", not a hardcoded count.
- Schemas are `additionalProperties: false` everywhere — no invented keys in `task.yml` or control output.
- `budget.retries` and `max_runtime_min` are the binding knobs; `max_cost_usd` does not bind under the default `copilot-cli` executor (cost unmetered, `docs/architecture.md` deviation 9). Size runtime to the real work (implement 90, documents 30, finalize 15).
- No engine behavior is keyed to a task name — don't expect or add any.

## References

- `docs/building-tasks.md` — design judgment: graph-first, prompts, gates, budgets, anti-patterns
- `docs/task-definition.md` — field reference for `task.yml`
- `docs/task-authoring.md` — control outcomes, artifact namespace, validation mechanics
- `docs/local-testing.md` — sandbox dry-run
