# Authoring a task

A task is one directory under `tasks/<id>/` with a `task.yml` validated
against `schemas/task.schema.json`, plus whatever `prompts/`/`checklists/`
skill files it references. There is no fixed chain and no task-name special
case in the engine (`intake` and `finalize` used to be special-cased; neither
is anymore -- see "Dispositions" below). A task joins the live graph the
moment some run's accepted `control.json` queues it; nothing else "wires it
in". Since any task in the library is queueable, that means editing a prompt --
there is no declared edge to add.

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
outcome `"queue"` (see "Control outcomes" below); the task definition only
constrains what's *allowed*:

- There is **no** per-task allowlist. Any task in the loaded library may be
  queued by any run; a target that isn't a loaded task id is rejected
  (`engine.handoff.validate_queue`).
- `budgets.max_queue_length` -- the most entries one run may declare in a
  single `control.json`. One global sanity bound rather than a per-task table:
  a run cannot queue 500 tasks, but which tasks it queues is its own call.
  Fan-out is a prompt decision -- the pilot's `spec` queues one `implement`
  entry per affected configured repo (`config/repos.yml`), each carrying that
  repo in the entry's `repo` field.

Validation is pure and total-rejection: `engine.handoff.validate_queue`
checks the whole declaration against `schemas/control.schema.json`, then
path containment on every artifact, then per-entry semantics (target in
the loaded library, `repo` if given is a configured repo, key uniqueness,
total count `<= budgets.max_queue_length`, and each artifact is in
the run's **provenance set** -- its inherited `input_artifacts` union its own
substituted `outputs.artifacts`, never an arbitrary worktree file). Any
single violation rejects the *entire* set, not just the offending item.

State-dependent guards that the pure validator can't see (each artifact's
ledger entry actually exists, and the ticket's loop/budget/depth limits
still hold) are enforced atomically in `engine.engine.apply_queue`, inside
the same state-store transaction that marks the source run terminal --
so a crash between "run succeeded" and "children queued" can't happen.
A queued entry's run identity is `(source_run_id, key, attempt)` only
-- the target task id is **not** part of it, so a re-delivered handoff key
always resolves to the same run id regardless of payload content (the first
accepted delivery wins; a duplicate is a no-op).

## Control outcomes

Every completed run writes exactly one `.agent-hq/control.json`
(`schemas/control.schema.json`, `additionalProperties: false` --
schema-invalid means the run *fails* per its own retry budget, never
"ignored"):

- `{"outcome": "queue", "queue": [...]}` -- `queue` required; entries run in
  the order listed. With no `gates.post` on this task they enqueue as `QUEUED`
  runs immediately and this run finishes `SUCCEEDED`. With a `gates.post`
  entry, they are stored as `run.pending_handoffs` and the run stops at
  `WAITING_GATE`; a gate `APPROVED` decision applies them and completes the
  run — unless that gate sets `auto_approve`, in which case they apply
  immediately as if there were no gate (see "Gates" below).

  An **empty** `queue` is how a run says "nothing further from me" — there is
  no separate `complete` outcome. This is what feeds queue-empty completion
  (see "Where the route ends" below), and a task with no
  prompt that queues anything (e.g. `finalize`) always emits it.

  A `queue` outcome may also remove pending work: `"cancel": ["<key>"]` drops
  named `QUEUED` entries, and `"cancel_pending": true` clears the whole
  remaining queue before this document's own entries are added. **Omission
  never cancels** — a run that simply does not mention a pending entry leaves
  it alone, so one branch of a fan-out cannot drop its sibling by saying
  nothing. Each removal is recorded as a `run.cancelled` event and the run
  becomes `CANCELLED`; runs are never deleted, because `runs` is the audit
  trail. A key matching no `QUEUED` entry is ignored; a key matching more than
  one is an error, since keys are unique only per source run.

  A run that stops at a gate may **not** also cancel: `pending_handoffs`
  carries its additions but nothing carries its removals, so approving later
  would apply half the declaration. The engine rejects that combination
  outright rather than half-applying it.
