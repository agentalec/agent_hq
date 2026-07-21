# Plan — generic sequential handoff orchestration

Status: proposed
Last updated: 2026-07-21

## Outcome

Refactor `agent_hq` from a fixed task chain into a generic, handoff-driven
engine with:

- one parent GitHub issue in the engine repository per body of work;
- one ordered task queue and at most one active task per issue;
- all state on the existing orphan `agent-hq-state` branch, partitioned by
  ticket directory;
- one stable branch and PR per issue in each affected work repository;
- explicit, validated task handoffs;
- one central dispatcher workflow;
- issue-based orchestration approvals and PR-based code approvals;
- credential-isolated prepare, execute, and collect jobs;
- optional GitHub Agentic Workflows execution hardening; and
- optional Spec Kit templates inside tasks, without a second scheduler.

`docs/roadmap.md` remains the backlog for unrelated deferred features. This
file is the source of truth for the refactor.

## Decisions

1. **Sequential within an issue.** Remove the planned dependency DAG,
   fan-out/fan-in, and task reordering. Different issues may run concurrently.
2. **Keep one global state branch.** Store every ticket under
   `tickets/<issue-number>/` on the existing orphan `agent-hq-state` branch.
   Per-issue state branches are deferred unless post-split write contention is
   measured to be a throughput problem.
3. **Parent issues live in the engine repository.** The engine-repository
   issue number is the canonical ticket key. Intake, comments, close, and
   reopen events are therefore local and event-driven.
4. **One work branch per issue and repository.** Reuse
   `agent-hq/<issue-number>` for implementation, tests, QA fixes, and
   documentation in each affected repository.
5. **Commits are checkpoints, not triggers.** Commit state first, then send an
   explicit `repository_dispatch` wake-up. The 15-minute cron is recovery.
6. **The dispatcher is central.** Keep one `dispatch.yml` on `main`; do not
   create dispatcher workflows on state or work branches.
7. **Claims enforce concurrency.** The in-flight cap is checked inside the
   state claim transaction. A rejected non-fast-forward push is the
   compare-and-swap that forces a re-read and recount.
8. **Tasks are generic configuration.** The engine contains no behavior keyed
   to names such as `product`, `qa`, `intake`, or `finalize`.
9. **Handoffs are untrusted proposals.** The engine validates them against the
   task library, repository config, port bindings, and path-containment rules
   before changing the queue.
10. **No direct agent privileges.** Agents cannot choose workflows, secrets,
    permissions, tools, budgets, or arbitrary repositories.
11. **Approvals follow the artifact.** Orchestration approvals happen on the
    parent issue; code approval remains on work-repository PRs.
12. **DONE means engine complete, not shipped.** When work and gates are
    exhausted and a closing summary exists, required PRs are marked ready,
    the parent issue is closed, and the ticket becomes `DONE`. PR merge state
    is not tracked.
13. **A human close stops active work.** Closing an issue before its work is
    exhausted sets the ticket `BLOCKED`, cancels and fences the active run,
    and preserves the queue and gates for an explicit resume.
14. **Reopen is guarded.** An authorized reopen command or native issue reopen
    resumes a ticket blocked by issue closure. It can restart a `DONE` ticket
    only when every recorded work PR is still open or no work PR exists.
15. **The pilot is public-repository only.** GitHub Pages may render public
    state. Intake must reject content that is not public-safe. Private
    deployments use the operator CLI until an authenticated dashboard is
    justified.
16. **No Codespaces automation.** Actions may reuse `.devcontainer` through
    `devcontainers/ci`; they do not create or manage Codespaces.
17. **GitHub AW is an execution adapter, not the scheduler.** It may replace
    the native execute-job boundary after the core handoff model works.
18. **Spec Kit is a task methodology, not the scheduler.** Use its templates
    selectively; `agent_hq` owns sequencing, branches, state, and gates.

## Target lifecycle

