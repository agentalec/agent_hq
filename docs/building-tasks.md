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

A route is a graph whose edges are `handoff.allowed` entries; nothing else
wires tasks together. Sketch the edges first, then write the nodes.

- Default to a linear chain with `max: 1`. Every wired task except
  `breakdown` is `max: 1`, and a linear chain is the easiest route to
  reason about, gate, and debug.
- Fan out only where one run genuinely yields per-repo work. `breakdown` is
  the model: `handoff.max: 2` because `config/repos.yml` configures two
  repos, and each `implement` handoff carries its `repo` field. Set `max`
  to the number of configured repos, not a round number.
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
`.agent-hq/control.json` outcome shapes, this task's own
`handoff.allowed`/`max`, and the output path) and the run's repo scoping.
Never restate either in a prompt — a stale restatement that drifts from the
real contract is worse than silence.

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
- In a handoff, pass exactly what the child needs in `artifacts[]` — the
  child's `input_artifacts` are its only input source. The provenance rule
  (`engine.handoff.validate_queue`): a run may forward only artifacts it
  inherited as inputs or declared as its own outputs, never an arbitrary
  worktree file.
- Never write outside the worktree. Every proposed artifact path is
  containment-checked (`engine.handoff._check_containment`) — absolute
  paths, `..` segments, and symlink escapes reject the whole handoff set.

## Gates

Gate the tasks whose downstream work is expensive or irreversible: a spec
before implementation burns agent runs on it, an approval before anything
merge-ready. The pilot gates `spec` and `arch-approval`; `implement` and
`review` run ungated because their output is still reviewable later.

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

## End every route the finalize way

Queue-empty completion (`engine.engine._complete_if_queue_empty`) closes
the issue only when the terminal run's own recorded artifacts include
`specs/{ticket}/summary.md`. So every route must end with a task that:

- declares `specs/{ticket}/summary.md` in `outputs.artifacts`,
- emits `{"outcome": "queue", "queue": []}` — i.e. queues nothing on the
  terminal run.

Leaving `handoff.allowed` off the terminal task entirely is the recommended
convention, but the engine never checks it — a task that declares handoffs
yet emits `complete` closes the ticket identically.

That is the `finalize` pattern, and it's a convention, not a special case —
any task shaped this way terminates a route the same way. A route that ends
without it leaves the ticket pinned "awaiting human input" instead of
closed.

## Staged tasks are normal

It is fine — expected, even — to define a task nobody hands off to yet.
`clinical`, `poll`, `docs`, and `qa` are all valid library members that
stay unwired until some task's `handoff.allowed` names them; `agent-hq
tasks validate` only requires that handoff *targets* resolve, not that
every task is targeted. Record the activation edit as a header comment in
the task's own `task.yml`, the way `clinical` does ("activate by pointing
`tasks/spec/task.yml` `handoff.allowed` at clinical"), so wiring it in
later is a documented one-liner rather than archaeology.

## Budgets and retries

Under the default `copilot-cli` executor, per-run cost is not metered
(runs record `cost_usd: 0.0`), so `max_cost_usd` and `ticket_cap_usd` do
not bind — see [architecture.md](architecture.md) deviation 9. The knobs
that actually constrain a task:

- `budget.retries` — how many times a failed or schema-invalid run
  re-attempts. This is the per-task knob that matters; size it to how
  flaky the task's work is (2 for agent-judgment tasks, 1 for `finalize`).
- `budget.max_runtime_min` — size to the task's real work, not a default:
  `implement` gets 90, document-producing tasks get 30, `finalize` 15. Too
  small kills healthy runs; too large delays lost-run detection.
- `loop_guard.max_runs` in `config/budgets.yml` is the
  ticket-level backstop, checked both before handoffs apply and at
  dispatch; `in_flight_cap` is a global concurrent-ticket cap, checked at
  dispatch/claim only. Leave them alone when adding a task unless
  your route legitimately exceeds them (a long chain plus retries can
  approach `max_runs`).

## Testing a new task

1. `agent-hq tasks validate` — schema, on-disk skill files, every
   `handoff.allowed` target resolves, declared `components` ports exist in
   `components.yml`.
2. If the task introduces a new graph shape (a new fan-out, a new gate
   binding), extend `tests/test_task_library.py` — its checks are generic
   (handoff targets resolve, gate bindings construct, no concrete adapter
   names), so add the new shape to those, never a task-name special case.
3. Dry-run the route on a sandbox ticket before trusting it — see
   [local-testing.md](local-testing.md) §3 for the live sandbox setup.

## Anti-patterns

- Concrete adapter names in `task.yml` — rejected by
  `tests/test_task_library.py`
  (`test_no_concrete_adapter_name_leaks_into_task_defs`).
- Expecting engine behavior keyed to a task name — there is none; even
  `intake` and `finalize` are not special-cased
  (`test_no_intake_task_directory` pins it).
- Handing off to a task not in your `handoff.allowed` — the entire handoff
  set is rejected (`engine.handoff.validate_queue`).
- Absolute or `..` artifact paths — containment check rejects the set
  (`engine.handoff._check_containment`).
- Forwarding an artifact outside your provenance set (not inherited, not
  your own declared output) — rejected by `validate_queue`.
- Emitting `"outcome": "queue"` with no `queue` key at all —
  schema-invalid (`control.schema.json` requires `minItems: 1`); an empty
  set of next steps is `"complete"`.
- Relying on `max_cost_usd`/`ticket_cap_usd` for safety under the Copilot
  binding — cost is unmetered there; use `retries`, runtime, and the loop
  guard ([architecture.md](architecture.md) deviation 9).
