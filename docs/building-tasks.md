# Recommended ways to build tasks

How to design a new task or task route on top of a running deployment. This
is the judgment layer: [task-definition.md](task-definition.md) is the field
reference, [task-authoring.md](task-authoring.md) is the mechanics deep-dive
(validation rules, artifact namespace, control outcomes). Where those cover
something, this doc points instead of restating.

## Start from a copy

Copy the closest existing task directory and edit it down. The library is
small enough that one of the wired tasks is always near what you want:
`spec` for "produce a reviewed document", `implement` for "change code",
`review` for "read and judge", `finalize` for "terminal summary".

The minimal viable task is tiny. `tasks/finalize/task.yml` is the smallest
in the library:

```yaml
id: finalize
version: 1
description: Summarize the ticket outcome.
trigger: enqueued_by
outputs:
  artifacts:
    - specs/{ticket}/summary.md
budget:
  max_cost_usd: 2
  max_runtime_min: 15
  retries: 1
```

Five required fields (`id`, `version`, `description`, `trigger`, `budget`)
plus one declared output. It has no `prompts/` at all — the description,
the injected control contract, and the declared output path carry it. Most
tasks should add one `skills:` prompt file; almost nothing needs more than
that plus a checklist (see "Prompts are the behavior" below).

## Design the graph before the tasks

A route is what runs actually queue; nothing else
wires tasks together. Sketch the edges first, then write the nodes.

- Default to a linear route: one entry per declaration. A linear route is the
  easiest thing to reason about, gate, and debug, and a task declares no
  successors, so the only place a route exists is a prompt.
- Fan out only where one run genuinely yields per-repo work. `spec` is the
  model: its prompt queues one `implement` entry per repo that has real work,
  each carrying that repo as the entry's `repo` field. The bound is the
  global `budgets.max_queue_length`, not a per-task cap.
- Do not design for parallelism inside a ticket — it doesn't exist. The
  engine holds one run per ticket in an exclusive state
  (`RUNNING`/`WAITING_GATE`, `engine.engine.EXCLUSIVE_STATES`); queued
  siblings wait their turn. A fan-out's children execute sequentially, so
  fan-out buys per-repo scoping, not speed.

## Prompts and checklists are the behavior

`task.yml` says what a task is allowed to do; `prompts/*.md` says what it
actually does. Keep the yaml thin and put all the judgment in the prompt.

Two things are injected into every prompt automatically by
`engine.runner._assemble_prompt`: the control-output contract (the
`.agent-hq/control.json` outcome shapes, the queueable-task menu with each
task's `description`, `max_queue_length`, and this task's own required output
paths) and the run's repo scoping. Never restate either in a prompt — a stale
restatement that drifts from the real contract is worse than silence, and is
exactly how five prompts ended up teaching `outcome: "handoff"` after the
schema stopped accepting it.