```text
Engine-repository issue labeled for intake
  -> create tickets/<issue-number>/ on agent-hq-state
  -> enqueue the configured initial task
  -> dispatcher advisory check
  -> claim transaction rechecks the global in-flight cap
  -> prepare -> credential-free execute -> trusted collect
  -> validate and commit artifacts, patch, result, and state
  -> apply a gate or append validated handoffs in order
  -> explicitly wake the dispatcher
  -> repeat one task at a time

ACTIVE + operator block or non-engine issue close with work remaining
  -> BLOCKED; cancel/fence active run; preserve queue and gates
  -> authorized unblock/reopen: ACTIVE; retry interrupted task if any

ACTIVE with queue/current/gates empty
  -> summary.md present: mark required PRs ready, close issue, DONE
  -> summary.md absent: await human input; do not complete automatically

DONE + authorized reopen/native issue reopen
  -> all recorded PRs open or no PRs: ACTIVE + configured initial task
  -> any recorded PR merged/closed: remain DONE; require a new ticket
```

`DONE` must be displayed as “engine complete; merge status not tracked.” A
non-engine actor closing an otherwise complete issue is accepted as a human
declaration of completion.

## State and branch layout

```text
agent_hq repository
  main
    engine, schemas, task definitions, workflows, docs

  agent-hq-state                         # existing orphan state branch
    tickets/<issue-number>/
      state.json                         # runs (single source of truth) +
                                          # handoffs, approvals, lifecycle
      events.jsonl                       # per-ticket event log
      artifacts/                         # product.md, clinical.md, summary.md
    health/latest.json                   # existing adapter-health snapshot

work repository
  agent-hq/<issue-number>                # stable work branch
    implementation, tests, QA fixes, docs
  PR: agent-hq/<issue-number> -> configured base branch
```

`state.json`'s `runs` array is the single source of truth for a ticket; there
is no stored `queue`, `current`, or `history` field. Queue (`QUEUED` runs in
insertion order), current (the one `RUNNING`/`WAITING_GATE` run), and history
(terminal runs) are derived views computed from `runs`, not persisted
separately. **Note:** the executable task plan
(`.hyperclaude/plans/20260721-2056-harden-the-existing-plan-at.md`) is
authoritative over this document wherever the two differ on state-layout
detail.

Enumeration is one shallow state-branch fetch followed by a directory listing.
Completed tickets remain in place and are hidden by lifecycle status. The
state store's fetch/reset/replay loop is the write-concurrency model after the
job split; shallow fetches keep checkout cost independent of branch history.

## Phase tracker

| Phase | Scope | Status | Depends on |
|---|---|---|---|
| 0 | Freeze identity, lifecycle, and cutover contracts | Pending | — |
| 1 | Schemas, models, and configuration validation | Pending | 0 |
| 2 | Global state-store extensions | Pending | 1 |
| 3 | Atomic handoff and task-library cutover | Pending | 1, 2 |
| 4 | Dispatcher and isolated task-run jobs | Pending | 2, 3 |
| 5 | Stable work branches and PRs | Pending | 2, 4 |
| 6 | Approvals and ticket lifecycle | Pending | 3–5 |
| 7 | Dashboard and operator workflows | Pending | 2, 4, 6 |
| 8 | GitHub Agentic Workflows evaluation | Pending | 3–5 |
| 9 | Spec Kit task integration | Pending | 3, 5 |
| 10 | End-to-end validation and closeout | Pending | 1–9 |

## Phase 0 — freeze identity, lifecycle, and cutover contracts

- [ ] Record that parent issues live in the engine repository and the issue
  number is the canonical ticket key.
- [ ] Define `agent-hq/<issue-number>` base-branch selection for every work
  repository.
- [ ] Record the lifecycle states and edges: `ACTIVE`, `BLOCKED`, and `DONE`;
  queue-empty completion; operator block/unblock; guarded reopen.
- [ ] Record that `DONE` means engine complete and PR merge status is
  deliberately untracked; supersede architecture deviation 7 accordingly.
- [ ] Define approval and `/agent-hq reopen <reason>` commands and configured
  approver groups.
- [ ] Confirm the pilot repositories are public and add an intake governance
  gate requiring issue content and generated artifacts to be public-safe.
- [ ] Start the schema cutover from a clean `agent-hq-state` ticket area:
  confirm no live ticket depends on existing directories, then archive them
  outside the active `tickets/` namespace or remove them before writing the
  new state format.
- [ ] Use a clean, atomic cutover: no production interval may run static
  `on_success.enqueue` and handoff progression together.

