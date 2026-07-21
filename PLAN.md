# Plan — sequential issue orchestration

Status: proposed
Last updated: 2026-07-21

## Outcome

Refactor `agent_hq` from a fixed task chain backed by one global state branch
into a generic, handoff-driven engine with:

- one parent GitHub issue per body of work;
- one state-only orchestration branch per issue;
- one ordered task queue and at most one active task per issue;
- one stable branch and PR per issue in each affected work repository;
- explicit, validated task handoffs;
- one central dispatcher workflow;
- issue-based orchestration approvals and PR-based code approvals;
- optional GitHub Agentic Workflows execution hardening;
- optional Spec Kit templates inside tasks, without a second scheduler.

`docs/roadmap.md` remains the backlog for unrelated deferred features. This
file is the source of truth for the refactor.

## Decisions

1. **Sequential within an issue.** Remove the planned dependency DAG,
   fan-out/fan-in, and task reordering. Different issues may run concurrently.
2. **One issue ledger branch.** Store issue state on an orphan
   `agent-hq/tickets/<canonical-ticket-key>` branch in the engine repository.
3. **One work branch per issue and repository.** Reuse
   `agent-hq/<canonical-ticket-key>` for implementation, QA fixes, tests, and
   documentation in each affected repository.
4. **Commits are checkpoints, not triggers.** Commit state first, then send an
   explicit `repository_dispatch` wake-up. The 15-minute cron is recovery.
5. **The dispatcher is central.** Keep one `dispatch.yml` on `main`; do not
   create a dispatcher workflow per issue branch.
6. **Handoffs are untrusted proposals.** The engine validates them against the
   source and target task definitions before changing the queue.
7. **No direct agent privileges.** Agents cannot choose workflows, secrets,
   permissions, tools, budgets, or arbitrary repositories.
8. **Approvals follow the artifact.** Product, clinical, and design approvals
   happen on the parent issue; code approval happens on work-repository PRs.
9. **No Codespaces automation.** Actions may reuse `.devcontainer` through
   `devcontainers/ci`; they do not create or manage Codespaces.
10. **No browser-side state fetches.** Pages renders a server-side snapshot;
    browsers do not fetch private state through `raw.githubusercontent.com`.
11. **GitHub AW is an execution adapter, not the scheduler.** It may replace
    the unsafe agent-job boundary after the core handoff model works.
12. **Spec Kit is a task methodology, not the scheduler.** Use its templates
    selectively; `agent_hq` owns sequencing, branches, state, and gates.

## Target lifecycle

```text
Issue labeled for intake
  -> create agent-hq/tickets/<ticket-key>
  -> queue product
  -> central dispatcher claims product
  -> task runs in an ephemeral execution environment
  -> collect validates artifacts and control output
  -> commit issue ledger and work-repository changes
  -> apply gate or append ordered handoffs
  -> explicitly wake the dispatcher
  -> repeat one task at a time
  -> queue/gates empty: READY_FOR_MERGE
  -> all required work PRs merged: DONE
```

## State and branch layout

```text
agent_hq repository
  main
    engine, schemas, task definitions, workflows, docs

  agent-hq/tickets/<ticket-key>        # orphan issue ledger
    state.json
    events.jsonl
    artifacts/
      product.md
      clinical.md
      design.md

work repository
  agent-hq/<ticket-key>                # stable work branch
    implementation, tests, QA fixes, docs
  PR: agent-hq/<ticket-key> -> configured base branch
```

Global adapter health will be derived from the latest adapter-health events
across issue ledgers. Do not introduce a second mutable global state branch
unless branch enumeration is measured to be insufficient.

## Phase tracker

| Phase | Scope | Status | Depends on |
|---|---|---|---|
| 0 | Freeze contracts and migration choice | Pending | — |
| 1 | Issue-ledger schemas and models | Pending | 0 |
| 2 | Per-issue Git state store | Pending | 1 |
| 3 | Handoff contract and ordered queue | Pending | 1, 2 |
| 4 | Central dispatcher and task-run workflow | Pending | 2, 3 |
| 5 | Task library conversion | Pending | 3, 4 |
| 6 | Stable work branches and PRs | Pending | 2, 4 |
| 7 | Approvals and ticket lifecycle | Pending | 3, 5, 6 |
| 8 | Dashboard and operations | Pending | 2, 4, 7 |
| 9 | GitHub Agentic Workflows evaluation | Pending | 3, 4, 6 |
| 10 | Spec Kit task integration | Pending | 5, 6 |
| 11 | Migration, end-to-end validation, and closeout | Pending | 1–10 |

## Phase 0 — freeze contracts and migration choice

- [ ] Define a ref-safe canonical ticket key. It must include the source
  repository when tickets can originate from multiple repositories.
