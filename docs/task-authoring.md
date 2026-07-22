# Authoring a task

A task is one directory under `tasks/<id>/` with a `task.yml` validated
against `schemas/task.schema.json`, plus whatever `prompts/`/`checklists/`
skill files it references. There is no fixed chain and no task-name special
case in the engine (`intake` and `finalize` used to be special-cased; neither
is anymore -- see "Dispositions" below). A task joins the live graph the
moment some other task's `handoff.allowed` names it and an accepted run
proposes a handoff to it; nothing else "wires it in".

## Generic fields

Required: `id`, `version`, `description`, `trigger` (currently always
`enqueued_by` -- who/what enqueues a run is the handoff or intake that named
it, not a field on the task itself), `budget`.

Optional, all schema-validated (`additionalProperties: false` throughout, so
a typo'd key fails `agent-hq tasks validate` rather than being silently
ignored):

- `inputs.artifacts` / `inputs.ticket_fields` -- declares that a run must not
  start before its parent run has recorded these artifacts (`TE-3`, checked
  by `engine.engine._inputs_ready` at dispatch time). This is a *readiness*
  gate, separate from where the files actually come from at execute time (see
  "Artifact namespace" below).
- `context` -- symbolic references injected into the prompt: `constitution`
  (inlines `constitution.md`), `specs/{ticket}/*` (told to read from the
  worktree, `{ticket}` substituted), or a task-local `prompts/*`/`checklists/*`
  file (inlined verbatim).
- `skills` -- task-local `prompts/`/`checklists/` files, inlined into the
  prompt; must exist on disk (`engine.taskdefs.load_task` checks this).
- `components` -- port name -> **logical** binding name. Validated but
  currently inert: `engine.config.resolve_binding` honors a task-supplied
  binding name only for the `gate` port, and the gate binding is actually
  selected via `gates.post[].adapter`, never via `components` (see
  `docs/task-definition.md`). A task
  declaring a `components` entry for a port `components.yml` doesn't
  configure is a load-time error (`engine.config.validate_task_bindings`,
  wired into `agent-hq tasks validate`). A task declaring **no**
  `components` at all (e.g. `qa`) stays registered but unwired -- see
  "Dispositions".
- `model` -- currently unused by any adapter; reserved.
- `gates.post` -- see "Gates" below.
- `outputs.artifacts` -- declared output paths (`{ticket}` substituted); see
  "Artifact namespace".
- `opens_pr` -- open (or reuse) a draft PR on the task's work branch on
  success, independent of any gate (`implement` sets this).
- `handoff.allowed` / `handoff.max` -- see "Handoffs" below.
- `tools` -- allowed tool names passed to the agent adapter.
- `budget.max_cost_usd` / `max_runtime_min` / `retries` -- per-run caps; see
  "Budgets".

Every field that names a repository, a task, or a port is a **configured
value** (from `config/*.yml`) or a **task id from the loaded library** --
never a concrete adapter name. `tests/test_task_library.py`
(`test_no_concrete_adapter_name_leaks_into_task_defs`) enforces that no
`task.yml` ever contains a string like `github-issues` or `copilot-cli`.

## Ports a task uses

Three ports are bound automatically for every run at prepare time
(`engine.engine.BINDABLE_PORTS`): `tracker`, `agent-session`, `messaging`.
A task never names a concrete adapter for these -- `components.yml` does. A
`gates.post` entry additionally binds the `gate` port (see below). `qa-env`
and `poll` are declared as `engine.ports` Protocols with no P0 adapter; a
task that doesn't touch them (every current task) never resolves them, so
they can stay unbound in `components.yml` without breaking validation.

## Handoffs

A task proposes its children by writing `.agent-hq/control.json` with
outcome `"handoff"` (see "Control outcomes" below); the task definition only
constrains what's *allowed*:

- `handoff.allowed` -- the list of task ids this task may hand off to. A
  proposed handoff naming any other target is rejected
  (`engine.handoff.validate_handoffs`).
- `handoff.max` -- the most handoffs one run may propose in a single
  `control.json`. Most tasks are `max: 1` (a linear next step); `breakdown`
  is `max: 2` -- the pilot's fan-out point, emitting one `implement` handoff
  per affected configured repo (`config/repos.yml`), each carrying that
  repo in the handoff's `repo` field.

Validation is pure and total-rejection: `engine.handoff.validate_handoffs`
checks the whole proposed set against `schemas/control.schema.json`, then
path containment on every artifact, then per-handoff semantics (target in
`handoff.allowed` and in the loaded library, `repo` if given is a configured
repo, key uniqueness, total count `<= handoff.max`, and each artifact is in
the run's **provenance set** -- its inherited `input_artifacts` union its own
substituted `outputs.artifacts`, never an arbitrary worktree file). Any
single violation rejects the *entire* set, not just the offending item.

