# Task definition reference

The normative, field-by-field answer to "what can a `task.yml` say and what
does each field do". For the narrative version — why the graph works this
way, the artifact namespace, gate semantics in depth — see
[task-authoring.md](task-authoring.md); this page links there per topic
rather than restating it. For wiring a new work repository see
[setup-new-repo.md](setup-new-repo.md); for designing a task chain see
[building-tasks.md](building-tasks.md).

## Anatomy of a task

A task is one directory under `tasks/<id>/`:

```
tasks/spec/
  task.yml            # the definition (required)
  prompts/spec.md     # referenced by skills/context (optional)
  checklists/...      # referenced by skills/context (optional)
```

`task.yml` is validated against `schemas/task.schema.json`, which sets
`additionalProperties: false` at every level — a typo'd key is a validation
error, never silently ignored. The loader (`engine/taskdefs.py`) also
verifies that every `skills` entry and every task-local `context` entry
(`prompts/*`, `checklists/*`) exists on disk, and rejects duplicate task ids
across directories.

Nothing wires a task into the live graph except another task's
`handoff.allowed` naming it (or `config/projects.yml`'s `initial_task`
naming it as the ticket's root task). There is no fixed chain and no
task-name special case in the engine — a defined task that no
`handoff.allowed` reaches is registered but unwired (see the dispositions
table in [task-authoring.md](task-authoring.md)).

## Annotated example

`tasks/spec/task.yml`, verbatim, with commentary:

```yaml
id: spec                      # identity; what handoff.allowed targets name
version: 1                    # recorded on every run as task_version
description: Author the specification for the ticket.
trigger: enqueued_by          # required; currently always this value
context:
  - constitution              # inlines constitution.md into the prompt
  - specs/{ticket}/*          # "read this from the worktree" instruction
skills:
  - prompts/spec.md           # task-local files, inlined into the prompt
  - checklists/spec-quality.md
outputs:
  artifacts:
    - specs/{ticket}/spec.md  # required output; ledger artifact, not code
gates:
  post:
    - approvers: product-owners   # group in config/approvers.yml
      adapter: spec-approval      # LOGICAL name, resolved via components.yml
      timeout_working_hours: 48
handoff:
  allowed:
    - implement               # the only task a spec run may hand off to
  max: 3                      # fan-out cap: handoffs per run (one per repo)
budget:
  max_cost_usd: 5
  max_runtime_min: 30
  retries: 2
```

## Field reference

Required top-level fields: `id`, `version`, `description`, `trigger`,
`budget`. Everything else is optional.

### `id` (string, required)

The task's identity: the key it is loaded under, and the string other
tasks' `handoff.allowed` (and `config/projects.yml`'s `initial_task`) use
to name it. By convention it matches the directory name; what is enforced
is uniqueness — two directories declaring the same `id` fail
`agent-hq tasks validate` (`engine/taskdefs.py:load_all`).

### `version` (integer >= 1, required)

Recorded on every run as `task_version` (`engine/engine.py` — `enqueue`,
`apply_handoffs`, `reenqueue_same`), so state history shows which revision
of the task a run executed. Bump it when the task's behavior changes.

### `description` (string, required)

Injected verbatim as the prompt header for every run of the task
(`engine/runner.py:_assemble_prompt`). Write it as the one-line mission
statement the agent reads first.

### `trigger` (string, required)

Currently always `enqueued_by`. No engine code path reads this field — who
or what enqueues a run is decided by the handoff (or intake) that named the
task, not by the task itself. Required by the schema; declarative.

### `inputs` (object, optional)

- `inputs.artifacts` (list of strings) — a **readiness gate**, not an input
  source: the dispatcher will not trigger this run until its parent run has
  recorded (a superset of) these artifact paths, `{ticket}` substituted
  (`engine/engine.py:_inputs_ready`, checked at dispatch time). What files
  a run actually receives is decided by the accepted handoff's
  `artifacts[]`, restored from the parent run's ledger namespace — see
  "Artifact namespace" in [task-authoring.md](task-authoring.md).
- `inputs.ticket_fields` (list of strings) — accepted by the schema but not
  currently read by any engine code path; reserved.

### `context` (list of strings, optional)

Symbolic references rendered into the prompt's Context section
(`engine/runner.py:_assemble_prompt`). Three forms:

- `constitution` — inlines the engine repo's `constitution.md` into the
  prompt.
- A worktree pattern such as `specs/{ticket}/*` — rendered as a "Read
  `<ref>` from the worktree" instruction, `{ticket}` substituted with the
  issue number.
- A task-local `prompts/*` or `checklists/*` path — same "read from the
  worktree" rendering, but its existence in the task directory is verified
  at load time (`engine/taskdefs.py:TASK_LOCAL_CONTEXT_PREFIXES`). To
  inline a task-local file's content, list it under `skills` instead.