- [ ] Define branch names and base-branch selection for every configured work
  repository.
- [ ] Inventory any live data on `agent-hq-state`.
- [ ] Prefer a clean bootstrap if no production tickets depend on that branch;
  otherwise write and test a one-time migration before changing schemas.
- [ ] Record the exact issue lifecycle states: `ACTIVE`, `BLOCKED`,
  `READY_FOR_MERGE`, and `DONE`.
- [ ] Record the approval commands and configured approver groups.

Exit: naming, lifecycle, and migration behaviour are decided before schema or
branch code changes.

## Phase 1 — issue-ledger schemas and models

- [ ] Change the ticket state schema to include `current`, ordered `queue`,
  `history`, work-repository records, handoffs, approvals, and lifecycle state.
- [ ] Add a structured task control-output schema with exactly three outcomes:
  `handoff`, `complete`, and `blocked`.
- [ ] Define each handoff with a stable `key`, registered target `task`, reason,
  optional target repository, and declared input artifacts.
- [ ] Derive handoff identity from `<source-run-id>:<handoff-key>` rather than
  list position.
- [ ] Add proposed, accepted, rejected, and superseded handoff event types.
- [ ] Store repository branch, PR reference, current head, base branch, and
  merge status in the issue ledger.
- [ ] Keep schemas and dataclasses synchronized and update pinned model tests.

Exit: invalid state and handoff documents fail locally with actionable errors.

## Phase 2 — per-issue Git state store

- [ ] Create an orphan `agent-hq/tickets/<ticket-key>` branch idempotently at
  intake.
- [ ] Refactor `GitJsonStateStore` to open one issue ledger branch at a time.
- [ ] Store `state.json`, `events.jsonl`, and `artifacts/` at the branch root.
- [ ] Add branch enumeration for `refs/heads/agent-hq/tickets/*`.
- [ ] Make reads, commits, push retries, and re-delivery idempotent.
- [ ] Keep completed branches as the initial audit/archive mechanism.
- [ ] Aggregate latest adapter health from issue events at read/render time.
- [ ] Keep engine code and workflows on `main`; never merge issue-ledger
  branches into `main`.

Exit: two issue branches can be created, updated, read, and enumerated without
sharing mutable state files.

## Phase 3 — handoff contract and ordered queue

- [ ] Require every successful agent task to write control output under
  `.agent-hq/`; exclude that runner metadata from work-repository commits.
- [ ] Extend task definitions with `handoff.allowed` and `handoff.max`.
- [ ] Validate target task, repository, artifacts, count, depth, loop guard,
  budget, and source allowlist before accepting a handoff.
- [ ] Never accept tools, permissions, secrets, prompts, budgets, or raw
  workflow names from agent output.
- [ ] Append accepted handoffs to the queue in emitted order.
- [ ] Permit at most one `RUNNING` or `WAITING_GATE` task per issue.
- [ ] Do not allow agents to mutate accepted, running, or completed queue
  entries. Defer human queue editing until someone needs it.
- [ ] Store gated handoffs as pending and append them only after approval.
- [ ] Make handoff application and crash re-drive idempotent.

Exit: duplicate collect/re-drive produces one handoff and one queued task.

## Phase 4 — central dispatcher and task-run workflow

- [ ] Keep one `.github/workflows/dispatch.yml` on `main`.
- [ ] Preserve its scheduled `*/15` cron, manual dispatch, and
  `agent-hq-dispatch` repository event.
- [ ] Add an optional ticket key to the repository-dispatch payload for a
  narrow fast-path scan; a scheduled or unscoped run scans every active issue
  branch.
- [ ] Claim at most one ready task per issue during a dispatcher pass.
- [ ] Pass ticket key and run ID to the stable task-run workflow.
- [ ] Keep the layered duplicate defenses: queued-state check, active GitHub
  workflow lookup, per-run concurrency group, and atomic claim.
- [ ] Replace the global `agent-hq-state` concurrency group with per-ticket
  concurrency for state-changing work.
- [ ] Split prepare, execute, and collect so the agent execution job has no
  engine write credential.
- [ ] Commit state before sending a wake-up; retain cron as recovery when the
  wake-up fails.
- [ ] Re-drive a claimed/lost workflow after its grace period without
  duplicating side effects.

Exit: one issue stays sequential, two issues may progress concurrently, and
duplicate dispatch requests execute the task once.

## Phase 5 — convert the task library

- [ ] Rename or replace `spec` with the initial `product` task.
- [ ] Remove static `on_success.enqueue` after handoff collection is proven.
- [ ] Replace exact global-chain validation with handoff-allowlist validation.
- [ ] Make product hand off only justified work: clinical, design,
  architecture, breakdown, frontend, backend, QA, documentation, or another
  registered task.