Exit: identity, lifecycle, public-data policy, and clean-cutover behavior are
settled before schemas or workflows change.

## Phase 1 — schemas, models, and configuration validation

- [ ] Extend ticket state with `runs` as the single source of truth — queue,
  current, and history are derived from `runs`, not separately stored — plus
  work repositories, handoffs, approvals, and lifecycle state.
- [ ] Add structured task control output with exactly three outcomes:
  `handoff`, `complete`, and `blocked`.
- [ ] Define each handoff with a stable `key`, registered target task, reason,
  optional configured repository, and declared input artifacts.
- [ ] Derive handoff identity from `<source-run-id>:<handoff-key>` rather than
  list position.
- [ ] Add only proposed, accepted, and rejected handoff events; human queue
  editing and `superseded` remain deferred together.
- [ ] Add `handoff.allowed` and `handoff.max` to the task schema and delete
  `on_success.enqueue` from the post-cutover schema.
- [ ] Make task-library validation reject every `handoff.allowed` target that
  does not resolve to a registered task ID.
- [ ] Add configured `initial_task`; intake must not infer it from another
  task's success chain.
- [ ] Require every task's declared component/port to have a configured
  binding. Add `qa-env` to the component schema so an unbound QA task cannot
  be registered.
- [ ] Store work-repository branch, PR reference, recorded head, and base
  branch. Query PR status only when guarded reopen needs it.
- [ ] Keep schemas and dataclasses synchronized and update pinned model tests.
- [ ] Record lifecycle block reason/source and any interrupted run needed for a
  safe attempt+1 resume after a human closes an active issue.

Exit: invalid state, control output, task targets, and unbound ports fail local
validation with actionable errors.

## Phase 2 — global state-store extensions

- [ ] Keep the orphan `agent-hq-state` branch and existing per-ticket
  directory layout.
- [ ] Extend `GitJsonStateStore` for the queue, handoff, approval, lifecycle,
  repository, and artifact documents introduced in Phase 1.
- [ ] Store declared orchestration artifacts under
  `tickets/<issue-number>/artifacts/`.
- [ ] Enumerate tickets by listing `tickets/*/` after one shallow fetch.
- [ ] Preserve `health/latest.json`; do not derive global health by scanning
  ticket events.
- [ ] Make transactional replay the concurrency model: rejected pushes fetch,
  reset, and replay the state mutation with bounded attempts and jittered
  backoff.
- [ ] Ensure a mutation that declines after replay, including a refused claim,
  exits without committing.
- [ ] Keep completed ticket directories as the audit mechanism; hide them by
  state rather than renaming refs or directories.

Exit: concurrent writes to different tickets replay safely on the shared ref,
and the new documents remain idempotent under re-delivery.

## Phase 3 — atomic handoff and task-library cutover

- [ ] Require every successful agent task to emit schema-valid control output
  under `.agent-hq/`; runner metadata never enters a work-repository commit.
- [ ] Treat declared artifact paths as untrusted: reject absolute paths, `..`,
  missing paths, and symlink escapes before joining or collecting them.
- [ ] At collect, validate that each handoff target is registered and allowed
  by the source task; its repository is configured; count is within
  `handoff.max`; keys within one output are unique; depth, loop, and budget
  guards pass; and every artifact exists and is contained.
- [ ] Reject the whole emitted handoff set when any member is invalid.
- [ ] Never accept tools, permissions, secrets, prompts, budgets, or raw
  workflow names from agent output.
- [ ] Append accepted handoffs in emitted order, permit at most one `RUNNING`
  or `WAITING_GATE` task per ticket, and forbid agent edits to accepted,
  running, or completed entries.
- [ ] Store gated handoffs as pending. Approval appends them with the same
  `<source-run-id>:<handoff-key>` identity, making re-delivery a no-op.
- [ ] Make collect, gate resolution, and crash re-drive apply handoffs
  idempotently.
- [ ] Atomically land the engine handoff path, remove every engine consumer of
  `on_success.enqueue`, convert every registered task, and switch intake to
  configured `initial_task` in one change.
- [ ] Remove `intake` and `finalize` name-based behavior from the engine.
  Queue-empty state drives completion; a configured terminal task produces
  the required `summary.md` without receiving special engine treatment.