### `skills` (list of strings, optional)

Task-local `prompts/` / `checklists/` files, inlined verbatim into the
prompt with `{ticket}` substituted (`engine/runner.py:_assemble_prompt`).
Every entry must exist in the task directory
(`engine/taskdefs.py:load_task`).

### `components` (object, optional)

Port name -> **logical** binding name. Three ports (`tracker`,
`agent-session`, `messaging`) are bound automatically for every run at
prepare time (`engine/engine.py:BINDABLE_PORTS`). An entry here is
validated but currently inert: `engine/config.py:resolve_binding` honors a
task-supplied binding name only for the `gate` port, which is actually
selected via `gates.post[].adapter`, never via `components`. The field's
only live effect is the load-time check that a declared port is configured
in `components.yml` (`engine/config.py:validate_task_bindings`, run by
`agent-hq tasks validate`). Never a concrete adapter name — see "What a
task may not contain" below.

### `model` (string, optional)

Reserved; no adapter reads it. The executing model is configured in
`components.yml` under the `agent-session` binding's settings.

### `gates.post` (list, optional)

Each entry is `{approvers, adapter, timeout_working_hours}`; `approvers`
and `adapter` are required. The engine uses the **first** entry only (P0
has one gate per task; `engine/runner.py:_prepare` and
`engine/engine.py:sweep` both read `gates.post[0]`).

- `approvers` — a group name in `config/approvers.yml`; only comments by
  its members count as decisions.
- `adapter` — a **logical** gate name, resolved through `components.yml`'s
  `gate.named` map (or the plain `gate.adapter` default when the name is
  `default`) by `engine/config.py:resolve_binding`. Never a concrete
  adapter id.
- `timeout_working_hours` (number > 0, optional) — measured against the
  `working_hours` schedule in `config/approvers.yml`; a gate past it with
  no decision resolves `EXPIRED` at the next sweep, blocking the ticket and
  escalating.

Semantics: the gate fires only when the run's control outcome is
`handoff` — it gates the **pending handoffs**, parking the run
`WAITING_GATE` with the proposals stored until a decision
(`engine/runner.py:_collect_success`). A gated task that emits `complete`
proceeds straight to `SUCCEEDED` without a gate. Decisions are authorized
issue comments on the engine-repo ticket, per
`engine/adapters/github_issue_comment_gate.py`:

```
/agent-hq approve <run-id>
/agent-hq request-changes <run-id> <reason>
/agent-hq reject <run-id> <reason>
```

The latest decision by an approver-group member wins. Decisions are
noticed by the dispatch sweep — a `repository_dispatch` wake-up when a
producer sends one, else the `*/15` cron
(`.github/workflows/dispatch.yml`), so up to ~15 minutes of latency. See
[operations.md](operations.md) for the operational side.

### `outputs.artifacts` (list of strings, optional)

Declared output paths, `{ticket}` substituted with the issue number
everywhere they are used. These are **ledger artifacts**, not work-repo
code: the prompt lists them as required outputs; execute fails the run if
any is missing (`collect_outputs`); collect re-verifies them after the job
boundary, persists them under `tickets/<id>/artifacts/<run_id>/` on the
state branch (`engine/state.py:write_artifact`), and excludes them from the
work patch that lands on the branch. Together with the run's inherited
`input_artifacts` they form the **provenance set** — the only paths a
handoff may forward (`engine/handoff.py:validate_handoffs`).

### `opens_pr` (boolean, optional)

On a successful land, create — or reuse the ticket's existing — draft PR
from `agent-hq/<issue-number>` to the repo's base branch
(`engine/runner.py:_collect_success`). At most one PR per repo per ticket;
independent of any gate. Queue-empty completion marks recorded PRs ready
for review (`engine/engine.py:_complete_if_queue_empty`). `implement` sets
this.

### `handoff` (object, optional)

- `handoff.allowed` (list of task ids) — the only targets this task's
  `control.json` may propose; every entry must resolve to a loaded task
  (`engine/taskdefs.py:validate_library`).
- `handoff.max` (integer >= 0) — the most handoffs one run may propose in
  a single `control.json`. Default when omitted: 0, i.e. the task may not
  hand off at all.

A proposed set violating either — or any other check — is rejected
whole (`engine/handoff.py:validate_handoffs`); see
[task-authoring.md](task-authoring.md) "Handoffs" for the full validation
pipeline and the handoff-spawned run's identity rules.

### `tools` (list of strings, optional)