- [ ] Default backend work to absent; require evidence that existing APIs or
  configuration cannot satisfy the acceptance criteria.
- [ ] Do not create empty no-change clinical or architecture artifacts; retain
  the decision and reason in product output/handoff history.
- [ ] Keep breakdown for implementation work without forcing a formal
  architecture handoff.
- [ ] Update prompts and checklists to produce the structured control output.

Exit: product-only and frontend-only fixtures route correctly without a
hard-coded lifecycle.

## Phase 6 — stable work branches and PRs

- [ ] Create `agent-hq/<ticket-key>` once per affected work repository from its
  configured base branch.
- [ ] Reuse the branch for every later task touching that repository.
- [ ] Open at most one normal work PR per issue per repository.
- [ ] Commit orchestration artifacts to the issue ledger unless a task names a
  work-repository destination.
- [ ] Commit implementation, tests, QA fixes, and documentation to the stable
  work branch they modify.
- [ ] Preserve the recorded branch head through review and rework; never fall
  back to `main` after a failed downstream task.
- [ ] Support a QA task reading the exact recorded heads of all required work
  repositories, sequentially after their changes are present.
- [ ] Mark required PRs ready when the task queue completes; keep merge human.

Exit: downstream QA/docs commits remain in the mergeable PRs and one issue
never creates duplicate PRs in a work repository.

## Phase 7 — approvals and ticket lifecycle

- [ ] Add an issue-comment gate adapter for product, clinical, design, and
  other orchestration approvals.
- [ ] Require an explicit decision command containing the run/task ID.
- [ ] Verify the commenter against the configured approver group.
- [ ] Record decision, actor, source comment, and time before advancing the
  queue.
- [ ] Continue using work-repository PR reviews for code approval.
- [ ] Keep the pinned issue comment synchronized with current task, pending
  gate, ordered queue, blockers, and work PRs.
- [ ] Set `READY_FOR_MERGE` only when queue, current task, and gates are empty.
- [ ] Consume merge events for every required PR and set `DONE` only after all
  are merged.

Exit: an unauthorized comment cannot advance a task, and merge state is not
confused with agent-task completion.

## Phase 8 — dashboard and operations

- [ ] Make the Pages job enumerate issue branches server-side.
- [ ] Render one consistent static snapshot without browser-side private-state
  fetches.
- [ ] Aggregate adapter health from the latest issue-ledger events.
- [ ] Hide completed issues from the default view without deleting branches.
- [ ] Refresh after state changes and retain the existing scheduled refresh as
  recovery.
- [ ] Add operator commands for listing, inspecting, blocking, retrying, and
  reconciling one ticket key.

Exit: the dashboard and operator CLI agree with the issue branches after
re-delivery, blocking, approval, and merge.

## Phase 9 — GitHub Agentic Workflows evaluation

- [ ] Keep the core engine independent of GitHub AW.
- [ ] Spike one task type as an `agent-session`/executor backend using a
  compiled GitHub Agentic Workflow.
- [ ] Verify run ID input, read-only agent execution, network policy, artifact
  transfer, threat detection, and a trusted structured-output application job.
- [ ] Implement handoff/patch application as a safe output or a narrowly scoped
  trusted collect command; never give the agent the engine write credential.
- [ ] Verify whether target-repository tests can use the existing devcontainer;
  do not assume GitHub AW automatically runs `.devcontainer`.
- [ ] Adopt `gh aw compile --strict` and commit source plus lock workflow only
  if the spike meets the execution and debugging requirements.
- [ ] Add `agent-hq workflows build --check` only if task types genuinely need
  different static workflow envelopes.

Exit: either GitHub AW is a proven adapter with a documented fallback, or the
three-job native Actions boundary is retained with the rejection reason.

## Phase 10 — Spec Kit task integration

- [ ] Keep `agent_hq` as the only scheduler and branch owner.
- [ ] Reuse the existing `constitution.md`; do not create a second conflicting
  project constitution.
- [ ] Evaluate Spec Kit templates for `product` (`specify`), architecture
  (`plan`), breakdown (`tasks`), and repository implementation.
- [ ] Use only the phases selected by handoffs; do not run the complete Spec
  Kit lifecycle for every issue.
- [ ] Disable or avoid Spec Kit's optional Git branch management.
- [ ] Do not use Spec Kit Workflows as a second queue/state machine.
- [ ] Add a preset only when a checked-in prompt/checklist cannot express the
  required organization-specific output.

Exit: one representative ticket produces compatible artifacts without
duplicate branches, constitutions, queues, or lifecycle state.

## Phase 11 — migration, end-to-end validation, and closeout

- [ ] Run the clean bootstrap or tested one-time migration selected in Phase 0.
- [ ] Test issue-branch creation, ref safety, enumeration, idempotent commits,
  and completed-branch retention.