- [ ] Record a disposition for every existing task: converted, absorbed into
  queue-empty completion, removed, or left unwired pending a declared port.
- [ ] Keep QA as an unwired task until its declared `qa-env` binding exists;
  do not build that adapter merely to complete this refactor.
- [ ] Replace hard-coded `P0_CHAIN` tests with generic library, handoff-target,
  port-binding, and zero-concrete-adapter validation. Include `copilot-cli` in
  the forbidden concrete-adapter-name check.

Exit: fixtures route only through configured tasks, and no static chain or
task-name special case remains in engine code.

## Phase 4 — dispatcher and isolated task-run jobs

- [ ] Keep one `.github/workflows/dispatch.yml` on `main` with its `*/15`
  recovery cron, manual dispatch, and `agent-hq-dispatch` event.
- [ ] Accept an optional issue number in the repository-dispatch payload for a
  narrow fast-path scan; scheduled and unscoped runs scan all active ticket
  directories.
- [ ] Keep the dispatcher concurrency check as a cheap advisory pre-filter.
- [ ] Enforce the in-flight cap again inside the claim transaction on
  `agent-hq-state`. A competing rejected push must re-read and recount before
  retrying; a cap-rejected run remains `QUEUED` and unclaimed.
- [ ] Claim at most one ready task per ticket per pass and pass ticket key and
  run ID to the stable task-run workflow.
- [ ] Keep layered duplicate defenses: queued-state check, active GitHub-run
  lookup, per-run concurrency group, and atomic claim.
- [ ] Replace the long-held global Actions concurrency group with short state
  transactions plus per-ticket run concurrency. Document push/replay as the
  cross-ticket serialization mechanism.
- [ ] Split task execution into prepare, execute, and collect jobs.
- [ ] Give execute `permissions: {}` and no secret except the dedicated
  `COPILOT_GITHUB_TOKEN`; never expose the engine PAT. Public work repositories
  need no clone credential.
- [ ] Transfer only same-run Actions artifacts: the working-tree patch,
  schema-bound `execute-result.json`, and a separate archive of declared
  ledger artifacts. Never transfer `.git`.
- [ ] Make collect use a fresh clone, apply the patch with `git apply`, validate
  the result and artifact paths, and never execute builds, tests, hooks, or
  scripts from agent output. A patch that does not apply fails the run.
- [ ] Preserve `.agent-hq/` stripping and push stable work branches with
  `--force-with-lease` against the recorded head so a zombie run cannot
  overwrite newer work.
- [ ] Keep prepare and collect credentialed for state, repository, and API
  writes; all engine-side writes happen in collect.
- [ ] Immediately before each external collect side effect, revalidate that
  the claimed run is still current and the ticket is `ACTIVE`; blocking
  invalidates that claim so later collect work becomes a stale no-op.
- [ ] Commit state before wake-up and re-drive lost workflows after the grace
  period without duplicating side effects.

Exit: the cap holds under concurrent claims, one ticket stays sequential, two
tickets may progress concurrently, and execute cannot access engine write
credentials or smuggle executable repository state into collect.

## Phase 5 — stable work branches and PRs

- [ ] Create `agent-hq/<issue-number>` once per affected work repository from
  its configured base branch and reuse it for every later task.
- [ ] Open at most one work PR per ticket per repository.
- [ ] Commit orchestration artifacts to the state branch; commit collected
  implementation, tests, QA fixes, and documentation patches to their stable
  work branches.
- [ ] Preserve the recorded branch head through review and rework; never fall
  back to the base branch after a failed downstream task.
- [ ] Let tasks such as QA read the exact recorded heads of all required work
  repositories after their changes are present.
- [ ] On queue-empty completion, mark required PRs ready but do not track or
  wait for their merges.
- [ ] On reopen, query recorded PRs once. If any is merged or closed, leave the
  ticket `DONE`, post a deduplicated explanation, and require a new ticket.
  Do not recreate deleted work branches.

Exit: later task patches remain in one mergeable PR per affected repository,
and a reopened ticket cannot overwrite or recreate completed work.

## Phase 6 — approvals and ticket lifecycle