- `{"outcome": "blocked", "reason": "..."}` -- `queue`/`cancel`/
  `cancel_pending` forbidden, `reason` required; the run is recorded blocked
  and the ticket moves to `BLOCKED` with that reason, escalating to a human
  with no auto-retry.

Any outcome may also carry `summary` -- a Conventional Commits description of
what the run changed in the work repo. Its first line becomes the subject of
the commit the run lands, the rest the body; the ticket reference and run id
are appended as trailers. A run's own commits are squashed into that single
commit by `materialize_work_patch`, so `summary` is the only description that
reaches the work repo. A run that changed no files can omit it (collect falls
back to the ticket title).

`engine.runner._assemble_prompt` injects this contract into every prompt
automatically (the required outcome shapes, the `summary` convention, this
the queueable task list and `max_queue_length`, and the output path) -- a task never needs
to spell this out itself, and it does not depend on the task including
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
  transitive handoff still resolves. Artifacts are stored as **bytes** --
  they are not all text (`qa`'s screenshots), and anything that inlines one
  into a comment decodes it, skipping what has no text.
- **Directory artifacts.** An `outputs.artifacts` entry ending in `/` is a
  directory: the engine collects whatever files it holds, recursively, zero
  or more (`engine.runner._expand_declared`). Use it for output a task cannot
  name in advance -- `qa` writes one video (and optional screenshots) per
  acceptance criterion it managed to exercise, which is not a list anyone can
  write into `task.yml`.
  Unlike a plain entry they are never *required*: an empty or absent
  directory is a valid run. They expand to concrete paths before anything is
  recorded, so `run.artifacts`, handoff forwarding, and `_inputs_ready` only
  ever see real files -- nothing downstream knows the convention exists.
- **Input artifacts** on a handoff-spawned run
  (`run.input_artifacts`, copied from the accepted handoff's `artifacts[]`
  at apply time) are the run's **only** input source -- there is no
  separate task-level input list. Prepare restores their content from the
  **source** (parent) run's ledger namespace (`engine.runner
  ._restore_input_artifacts`) into a transported manifest -- execute (its
  own, credential-free Actions job, hardening plan Task 12) then
  materializes them into its worktree (`engine.runner._materialize_inputs`),
  so a child reads exactly what its handoff accepted, never a sibling's
  file. A **root** run (intake's first task, or a comment inserted with no
  declaring handoff) has no such list: prepare inherits every file in the
  input source's ledger namespace (`GitJsonStateStore.list_artifacts`) --
  declared outputs plus anything that run forwarded into its own directory
  -- not only `run.artifacts`, which omits the forwarded set.
- The **work patch** excludes both: execute's `materialize_work_patch`
  diffs out every declared output path and every inherited
  `input_artifacts` path before handing the patch to collect, which
  `git apply`s it to a fresh clone and lands it on the target branch
  (`engine.runner._collect_success`). Neither is code; both live only in
  the ledger.
- **Reject-time retention.** When collect emits `run.artifact_rejected`
  (missing declared outputs, dishonest `qa-report.json`, or a work patch
  that failed to apply) and staged artifact bytes exist, those bytes are
  still written under `tickets/<id>/artifacts/<run_id>/` for tracing.
  The failed run keeps `artifacts: []` so reject evidence cannot unlock
  handoff children via `_inputs_ready`. GIF derive, landing, and green
  `:pr-qa` posting remain success-only; a rejected `qa-report.json` may
  still announce `:pr-qa-rejected` when a work PR already exists.

Every artifact path a handoff proposes is **containment-checked** against
the worktree root before it's trusted anywhere (absolute paths, `..`
segments, and symlink escapes are all rejected;
`engine.handoff._check_containment`).

## Gates

`gates.post` is a list (P0 uses one entry) of `{approvers, adapter,
timeout_working_hours, auto_approve}`. `approvers` names a group in `config/approvers.yml`;
`adapter` is a **logical** gate name resolved through `components.yml`'s
`gate.named` map (or the plain `gate.adapter` default) -- never a concrete
adapter id. The pilot's `default`/`spec-approval` logical names both resolve
to the `github-issue-comment` adapter (an authorized-comment approval on the
parent engine issue); `pr-review` remains registered for a task that wants a
work-repo-PR-based approval instead. See `docs/ports/gate.md` for the full
adapter contract. A gate past `timeout_working_hours` with no decision
resolves to `EXPIRED` at the next sweep, blocking the ticket and escalating.

`auto_approve: true` decides the gate without a human: the run never enters
`WAITING_GATE` and its handoffs apply immediately. It defaults to false — a
declared gate is a human decision unless the task says otherwise.

What it does **not** skip is the record. The gate still posts its comment,
carrying the run's declared artifacts exactly as a real request would — that
comment is where a spec becomes readable to a human, and an auto-approved
task that posted nothing would be invisible in the thread. It is rendered as
a record rather than a request: heading "Gate auto-approved", no decision
grammar, and no `@`-mention of a group with nothing to decide. A
`gate.decided` event records it in the ledger too.

Turning it on is **retroactive**. The sweep honors it for runs already parked
at `WAITING_GATE`, so flipping the flag drains the gates currently waiting on
the next pass rather than stranding them behind a flag that says they need no
human. Those runs already posted a request comment asking for a decision that
will now never come, so the sweep posts a short follow-up saying the gate was
auto-approved after the fact. Turning the flag back off is not retroactive in
the same way — a run that already sailed through is finished.

Use it for a checkpoint you want in the graph but not in the critical path
today — a task whose gate you intend to staff later, or one you are still
tuning. Note what it costs: `WAITING_GATE` is also what holds a ticket's
in-flight slot for review, so auto-approving trades a human checkpoint for
throughput. Weigh that per task, not as a default. Because it lives in the
task definition, it applies to **every** deployment of the library; a gate
that should be automatic in one environment and staffed in another wants a
config-level switch instead, which does not exist yet
(`docs/roadmap.md`).

## Environment setup

A task rarely wants to build its own environment. `repos.yml` carries a
`setup` map per repo — task id to shell command, with `default` covering any
task that has no entry of its own:

```yaml
agentalec/care_fe:
  setup:
    default: npm ci
    qa: |
      make -C .agent-hq/care up load-fixtures
      npm ci && npm run build
  format:
    implement: |
      # prettier --write on git-changed files only (exclude .agent-hq)
```

The engine runs setup in the worktree before the agent starts
(`engine.runner._run_setup`), and resolution is
`setup[task_id] or setup["default"] or None`
(`engine.engine.resolve_setup`). An optional `format` map has the same shape
and resolution (`engine.engine.resolve_format`): after a successful agent run
on a task with `writes_code: true`, execute runs it before
`materialize_work_patch` (`engine.runner._run_format`). Collect does not
reinstall deps or reformat. Both live in config, not in a prompt or in
engine code, so a different project configures a different command without
touching either.

Why it is not the agent's job: a fixed sequence of shell commands costs one
agent request per step under a per-request billing model, fails differently
every time, and is exactly the part that needs no judgment. Doing it in shell
also means a broken environment **fails the run** — non-zero exit becomes a
normalized `execute-result` failure carrying the command and a log tail, so
the ordinary retry budget applies and the reason reaches the ticket. The
alternative is an agent flailing against a half-built environment and
reporting whatever it managed, which is what QA did before this existed.

The command runs with the engine's credentials stripped
(`AGENT_HQ_TOKEN`/`GITHUB_TOKEN`/`GH_TOKEN`/`COPILOT_GITHUB_TOKEN`): it is
operator-authored config and so trusted further than agent output, but it has
no business holding tokens. It is bounded by the run's own deadline — note
that deadline starts at *claim* time, so setup (and format) time comes out of
the task's `budget.max_runtime_min`.

Anything the agent needs to know goes in `.agent-hq/setup-notes.md` (URLs,
credentials, paths). When a setup command is configured, the assembled prompt
gains an Environment section telling the agent the worktree is already
prepared, to read that file, and not to rebuild anything itself. The engine
never learns what the command did — that contract is entirely between the
config and the notes file.

## Budgets

Per-task `budget.max_cost_usd`/`max_runtime_min`/`retries` bound one run.
Ticket-wide caps live in `config/budgets.yml`: `ticket_cap_usd` (total spend
across every run on a ticket), `in_flight_cap` (global concurrent-ticket
cap), and `loop_guard.max_runs` (runaway protection --
total run count and causal chain depth). All four are checked before a
handoff set is applied (`engine.engine.apply_queue`) and before a queued
run is dispatched, so a task cannot out-run these limits by proposing more
handoffs. Under the default Copilot-billed executor, run cost is not
metered (`cost_usd: 0.0`, `usage_known: true`), so `max_cost_usd`/
`ticket_cap_usd` don't bind in that configuration -- `retries`, the loop
guard, the in-flight cap, and runtime deadlines still do (see
`docs/architecture.md` deviation 9).

## Where the route ends

Queue-empty completion (`engine.engine._complete_if_queue_empty`) fires once a
ticket has no `QUEUED`/`RUNNING`/`WAITING_GATE` run and no pending entries left
anywhere. What it does then depends on **which task** the terminal run was:

- **It is `config.projects.final_task`** (`finalize` in the pilot): the route
  reached its designed end. The closing summary posts from that run's ledger
  copy of `specs/{ticket}/summary.md`, every recorded work PR is marked ready,
  and the ticket goes `AWAITING_MERGE` (or `DONE` when no PR exists).
- **It is anything else**: the queue ran dry early. The ticket goes `BLOCKED`
  with that reason and escalates. "I am done" and "I stopped" are different
  facts, and only one of them should close a ticket.

This used to key off whether the terminal run happened to produce
`specs/{ticket}/summary.md` -- a filename the engine had to know about, sitting
oddly beside "the engine special-cases no task name". `final_task` is config,
the mirror of `initial_task` and `feedback_task`, so "the route finished" and
"someone wrote a file with the right name" stop being the same question.

`final_task` still needs to declare `specs/{ticket}/summary.md` as an output so
there is something to post; a required declared output means a run that didn't
write it fails rather than completing silently. A **reopened** ticket cannot
complete off a prior lifecycle's stale summary, because the summary is read from
the terminal run's own ledger namespace.

A task that gives up rather than finishes should emit
`{"outcome": "blocked", "reason": "..."}` -- `review` does exactly this when its
round cap is reached. That is what labels the issue for a human, escalates, and
records the reason; queueing nothing would instead look like the route ending
somewhere unexpected.

## Validation

- `agent-hq tasks validate` loads every `tasks/*/task.yml`
  (`engine.taskdefs.load_all`, schema + on-disk skill/context checks),
  cross-checks the library (`engine.taskdefs.validate_library`: every
  ids are unique and self-consistent), and checks every
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
| spec | Routed through by the pilot's prompts. Gated (`spec-approval`) but currently `auto_approve: true` -- the checkpoint is declared and evented, decided by the engine rather than a product owner; staffing it is deleting that one line. Its prompt queues one `implement` entry per affected configured repo (the fan-out point), or nothing when the ticket needs no change. |
| arch-plan | Defined; **no prompt queues it**. Nothing to activate beyond a prompt that names it -- any task in the library is queueable. |
| arch-approval | Defined; **no prompt queues it**. Confirms the plan artifacts, no changes; gated (`default`). |
| breakdown | Defined; **no prompt queues it**. Would queue one `implement` entry per affected repo. |
| implement | Routed through. `opens_pr: true`; its prompt queues `review`. Writes required `specs/{ticket}/qa-plan.md` (research map + Action/Expect/Record steps per user-facing criterion) and forwards it with `spec.md` so QA never invents a click path from scratch. |
| review | Routed through. Its prompt loops back to `implement` while blockers remain (prompt-capped at 3 rounds; on the cap it emits `outcome: blocked` and the engine posts the accumulated `review.md` findings to the thread, parking awaiting-human with the PR left in draft), else queues `qa`, forwarding `spec.md`, `review.md`, and `qa-plan.md`. Round memory is `review.md` forwarded around the loop as an input artifact. Every review round also reflects its latest-round findings onto the work-repo PR as a comment (`engine.engine.post_pr_comment`, in the credentialed collect phase -- the read-only agent can't, PD-5). |
| finalize | Routed through, and named by `config.projects.final_task`: writes `summary.md`, queues nothing, and its completion is what finishes the ticket (see "Where the route ends"). Still no task-name special case in the engine -- the name lives in config, and pointing `final_task` elsewhere moves the endpoint. |
| clinical | Defined; **no prompt queues it**. Gated (`clinical-reviewers`, `default` adapter). |
| poll | Converted, defined, **unwired** -- needs the P1 reaction-based `poll` adapter (`docs/roadmap.md`); no task currently hands off to it. |
| docs | Defined; **no prompt queues it** -- it belongs between `qa` and `finalize`, so `qa`'s prompt would name it. |
| qa | Routed through. Its prompt always queues `finalize` -- `qa` reports, it never gates. `writes_code: false`, so the engine discards its work patch outright: everything it leaves in the worktree is scratch (including throwaway drivers), and an instruction to keep scratch under `.agent-hq/` is advisory where discarding is not. Stands the app up with the work repo's own tooling inside the devcontainer and executes `qa-plan.md` **serially** — one isolated Playwright driver per criterion (`node specs/{ticket}/qa-drivers/{id}.mjs`), never parallel workers or a shared recording across ACs — with `recordVideo` (default evidence; `viewport` must equal `recordVideo.size`, care_fe 1440×900 — mismatched sizes grey-letterbox) plus `page.screencast.showActions({ cursor: "pointer" })` so clicks are visible; it declares **no** `components` port, so the deferred `qa-env` binding (`docs/ports/qa-env.md`) is still not required. Required `qa-report.json` is validated at collect (`engine.qa_report.validate_qa_report`, filename convention — no task-id special case): a `pass` needs `live-flow` + canonical `specs/{ticket}/videos/{id}.webm` (exclusive ownership), matching ledgered `qa-drivers/{id}.mjs`, and non-empty `qa-logs/{id}.log` (repo `qa.video`, default true); screenshots stay optional (`qa.screenshots`). `not-exercised` + `missing-test-data` also requires `seed_attempt` (`method` `ui`\|`api`\|`both` + non-empty `summary` of the seed ladder), **non-empty `plan_steps_run`**, and the same canonical driver + non-empty log receipts; a prose-only claim (empty steps / missing receipts) fails collect so retry gets rework feedback. Any `fail` / `not-exercised` with non-empty `plan_steps_run` needs those receipts too; a true pre-execution blocker (e.g. `no-qa-plan`) may stay log-free. Auth readiness is prompt/setup-notes only — authenticated shell probes (not URL-without-`/login`), then JWT refresh and fresh UI login before `auth-failure`; the engine does not special-case CARE login paths. Seed recipes and selectors come from per-ticket `qa-plan.md` plus worktree discovery (`tests/PLAYWRIGHT_GUIDE.md`, `tests/**`, `src/types/**/*Api.ts`), not a static CARE routes encyclopedia under checklists. Directory artifacts `videos/`, `screenshots/`, `qa-drivers/`, and `qa-logs/` are kept out of the work repo (ledger only); collect best-effort derives a lite sibling `.gif` per WebM (`ffmpeg`, presentation-only — missing gif does not fail the run), rewrites `qa.md`'s relative media links into **blockquoted** collapsed `<details>` GIF previews (or a plain WebM link when no gif), and appends summary counts (`3 pass / 2 not-exercised`) before posting to the PR (`engine.runner._ledger_image_urls`). On `artifact_rejected`, staged bytes (report/videos/drivers/logs) are still ledgered under the failed run for tracing while `run.artifacts` stays empty. A dishonest/incomplete report still fails the run (no soft-pass), but collect ledgers the evidence and posts a clearly labeled **rejected (not a pass)** PR comment (`:pr-qa-rejected`) when a work PR already exists. |

None of the above is a name the engine special-cases; every row describes a
task-graph state (wired vs. defined-but-unwired), not an engine code path.