State-dependent guards that the pure validator can't see (each artifact's
ledger entry actually exists, and the ticket's loop/budget/depth limits
still hold) are enforced atomically in `engine.engine.apply_handoffs`, inside
the same state-store transaction that marks the source run terminal --
so a crash between "run succeeded" and "children queued" can't happen.
Handoff-spawned run identity is `(source_run_id, handoff_key, attempt)` only
-- the target task id is **not** part of it, so a re-delivered handoff key
always resolves to the same run id regardless of payload content (the first
accepted delivery wins; a duplicate is a no-op).

## Control outcomes

Every completed run writes exactly one `.agent-hq/control.json`
(`schemas/control.schema.json`, `additionalProperties: false` --
schema-invalid means the run *fails* per its own retry budget, never
"ignored"):

- `{"outcome": "handoff", "handoffs": [...]}` -- `handoffs` required,
  non-empty. With no `gates.post` on this task, accepted handoffs enqueue as
  `QUEUED` runs immediately and this run finishes `SUCCEEDED`. With a
  `gates.post` entry, the proposals are stored as `run.pending_handoffs` and
  the run stops at `WAITING_GATE`; a gate `APPROVED` decision applies them
  and completes the run.
- `{"outcome": "complete"}` -- `handoffs` forbidden; the run finishes
  `SUCCEEDED` with no children. This is what feeds queue-empty completion
  (see "Terminal-summary convention" below) -- a task with no
  `handoff.allowed` at all (e.g. `finalize`) always emits this.
- `{"outcome": "blocked", "reason": "..."}` -- `handoffs` forbidden, `reason`
  required; the run is recorded blocked and the ticket moves to `BLOCKED`
  with that reason, escalating to a human with no auto-retry.

`engine.runner._assemble_prompt` injects this contract into every prompt
automatically (the required outcome shapes, this task's own
`handoff.allowed`/`max`, and the output path) -- a task never needs to spell
this out itself, and it does not depend on the task including
`constitution.md` in `context`.

## Artifact namespace: ledger vs. work-patch

There is exactly one artifact namespace and one input source:

- **Ledger artifacts** are a run's declared `outputs.artifacts`, persisted
  by collect into `tickets/<id>/artifacts/<run_id>/` (keyed by the
  *producing* run id, via `engine.state.GitJsonStateStore.write_artifact`/
  `read_artifact`/`artifacts_dir`) -- never a work-repo commit. If an
  accepted handoff forwards an artifact the run itself only *inherited*
  (e.g. `arch-plan` -> `breakdown` forwarding `spec.md`), collect also
  snapshots that file into the *source* run's own ledger directory, so a
  transitive handoff still resolves.