What a prompt should say: which artifact to produce, what goes in it, and
what quality bar applies. `tasks/spec/prompts/spec.md` plus
`tasks/spec/checklists/spec-quality.md` are the model — the prompt names
the file, its required sections, and the boundaries ("do not implement
code"); the checklist is a short list of verifiable conditions the agent
runs before finishing. Checklists earn their keep when the quality bar is
checkable ("every acceptance criterion is testable"); skip them otherwise.

## Artifacts

- Declare every file the task produces in `outputs.artifacts`, using
  `specs/{ticket}/` paths (`{ticket}` is substituted). Declared outputs are
  ledger artifacts, not work-repo commits — see
  [task-authoring.md](task-authoring.md) "Artifact namespace".
- In a queue entry, pass exactly what that run needs in `artifacts[]` — its
  `input_artifacts` are its only input source. The provenance rule
  (`engine.handoff.validate_queue`): a run may forward only artifacts it
  inherited as inputs or declared as its own outputs, never an arbitrary
  worktree file.
- Never write outside the worktree. Every proposed artifact path is
  containment-checked (`engine.handoff._check_containment`) — absolute
  paths, `..` segments, and symlink escapes reject the whole declaration.
- Anything a task leaves under `specs/{ticket}/` that it did **not** declare
  lands in the work repo as product code: only declared outputs and inherited
  inputs are excluded from the patch (`engine/runner.py:_execute`). A task
  that produces no code at all should say `writes_code: false` rather than
  rely on a prompt asking politely.

## Gates

Gate the tasks whose downstream work is expensive or irreversible: a spec
before implementation burns agent runs on it, an approval before anything
merge-ready. On the pilot's route only `spec` declares a gate, and it carries
`auto_approve: true` — the request comment is still posted with the spec
inlined, as a record rather than a request, so staffing the gate later is
deleting one line. `implement` and `review` run ungated because their output
is still reviewable later, and merge is human regardless.

Prefer a named gate variant per audience over a new adapter. `spec` binds
`adapter: spec-approval`; `components.yml` resolves it via the `gate.named`
map, while `default` falls through to the plain `gate.adapter` — both land
on the same `github-issue-comment` adapter.
A new audience is one line in the `named` map, not new code. Decisions are
authorized comments on the engine issue —
`/agent-hq approve|request-changes|reject <run-id> [reason]`
(`engine/adapters/github_issue_comment_gate.py`) — noticed by the `*/15`
dispatch cron, so allow up to ~15 minutes of decision latency.

Set `timeout_working_hours` deliberately. A gate past its timeout resolves
`EXPIRED` at the next sweep, which blocks the ticket and escalates — an
overly tight timeout turns a slow reviewer into a blocked ticket.

## End every route on `final_task`

Queue-empty completion (`engine.engine._complete_if_queue_empty`) finishes a
ticket only when the terminal run's task is the one named by
`config/projects.yml` `final_task` (`finalize` in the pilot). That task must:

- declare `specs/{ticket}/summary.md` in `outputs.artifacts` — there has to be
  something to post, and a required declared output means a run that skips it
  fails rather than completing silently,
- queue nothing, so the queue is actually empty when it finishes.

A queue that drains on any **other** task did not finish the route, it stopped
early: the ticket goes `BLOCKED` with that reason and escalates. Naming the
endpoint in config rather than checking for a filename is what makes those two
outcomes distinguishable — before, a run that stopped halfway and a run that
finished looked identical to the engine unless one happened to write a file
called `summary.md`.

To move the endpoint, repoint `final_task` (via `hq-config`) — the engine still
special-cases no task name.

A task that *gives up* should emit `{"outcome": "blocked", "reason": "..."}`
instead; `review` does this at its round cap. Queueing nothing would look like
the route ending in the wrong place.

## Staged tasks are normal

It is fine — expected, even — to define a task nothing queues yet.
`arch-plan`, `arch-approval`, `breakdown`, `clinical`, `poll` and `docs` are
all valid library members that stay unqueued until some prompt names them —
there is no activation edit, since every library task is already queueable by
every other. `agent-hq tasks validate` checks
each task in isolation and never asks whether anything queues it. Record that
it is staged as a header comment in the task's own `task.yml`, the way
`clinical` does, so using it
later is a documented one-liner rather than archaeology.

## Budgets and retries

Under the default `copilot-cli` executor cost **is** metered: Copilot bills
tokens as AI credits and prints the session's total on stderr, which
`copilot_cli._parse_usage` records as the run's billed `cost_usd` (1 credit =
$0.01), so `max_cost_usd` and `ticket_cap_usd` bind normally — see
[architecture.md](architecture.md) deviation 9. The one gap: a run whose
trailer never appears (a kill, or a CLI format change) records
`cost_usd: 0.0`, deliberately understating rather than blocking the ticket on
every transient failure. So size the USD caps, and do not rely on them alone.
The other knobs:

- `budget.retries` — how many times a failed or schema-invalid run
  re-attempts. This is the per-task knob that matters; size it to how
  flaky the task's work is (2 for agent-judgment tasks, 1 for `finalize`).
- `budget.max_runtime_min` — size to the task's real work, not a default:
  `implement` gets 90, document-producing tasks get 30, `finalize` 15. Too
  small kills healthy runs; too large delays lost-run detection.
- `loop_guard.max_runs` in `config/budgets.yml` is the only structural
  ceiling (there is no depth guard), checked both before a queue applies and
  at dispatch; `CANCELLED` runs are excluded.
  `in_flight_cap` is a global concurrent-ticket cap, checked at
  dispatch/claim only. Leave them alone when adding a task unless
  your route legitimately exceeds them (a long chain plus retries can
  approach `max_runs`).

## Testing a new task

1. `agent-hq tasks validate` — schema, on-disk skill files, every
   declared `components` ports exist in
   `components.yml`.
2. If the task introduces a new shape (a new fan-out, a new gate binding),
   extend `tests/test_task_library.py` — its checks are generic (no task
   declares a route, gate bindings construct, no concrete adapter names, no
   prompt teaches retired control vocabulary), so add the new shape to those,
   never a task-name special case.
3. Dry-run the route on a sandbox ticket before trusting it — see
   [local-testing.md](local-testing.md) §3 for the live sandbox setup.

## Anti-patterns

- Concrete adapter names in `task.yml` — rejected by
  `tests/test_task_library.py`
  (`test_no_concrete_adapter_name_leaks_into_task_defs`).
- Expecting engine behavior keyed to a task name — there is none; even
  `intake` and `finalize` are not special-cased
  (`test_no_intake_task_directory` pins it).
- Queueing a task id that is not in the loaded library — the entire declaration
  set is rejected (`engine.handoff.validate_queue`).
- Absolute or `..` artifact paths — containment check rejects the set
  (`engine.handoff._check_containment`).
- Forwarding an artifact outside your provenance set (not inherited, not
  your own declared output) — rejected by `validate_queue`.
- Emitting `"outcome": "queue"` with no `queue` key at all —
  schema-invalid. An empty **array** (`"queue": []`) is the way to say
  "nothing further"; there is no `"complete"` outcome.
- Declaring an empty queue from a task that is not `projects.final_task` —
  the engine reads that as a route that stopped early and BLOCKs the ticket
  (`engine/engine.py:_complete_if_queue_empty`). A task that means "I gave
  up" says `"outcome": "blocked"` with a reason.
- Leaving an undeclared file under `specs/{ticket}/` — only declared outputs
  and inherited inputs are excluded from the work patch
  (`engine/runner.py:_execute`), so anything else there lands in the work
  repo as product code. Scratch goes in `.agent-hq/`.