- [ ] Extend `.github/workflows/intake.yml` to subscribe to
  `issue_comment: created` and `issues: closed/reopened`, then route those
  payloads to the engine alongside its existing open/labeled intake events.
- [ ] Add an issue-comment gate adapter for configured orchestration approvals.
- [ ] Require explicit decision commands containing the run/task ID, verify
  the commenter against the configured approver group, and record decision,
  actor, source comment, and time before advancing.
- [ ] Continue using work-repository PR reviews for code approval.
- [ ] Keep the pinned issue comment synchronized with current task, pending
  gate, ordered queue, blockers, work PRs, and the honest `DONE` meaning.
- [ ] Make collect, gate resolution, and sweep perform the same idempotent
  queue-empty check for an `ACTIVE` ticket, keyed by
  `{ticket}:{terminal-run-id}:done`.
- [ ] If `summary.md` exists, post it as the closing comment, mark required PRs
  ready, close the issue idempotently, and set `DONE`.
- [ ] If `summary.md` is absent, update the pinned comment with “tasks complete,
  no closing summary — awaiting human input” and take no terminal action. A
  later pass may retry, or a non-engine actor may close the issue as a human
  declaration of completion.
- [ ] Handle a non-engine `issues: closed` event for an otherwise complete
  ticket by setting `DONE` without requiring `summary.md`.
- [ ] Handle a non-engine close while work, a gate, or a current run remains by
  atomically setting `BLOCKED` with reason `issue_closed`, preserving the
  queue and pending gates, marking an active run interrupted, updating the
  pinned comment, and requesting cancellation of its Actions run.
- [ ] Parse `/agent-hq reopen <reason>` with the approval-command machinery,
  require an authorized commenter, and deduplicate by comment ID. Treat
  `issues: reopened` as the equivalent native signal.
- [ ] Resume a ticket blocked specifically by issue closure on authorized
  reopen/unblock: reopen the issue if needed, return to `ACTIVE`, retain the
  queue and gates, and enqueue attempt+1 of an interrupted task. Reopening must
  not clear an unrelated block reason.
- [ ] Reopen only a `DONE` ticket whose recorded PRs are all open or absent;
  set it `ACTIVE`, reopen the parent issue idempotently, enqueue configured
  `initial_task`, and retain the reason in ticket context.
- [ ] Filter the engine actor and event markers from `issue_comment` and
  `issues` triggers. Lifecycle guards make the engine's own reopen echo a
  no-op after state is already `ACTIVE`.

Exit: unauthorized and self-authored events cannot advance or reopen work,
queue-empty completion is idempotent, and merge state is never presented as
engine state.

## Phase 7 — dashboard and operator workflows

- [ ] Make the public Pages job check out `agent-hq-state`, list ticket
  directories, and render one server-side snapshot without browser-side raw
  GitHub fetches.
- [ ] Require public-safe ticket data in public mode. Disable Pages for private
  deployments and use the authenticated operator CLI instead.
- [ ] Continue reading adapter health from `health/latest.json`.
- [ ] Hide `DONE` tickets from the default view without deleting state.
- [ ] Refresh after state changes and retain the existing scheduled refresh as
  recovery.
- [ ] Define operator commands precisely: `retry` enqueues a new attempt of a
  terminal FAILED/BLOCKED run; `reconcile` runs the sweep for one ticket;
  `block` records an operator event and sets `BLOCKED`; `unblock` records an
  event and returns to `ACTIVE` with the queue intact. Unblocking an
  `issue_closed` stop also reopens the issue and retries any interrupted task.
- [ ] Do not add operator queue editing. Restore it only with a concrete need.

Exit: Pages and the operator CLI agree with state after re-delivery, blocking,
approval, completion, and reopen; private deployments publish no Pages site.

## Phase 8 — GitHub Agentic Workflows evaluation

- [ ] Keep the core engine independent of GitHub AW.
- [ ] Spike one configured task as an `agent-session`/executor backend using a
  compiled GitHub Agentic Workflow.
- [ ] Verify run-ID input, read-only execution, network policy, artifact
  transfer, threat detection, and trusted structured-output collection.
- [ ] Apply handoffs and patches only in a narrowly scoped trusted collect
  step; never give the agent the engine write credential.