- **Input artifacts** on a handoff-spawned run
  (`run.input_artifacts`, copied from the accepted handoff's `artifacts[]`
  at apply time) are the run's **only** input source -- there is no
  separate task-level input list. Prepare restores their content from the
  **source** (parent) run's ledger namespace (`engine.runner
  ._restore_input_artifacts`) into a transported manifest -- execute (its
  own, credential-free Actions job, hardening plan Task 12) then
  materializes them into its worktree (`engine.runner._materialize_inputs`),
  so a child reads exactly what its handoff accepted, never a sibling's
  file.
- The **work patch** excludes both: execute's `materialize_work_patch`
  diffs out every declared output path and every inherited
  `input_artifacts` path before handing the patch to collect, which
  `git apply`s it to a fresh clone and lands it on the target branch
  (`engine.runner._collect_success`). Neither is code; both live only in
  the ledger.

Every artifact path a handoff proposes is **containment-checked** against
the worktree root before it's trusted anywhere (absolute paths, `..`
segments, and symlink escapes are all rejected;
`engine.handoff._check_containment`).

## Gates

`gates.post` is a list (P0 uses one entry) of `{approvers, adapter,
timeout_working_hours}`. `approvers` names a group in `config/approvers.yml`;
`adapter` is a **logical** gate name resolved through `components.yml`'s
`gate.named` map (or the plain `gate.adapter` default) -- never a concrete
adapter id. The pilot's `default`/`spec-approval` logical names both resolve
to the `github-issue-comment` adapter (an authorized-comment approval on the
parent engine issue); `pr-review` remains registered for a task that wants a
work-repo-PR-based approval instead. See `docs/ports/gate.md` for the full
adapter contract. A gate past `timeout_working_hours` with no decision
resolves to `EXPIRED` at the next sweep, blocking the ticket and escalating.

## Budgets

Per-task `budget.max_cost_usd`/`max_runtime_min`/`retries` bound one run.
Ticket-wide caps live in `config/budgets.yml`: `ticket_cap_usd` (total spend
across every run on a ticket), `in_flight_cap` (global concurrent-ticket
cap), and `loop_guard.max_runs`/`max_depth` (runaway-handoff protection --
total run count and causal chain depth). All four are checked before a
handoff set is applied (`engine.engine.apply_handoffs`) and before a queued
run is dispatched, so a task cannot out-run these limits by proposing more
handoffs. Under the default Copilot-billed executor, run cost is not
metered (`cost_usd: 0.0`, `usage_known: true`), so `max_cost_usd`/
`ticket_cap_usd` don't bind in that configuration -- `retries`, the loop
guard, the in-flight cap, and runtime deadlines still do (see
`docs/architecture.md` deviation 9).

## Terminal-summary convention

Queue-empty completion (`engine.engine._complete_if_queue_empty`) fires once
a ticket has no `QUEUED`/`RUNNING`/`WAITING_GATE` run and no
`pending_handoffs` left anywhere, but only actually closes the ticket if the
**terminal run's own recorded artifacts** include the declared summary path
`specs/{ticket}/summary.md` -- a reopened ticket can't complete off a prior
lifecycle's stale summary. `finalize` is exactly this: no `handoff.allowed`,
one declared output (`specs/{ticket}/summary.md`), always emits
`{"outcome": "complete"}`. Any task chain that wants queue-empty completion
to land on a real "done" message should end the same way: declare the
summary artifact, emit `complete`, propose no further handoffs. Without a
matching summary, completion instead pins "awaiting human input" and takes
no terminal action.

## Validation

- `agent-hq tasks validate` loads every `tasks/*/task.yml`
  (`engine.taskdefs.load_all`, schema + on-disk skill/context checks),
  cross-checks the library (`engine.taskdefs.validate_library`: every
  `handoff.allowed` target resolves to a loaded task id), and checks every
  task's declared `components` port against `components.yml`
  (`engine.config.validate_task_bindings`).
- `agent-hq config validate` validates `config/*.yml` against
  `schemas/*.schema.json` (including the `handoff`/`initial_task`/`intake`/
  `base_branch` additions).
- `tests/test_task_library.py` pins the graph-level properties (no
  P0_CHAIN, no concrete adapter names, gate bindings resolve to
  constructible adapters, no `tasks/intake/` directory).

## Dispositions

| Task | Status |
|---|---|
| intake | **Not a task.** Engine entry logic (`engine.runner.intake_ticket`) reads eligibility from `config.projects["intake"]`/`["public"]`/`["public_safe_label"]` and enqueues `config.projects["initial_task"]` (`spec` in the pilot config) with the root run's resolved repo. There is no `tasks/intake/` directory and no task-name special case for it. |
| spec | Converted (wired). `handoff.allowed: [implement]`, gated (`spec-approval`). The fan-out point in the minimal route: `handoff.max: 3`, one `implement` handoff per affected configured repo. |
| arch-plan | Converted, defined, **unwired** -- its header names the activation edit (point `spec`'s `handoff.allowed` back at it). `handoff.allowed: [arch-approval, breakdown]`. |
| arch-approval | Converted, defined, **unwired** (activated with `arch-plan`, its only in-edge). Confirms the plan artifacts, no changes; gated (`default`); `handoff.allowed: [breakdown]`. |
| breakdown | Converted, defined, **unwired** (activated with the `arch-plan` chain). `handoff.max: 2`, one `implement` handoff per affected repo when wired. |
| implement | Converted (wired). `opens_pr: true`; `handoff.allowed: [finalize]`. |
| review | Converted, defined, **unwired** -- its header names the activation edit (point `implement`'s `handoff.allowed` at it). `handoff.allowed: [finalize]`. |
| finalize | Converted (wired). Terminal task: writes `summary.md`, always `complete`, feeds queue-empty completion (see above). No task-name special case; any task ending this way completes the same way. |
| clinical | Converted, defined, **unwired** until an accepted handoff selects it -- its own header names the one-line activation edit (point `spec`'s `handoff.allowed` at it). Gated (`clinical-reviewers`, `default` adapter). |
| poll | Converted, defined, **unwired** -- needs the P1 reaction-based `poll` adapter (`docs/roadmap.md`); no task currently hands off to it. |
| docs | Converted, defined, **unwired** until an accepted handoff selects it (its header names the activation edit: insert it between `qa` and `finalize` once `qa` is wired). |
| qa | Registered, declares **no** `components` port at all (not even an unbound one) and stays unwired until a `qa-env` binding exists in `components.yml` -- its header names the activation edit. See `docs/ports/qa-env.md` for what's deferred with that binding. |

None of the above is a name the engine special-cases; every row describes a
task-graph state (wired vs. defined-but-unwired), not an engine code path.