- [ ] Test ordered handoffs, duplicate delivery, gates, blocking, retries,
  queue exhaustion, and forbidden queue mutation.
- [ ] Test that tasks for one issue never overlap and two different issues can
  run concurrently.
- [ ] Test stable work branches/PRs across implementation, QA, documentation,
  and rework.
- [ ] Test dispatcher fast-path wake-up and scheduled full-scan recovery.
- [ ] Test `READY_FOR_MERGE` and merge-driven `DONE` transitions.
- [ ] Run every check in `docs/local-testing.md`, including a live sandbox
  ticket spanning at least two work repositories.
- [ ] Complete the documentation register below and remove superseded wording.

Exit: the completion criteria pass in a throwaway multi-repository sandbox.

## Documentation update register

Update documentation in the same phase as the behaviour it describes; do not
defer all documentation until Phase 11.

| File | Required update | Phase |
|---|---|---:|
| `README.md` | Replace the fixed pipeline and global-state description with the issue-ledger, ordered-handoff, central-dispatcher, and stable-work-PR overview | 5–8 |
| `AGENTS.md` | Replace global-state/fixed-chain invariants; add handoff validation, per-ticket concurrency, issue-ledger, and stable work-branch invariants | 1–7 |
| `constitution.md` | Add agent rules for structured control output, explicit repository targets, and prohibition on direct queue/workflow mutation | 3, 5 |
| `docs/architecture.md` | Rewrite flow, state layout, branch ownership, dispatcher dedupe, approval surfaces, task/workflow/devcontainer boundaries, GitHub AW role, and Spec Kit role | 1–10 |
| `docs/operations.md` | Document issue-branch creation, dispatcher fast path and 15-minute recovery, per-ticket inspection/retry, approval commands, PR merge tracking, credentials, and recovery | 2, 4, 7–9 |
| `docs/local-testing.md` | Add issue-ledger tests, duplicate dispatch/claim checks, two-issue concurrency, stable multi-repo PR tests, lost-run recovery, devcontainer/Codespaces distinction, and optional AW/Spec Kit checks | 2–11 |
| `docs/project-review.md` | Mark superseded findings/fixes, reassess credential isolation, intake identity, global locking, disconnected descendant branches, and remaining production blockers | 4, 6, 9, 11 |
| `docs/roadmap.md` | Remove the parallel fan-out/join direction, update task-library activation notes, and retain only work genuinely deferred after this refactor | 0, 11 |
| `docs/task-authoring.md` (new) | Document task definition fields, handoff allowlists, control-output examples, artifact destinations, gates, budgets, and local validation | 3, 5 |
| `docs/ports/README.md` | Update the port inventory and link the changed contracts | 2–9 |
| `docs/ports/state-store.md` | Replace the global branch contract with per-issue ledger refs, enumeration, atomic claims, events, retention, and failure semantics | 1, 2 |
| `docs/ports/agent-session.md` | Document issue-ledger inputs, stable work branches, structured outputs, and the native/GitHub-AW executor boundary | 3, 6, 9 |
| `docs/ports/executor.md` | Document read-only execution, deadline/result contract, devcontainer behaviour, and optional GitHub AW backend | 4, 9 |
| `docs/ports/gate.md` | Add issue-comment orchestration approvals and retain PR-review code approvals, including whitelist and idempotency rules | 7 |
| `docs/ports/tracker.md` | Add canonical repo-qualified issue identity, pinned status projection, approval-comment reads, and merge-event handling | 0, 7 |
| `docs/ports/messaging.md` | Define current-task/queue/PR/blocker status updates and dedupe markers on the parent issue | 7 |
| `docs/ports/qa-env.md` | Define QA inputs as the exact recorded heads of all required work repositories | 6 |
| Task prompts/checklists under `tasks/` | Replace fixed-chain assumptions with structured handoff output and correct ledger/work-repository artifact destinations | 5, 6, 10 |
| JSON Schemas under `schemas/` | Keep descriptions/examples synchronized with the issue ledger, queue, handoff, repository, approval, and lifecycle contracts | 1–7 |

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

- [ ] A product-only issue can finish without creating an unnecessary task.
- [ ] A frontend-only issue creates no clinical, architecture, or backend task.
- [ ] A clinical frontend/backend issue executes handoffs sequentially,
  updates one PR per affected repository, passes gates and QA, and reaches
  `READY_FOR_MERGE` without a hard-coded task chain.
- [ ] Merging every required work PR moves the parent issue to `DONE`.
- [ ] Re-delivery, restart, and dispatcher retries create no duplicate task,
  handoff, comment, branch, commit, or PR.
- [ ] The dashboard is rebuilt from issue-ledger branches without exposing
  private state or credentials to browsers.
- [ ] The agent execution job cannot access the engine write credential.