Allowed tool names, bundled at prepare (`engine/runner.py`) and translated
into CLI flags by the agent-session adapter, so the flag is
adapter-specific: `claude-code-headless` passes `--allowedTools
<comma-list>`; the default `copilot-cli` binding maps the names
(`Read`/`Grep`/`Glob` -> `read`, `Write` -> `write`, `Bash` -> `shell`)
and passes one `--allow-tool=<kind>` per mapped tool, with omitted or
empty meaning `--allow-all-tools`.
`review` uses this to run read-only plus `Write` (for its findings file).

### `budget` (object, required — all three keys required)

- `max_cost_usd` (number > 0) — per-run cost cap, enforced as headroom:
  the dispatcher and `apply_handoffs` refuse a run when the ticket's known
  spend plus this cap would exceed `config/budgets.yml`'s
  `ticket_cap_usd` (`engine/engine.py:check_budget`). Under the default
  `copilot-cli` executor, per-run cost is not metered (runs record
  `cost_usd: 0.0`), so this cap does not bind in that configuration — see
  [architecture.md](architecture.md) deviation 9.
- `max_runtime_min` (number > 0) — sets the run's deadline at claim time
  (`store.claim_run` in `engine/runner.py:_prepare`); the deadline is also
  handed to the agent adapter, and the dispatch sweep fails a `RUNNING`
  run past it (`engine/engine.py:sweep`).
- `retries` (integer >= 0) — failed attempts are re-enqueued until
  `attempt` reaches this count, then the ticket is `BLOCKED`
  (`engine/engine.py:_handle_failure`).

## The control-output contract

Every completed run writes exactly one `.agent-hq/control.json` — a single
JSON object validated against `schemas/control.schema.json`
(`additionalProperties: false`, including inside each handoff item) by
`engine/handoff.py:validate_handoffs` before anything in it is trusted. A
schema-invalid document **fails the run** (retrying per its own
`budget.retries`); it is never silently ignored.

The three outcomes, with their exact field rules from the schema:

| `outcome` | Required | Forbidden | Effect |
|---|---|---|---|
| `complete` | — | `handoffs` | Run `SUCCEEDED`, no children; feeds queue-empty completion. |
| `blocked` | `reason` | `handoffs` | Run and ticket `BLOCKED` with that reason; escalates; no retry. |
| `handoff` | `handoffs` (non-empty) | — | Proposals validated, then gated (`WAITING_GATE`) or applied as `QUEUED` child runs; run `SUCCEEDED` once applied. |

Each item in `handoffs` requires `key`, `task`, `reason`; optional `repo`
(must be a configured repo) and `artifacts` (each path must be in the
run's provenance set and containment-safe).

The contract is injected into every prompt automatically
(`engine/runner.py:_assemble_prompt`): the outcome shapes, this task's own
`handoff.allowed`/`max`, and its required output paths. A task never
spells this out in its own prompts, and the injection does not depend on
the task including `constitution` in `context`.

## What a task may NOT contain

- **Concrete adapter names.** `tests/test_task_library.py`
  (`test_no_concrete_adapter_name_leaks_into_task_defs`) fails the build if
  any `task.yml` contains a string like `github-issues`, `pr-review`,
  `github-issue-comment`, `claude-code-headless`, or `copilot-cli`. Every
  adapter reference in a task is a logical name resolved through
  `config/components.yml`.
- **Engine special-casing expectations.** No task id is special-cased by
  engine code; `intake` is engine entry logic, not a task, and `finalize`
  is a convention (declare `specs/{ticket}/summary.md`, emit `complete`),
  not a code path. A task that assumes the engine treats its name
  specially is wrong by construction.
- **Absolute or escaping artifact paths.** Every artifact path — declared
  output or handoff-proposed — is containment-checked: no absolute path,
  no `..` segment, no symlink escape from the worktree
  (`engine/handoff.py:_check_containment`).
- **Unknown keys.** `additionalProperties: false` throughout the schema; a
  key the schema does not name fails validation.

## Validation

```bash
.venv/bin/agent-hq tasks validate    # the task library
.venv/bin/agent-hq config validate   # config/ registries
```

`tasks validate` (`engine/cli.py:_tasks_validate`) loads every
`tasks/*/task.yml` — schema validation, on-disk `skills`/task-local
`context` existence, duplicate-id detection (`engine/taskdefs.py`) — then
cross-checks the library (every `handoff.allowed` target resolves to a
loaded task) and every task's declared `components` port against
`components.yml` (`engine/config.py:validate_task_bindings`). It loads the
config to do so, so a broken config fails this command too.

`config validate` loads the five registries (`components`, `repos`,
`projects`, `approvers`, `budgets`) against their schemas
(`engine/config.py:load_config`).

Both run in CI, alongside the test suite —
`tests/test_task_library.py` additionally pins the graph-level invariants
(expected task set, handoff graph, constructible gate adapters, the
concrete-adapter-name ban, no `tasks/intake/` directory).