- [ ] Verify target-repository tests against the existing devcontainer; do not
  assume GitHub AW automatically uses `.devcontainer`.
- [ ] Adopt `gh aw compile --strict` and commit source plus lock workflow only
  if the spike meets execution and debugging requirements.
- [ ] Add `agent-hq workflows build --check` only if task definitions truly
  need different static workflow envelopes.

Exit: GitHub AW is either a proven executor adapter with a documented native
fallback or rejected with a recorded reason.

## Phase 9 — Spec Kit task integration

- [ ] Keep `agent_hq` as the only scheduler and branch owner.
- [ ] Reuse `constitution.md`; do not create another project constitution.
- [ ] Evaluate Spec Kit templates for configured specification, planning,
  breakdown, and implementation tasks without making those task names or
  phases mandatory.
- [ ] Run only templates selected by accepted handoffs.
- [ ] Disable Spec Kit branch management and do not use Spec Kit Workflows as
  a second queue or state machine.
- [ ] Add a preset only when a checked-in prompt/checklist cannot express the
  required organization-specific output.

Exit: one representative configured route produces compatible artifacts
without duplicate branches, constitutions, queues, or lifecycle state.

## Phase 10 — end-to-end validation and closeout

- [ ] Test the global state document, ticket-directory enumeration, artifact
  storage, transactional replay, bounded retry, and declined mutations.
- [ ] Race concurrent claims and prove the global in-flight cap cannot be
  exceeded.
- [ ] Test ordered handoffs, duplicate delivery, gates, blocking, retries,
  queue exhaustion, unique-key rejection, containment failures, and forbidden
  queue mutation.
- [ ] Test that no task name has engine behavior and no static success chain
  remains.
- [ ] Test one ticket remains sequential while different tickets may run
  concurrently.
- [ ] Test isolated artifact transfer, result validation, patch failure,
  `.agent-hq/` stripping, and fenced stable-branch pushes.
- [ ] Test stable work PRs across implementation, tests, documentation, and
  rework using only configured tasks and ports.
- [ ] Test dispatcher fast-path wake-up and scheduled full-scan recovery.
- [ ] Test summary-present completion, summary-absent waiting, human close,
  authorized reopen, unauthorized/self-trigger no-op, and reopen refusal after
  a recorded PR is merged or closed.
- [ ] Test a mid-flight human close blocks before further collect writes,
  cancels/fences the active run, preserves queued work, and resumes exactly one
  new attempt after an authorized unblock or reopen.
- [ ] Run every check in `docs/local-testing.md`, including a live public
  sandbox ticket spanning at least two work repositories.
- [ ] Complete the documentation register below and remove superseded wording.

Exit: the completion criteria pass in a throwaway multi-repository sandbox.

## Documentation update register

Update documentation in the same phase as the behavior it describes.

| File | Required update | Phase |
|---|---|---:|
| `README.md` | Replace the fixed pipeline with the global state directory, ordered handoffs, central dispatcher, isolated jobs, stable work PRs, and engine-complete `DONE` overview | 3–7 |
| `AGENTS.md` | Replace fixed-chain and workflow-lock invariants with generic task validation, claim-time cap enforcement, transactional push/replay, credential isolation, and stable work-branch invariants | 1–6 |
| `CLAUDE.md` | Keep the same architectural and safety invariants as `AGENTS.md`; the files should differ only where their audiences require it | 1–6 |
| `constitution.md` | Add agent rules for structured control output, explicit repository targets, public-safe artifacts, and prohibition on direct queue/workflow mutation | 0, 3 |
| `docs/architecture.md` | Rewrite identity, clean bootstrap, global state layout, lifecycle including mid-flight close, claim CAS, job isolation and artifact transfer, event routing, dispatcher dedupe, approval surfaces, GitHub AW role, and Spec Kit role; record merge tracking as deliberately absent | 0–9 |
| `docs/operations.md` | Document clean-state cutover, state-directory inspection, fast-path and 15-minute recovery, claim contention, event subscriptions, operator commands, stop/resume behavior, issue close/reopen, no merge tracking, credentials, public/private dashboard behavior, and recovery | 0, 2, 4, 6–8 |
| `docs/local-testing.md` | Add clean-bootstrap validation, shared-ref contention and cap races, handoff validation, duplicate claim, two-ticket concurrency, isolated transfer, stable multi-repo PR, mid-flight close fencing, DONE/reopen, public-data, and optional AW/Spec Kit checks | 0, 2–10 |
| `docs/project-review.md` | Mark superseded findings, reassess credential isolation, intake identity, claim concurrency, stable branches, public exposure, and remaining production blockers | 0, 4–8, 10 |
| `docs/roadmap.md` | Remove parallel fan-out/join direction; defer per-issue state branches until shared-ref serialization measurably throttles post-split throughput; defer authenticated web UI until a private deployment needs one; retain only genuinely deferred task work | 0, 7, 10 |
| `docs/task-authoring.md` (new) | Document generic task fields, configured ports, handoff allowlists, control output, artifact destinations and containment, gates, budgets, terminal summary convention, and validation | 1, 3 |
| `docs/ports/README.md` | Update the port inventory and link changed contracts | 1–8 |
| `docs/ports/state-store.md` | Document the single state ref, per-ticket directories, transactional replay/CAS, claim-time cap, artifacts, events, retention, health snapshot, and failure semantics | 1, 2, 4 |
| `docs/ports/agent-session.md` | Document configured task inputs, stable work branches, structured output, three artifact payloads, and native/GitHub-AW executor boundaries | 3–5, 8 |
| `docs/ports/executor.md` | Document credential-free execution, permissions, deadlines/results, data-only transfer, devcontainer behavior, and optional GitHub AW backend | 4, 8 |
| `docs/ports/gate.md` | Add issue-comment approvals and guarded reopen while retaining PR-review code approvals, whitelist checks, and idempotency | 6 |
| `docs/ports/tracker.md` | Fix identity to engine-repository issue number; document workflow event subscriptions, pinned status, approval/reopen comments, complete and mid-flight close handling, actor filtering, and deliberately absent merge tracking | 0, 6 |
| `docs/ports/messaging.md` | Define task/queue/PR/blocker status, mid-flight stop/resume notices, honest `DONE` wording, closing summary, reopen refusal, and dedupe markers on the parent issue | 6, 7 |
| `docs/ports/qa-env.md` | Define the optional QA port and exact recorded work-repository heads; note that the task remains unwired until a binding exists | 1, 3, 5 |
| Task prompts/checklists under `tasks/` | Remove fixed-chain assumptions; emit validated handoffs and control output; declare ports and correct state/work artifact destinations | 3, 5, 9 |
| JSON Schemas under `schemas/` | Synchronize state, control output, handoff, component, repository, approval, and lifecycle descriptions/examples; delete static success chaining | 1–6 |

## Validation commands

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/agent-hq config validate
.venv/bin/agent-hq tasks validate
docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:1.7.7 -color
```

If GitHub AW is adopted:

```bash
gh aw compile --strict --no-emit
```

## Completion criteria

- [ ] A configured initial task can finish without creating an unnecessary
  downstream task or work PR.
- [ ] Optional clinical, design, architecture, backend, QA, and documentation
  work exists only when an accepted handoff selects the corresponding
  registered task; these names remain illustrative, not engine concepts.
- [ ] A multi-repository route executes configured handoffs sequentially,
  updates one PR per affected repository, passes configured gates, produces a
  closing summary, closes the issue, and reaches `DONE` without a hard-coded
  task chain.
- [ ] `DONE` is reported as engine completion and never implies that work PRs
  were merged.
- [ ] An authorized reopen resumes eligible work; unauthorized, duplicate, and
  self-authored events do nothing; a closed or merged recorded PR requires a
  new ticket.
- [ ] A non-engine issue close during active work prevents further collect
  writes, preserves pending work, and resumes exactly once after authorized
  reopen or unblock.
- [ ] Concurrent claims cannot exceed the configured in-flight cap.
- [ ] Re-delivery, restart, transactional replay, and dispatcher retries create
  no duplicate task, handoff, comment, branch, commit, or PR.
- [ ] Public Pages is rebuilt from the global state branch without browser-side
  state fetches; private mode exposes only the authenticated operator CLI.
- [ ] The execute job cannot access the engine write credential, transfer
  repository metadata, or cause collect to execute agent-supplied code.
