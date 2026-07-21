# REVISION 2 — amendments to PLAN.md

Status: proposed (PLAN.md is unchanged until these are accepted and folded in)
Date: 2026-07-21
Inputs: review round 1 (14 confirmed findings, 17 refuted) + maintainer notes R1–R7.

Each section: the decision taken, what the current code actually does, risks and
open sub-decisions, and the concrete PLAN.md edits that fall out.

---

## R1 — No PR-merge tracking: DONE when the engine finishes, reopen by comment

**Decision.** A ticket is DONE when its queue, current task, and gates are
empty and required PRs are marked ready. Merge is human and untracked. A user
can reactivate a done ticket by commenting on the parent issue.

This replaces PLAN.md Phase 7 lines 252–253 ("consume merge events…") and
completion criterion line 378, and it dissolves review finding C1 (merge
events from work repos cannot trigger engine-repo workflows). It also fixes
the zero-PR edge case for free: a product-only issue goes straight to DONE
when its queue empties.

**Issues raised by this model — decide each before Phase 7:**

1. **DONE stops meaning "shipped".** A ticket reads DONE while its PRs are
   unmerged — or closed without merge. A rejected PR is indistinguishable from
   a merged one in engine state. Dashboards and reporting must label the state
   honestly ("engine complete; merge status not tracked"), and the deviation
   ledger gets an entry superseding deviation 7 (the deferred
   `pull_request: closed` path) with this decision as its closure.
2. **Where the parent issue lives now matters twice.** Today the trigger side
   is the engine repo (`.github/workflows/intake.yml:3-5`) but the tracker
   reads/writes the "intake repo" = first project repo
   (`engine/engine.py:215-220` → `example-org/product-be`), a recorded
   mismatch (`docs/architecture.md:8-10`). Comment events have exactly the
   same cross-repo limitation as merge events: an `issue_comment` trigger only
   fires for issues in the engine repo. So either (a) parent issues live in
   the engine repo — reopen can be event-driven; or (b) they live in work
   repos — reopen must be polled, and polling comments on every DONE ticket
   forever recreates the unbounded-scan problem (C9). **Decided: (a) — parent
   issues live in the engine repo.** Reopen is event-driven, and the recorded
   intake-identity mismatch (`docs/architecture.md:8-10`) is fixed by the
   same move. Record it as the Phase 0 identity decision.
3. **Self-triggering.** The engine posts comments with the `AGENT_HQ_TOKEN`
   PAT, and PAT-authored events DO fire workflows (only `GITHUB_TOKEN` events
   are suppressed). The pinned status comment is updated on the parent issue
   (`engine/adapters/github_issues.py:74-100`), so any new `issue_comment`
   trigger must first filter out the engine's own actor/marker or the engine
   wakes itself on every status update.
4. **Reopen is a privileged command, not any comment.** "Unless a user comes
   back and comments" must mean: an explicit command (e.g. `/agent-hq reopen
   <reason>`), commenter verified against the configured approver group,
   deduped by comment id — i.e. exactly the Phase 7 approval-comment machinery
   reused, not a second parser. A bare "+1" from a drive-by commenter must not
   reactivate a ticket.
5. **Reopen semantics need one definition.** What runs after reopen? Simplest:
   reopen sets the ticket ACTIVE and enqueues the configured initial task
   (same entry point as intake, with ticket context noting the reopen reason).
   If DONE renames the ledger branch to an archive namespace (R8, C9), reopen
   renames it back — one atomic ref move each way.
6. **Issue close behavior. Decided: the engine closes the issue at DONE**
   (idempotent, keyed by event id like every other tracker side effect).
   Comments on closed issues still work and still fire events, and
   `issues: reopened` becomes a second natural reopen signal — handle both
   the reopen command and the native reopen event through the same path.

**Plan edits.**
- Phase 0: replace the merge-tracking lifecycle items with: DONE = queue,
  current task, and gates empty and required PRs marked ready; drop
  READY_FOR_MERGE as a distinct state (it collapses into DONE) or keep it as a
  display label only.
- Phase 0: record that parent issues live in the engine repo (fixes the
  `intake_repo()` mismatch; makes reopen and close event-driven).
- Phase 7: replace lines 252–253 with: close the issue at DONE (idempotent by
  event id); the reopen command — authorized-commenter check, comment-id
  dedupe, reopen → ACTIVE + initial task enqueue; treat `issues: reopened` as
  an equivalent reopen signal; add the self-trigger actor filter for the
  `issue_comment` trigger.
- Completion criteria: replace line 378 with "a done ticket can be reopened by
  an authorized comment and an unauthorized comment does nothing".
- Deviation ledger: record "merge state untracked by design; DONE = engine
  complete" superseding deviation 7's restore trigger.

---

## R2 — In-flight cap: why it breaks, and the claim-commit fix

**Decision.** The cap check moves inside the claim transaction; a rejected
non-fast-forward push is the compare-and-swap. All claims land on the single
`agent-hq-state` branch (R8.1) — exactly the shared ref the CAS needs, so no
extra machinery.

**The mechanism today.** `check_concurrency` (`engine/engine.py:99-131`)
counts *other* tickets with any run in {QUEUED, RUNNING, WAITING_GATE} from a
snapshot of all ticket states taken once per dispatch pass
(`engine/engine.py:544-545`) and allows a trigger while `other_active <
in_flight_cap` (`config/budgets.yml:3`, cap 3). The check is pure arithmetic
on a snapshot — its correctness rests entirely on dispatch passes being
serialized by the `agent-hq-state` concurrency group
(`.github/workflows/dispatch.yml:15-17`). The claim itself happens later, in
prepare: `claim_run` flips QUEUED→RUNNING and stamps a deadline
(`engine/state.py:216-240`, called at `engine/runner.py:238`).

**The race under PLAN.md Phase 4.** Per-ticket concurrency groups plus
fast-path dispatch mean two passes for *different* tickets run simultaneously.
Both snapshot state, both count 2 active tickets, both conclude "2 < 3" and
trigger — 4 in flight. Nothing downstream catches it, because claim_run only
checks its *own* run's QUEUED state, not the global count.

**Your proposal (commit on claim, commit on timeout) — assessment.** The
ingredients already exist and are commits: the claim *is* a state commit
(claim_run), release-on-completion *is* a state commit (collect's terminal
transition, `engine/runner.py:437-457`), and release-on-timeout *is* a state
commit — a killed Actions job writes nothing, so the sweep detects
deadline/lost-run expiry and marks FAILED (`engine/engine.py:380-397`, 10-min
grace at line 23). State is already "pristine" in that sense. What's missing
is not a commit — it's **atomicity between counting and claiming across
concurrent passes**.

Git gives you exactly one atomic primitive here: a rejected non-fast-forward
push to a *single ref*. The store already uses it — push fails → fetch, reset,
re-run the transaction (`engine/state.py:197-214`). So the fix that makes your
idea correct: **move the cap check inside the claim transaction, on one shared
ref.** Two concurrent claimers then serialize: the second push is rejected, it
re-reads, recounts, sees the cap reached, and declines the claim. This works
if and only if all claims land on one ref:

- **Single state branch kept (R8 recommendation):** free. Extend claim_run to
  also refuse when the global active count ≥ cap. Done.
- **Per-issue ledger branches kept:** claims for different tickets land on
  different refs — both pushes succeed, no conflict, cap exceeded. You would
  need a small dedicated single claims ref (`agent-hq/claims`: a JSON map of
  ticket → {run_id, deadline}, sweep expires stale entries) — which is a
  mini global state branch, i.e. an argument for R8.
- **Alternative (considered, rejected):** keeping only the dispatcher's
  *trigger stage* under one global concurrency group — correct but weaker
  (cap enforced at trigger, not claim), and it reintroduces a global Actions
  lock the refactor is removing.

**Plan edits.**
- Phase 4: add "the in-flight cap is enforced inside the claim transaction on
  a single ref; a refused claim exits as unclaimed and the run stays QUEUED
  for a later pass". Name the primitive: rejected non-fast-forward push with
  fetch/reset/retry (`engine/state.py:197-214`).
- Phase 4: the store's retry is promoted from safety net to concurrency
  model — bounded attempts with jittered backoff instead of today's two
  (`engine/state.py:209-210`), and a declined claim aborts without
  committing. Rewrite the CLAUDE.md/AGENTS.md invariant accordingly.
- Considered and rejected (R9.1): per-file merge/rebase conflict detection so
  different-ticket writes never collide on the ref. Transactional replay
  already achieves that outcome — on retry the change re-applies to fresh
  state, so cross-ticket writes cost one retry and never conflict — while
  per-file merge semantics would let two claims for different tickets slip
  past the in-flight cap, a cross-ticket invariant no textual merge can see.
- Phase 4: note that claim-time enforcement subsumes the dispatcher's
  advisory check; keep the dispatcher check as a cheap pre-filter.

---

## R3 — The execute→collect boundary: what is written where, and what could get missed

**Which repos get written, by whom.** All engine-side writes happen in
collect, all with `AGENT_HQ_TOKEN` (env-var credential helper, never argv):

1. **Engine repo, state branch** (per plan: the ticket's ledger branch) —
   `state.json`, `events.jsonl`, spend/health, via `GitJsonStateStore.write`
   (`engine/state.py:197-214`).
2. **Work repo** (any repo in `config.repos`, e.g. `example-org/product-be`) —
   the work branch, built from the agent worktree's diff with `.agent-hq/`
   stripped by pathspec (`engine/adapters/claude_code_headless.py:180-191`,
   `:!.agent-hq` at line 188), pushed at line 190.
3. **GitHub API** — draft PR open/reuse, reviewers requested, PR marked ready,
   issue comments (`engine/runner.py:381-410`, `385-395`).

**Why the split is currently impossible without a decision.** Prepare,
execute, and collect share one job, one runner, one disk. Everything they
exchange is a local path: `bundle.json` and `diff.patch` under
`<worktree>/.agent-hq/` (`engine/runner.py:277-284`), the agent's actual work
product as *uncommitted working-tree changes* in the worktree, and
`execute-result.json` (`engine/runner.py:306-311`). Put execute on a different
job and: prepare's bundle never arrives, collect finds no execute-result
(treated as failure/unknown-usage → ticket blocks), and the diff — the entire
deliverable — exists only on a dead runner's disk. Meanwhile the current
isolation is process-env only: PD-5 keeps the PAT out of the agent child's
env, but the agent runs on the same host as the job that holds the PAT. The
job split upgrades that to host-level isolation — *if* the transfer mechanism
doesn't hand the boundary back.

**The decision, and the checklist of things that get missed:**

- **Transfer = same-run Actions artifacts, content = data, not a repo.** Ship
  (a) the working-tree diff as a patch, (b) `.agent-hq/execute-result.json`,
  (c) declared ledger artifacts (`product.md`, `clinical.md`, `summary.md`, …)
  as a separate upload — collect path-validates these and commits them to
  `tickets/<key>/artifacts/` on the state branch, never to the work repo
  (R9.2). Never ship a `.git` directory the agent could have tampered with.
- **Collect applies, never executes.** Collect makes its own fresh clone,
  `git apply`s the patch (no hooks run), schema-validates
  `execute-result.json`, and never runs builds/tests/scripts from the patch
  content. If the patch doesn't apply, the run fails — collect does not
  improvise.
- **Execute job: zero credentials, zero permissions.** No secrets except
  `COPILOT_GITHUB_TOKEN` (deviation 9), `permissions: {}` on its
  `GITHUB_TOKEN`. Public repos (R4) mean execute's clone needs no token.
- **Path containment becomes mandatory.** `collect_outputs` today only checks
  `(worktree / path).exists()` with no normalization
  (`claude_code_headless.py:173-178`). Safe today because paths come from
  checked-in task.yml; under the handoff model, declared artifact paths are
  **agent output**. Validation must reject absolute paths, `..`, and symlink
  escapes before any path is joined onto a worktree or committed.
- **Keep the `.agent-hq/` strip** on whatever new branch-build path replaces
  `build_pr_branch`, and fence the push (`--force-with-lease` against the
  recorded head) so a zombie re-drive can't clobber the stable work branch.
- **Prepare/collect stay credentialed** (state checkout + pushes + API); only
  execute is stripped.

**Plan edits.** Add the above as explicit Phase 4 bullets (transfer mechanism,
collect-applies-never-executes, execute permissions, fenced push) and a Phase
3 validation bullet (artifact path containment).

---

## R4 — Public repos; dashboard exposure

**Decision.** Pilots run on public repositories. GitHub Pages is acceptable
there — with a public engine repo the ledger branches are world-readable
anyway, so the dashboard adds no new exposure. For any private deployment,
Pages is not used; the dashboard must be a private surface (operator CLI now;
an authenticated web view is a roadmap item with restore trigger "a private
deployment needs a web dashboard").

**One consequence to record.** Public ledger branches mean every ticket
artifact — including `clinical.md` — is public. The plan should state that
ticket content must be public-safe in this mode; that's a data-governance
gate at intake, not an engine feature.

**Plan edits.** Phase 0 decision bullet (public-repo mode, Pages allowed;
private mode → no Pages, CLI-only); reword completion criterion lines 381–382
to name the chosen mechanism; drop the ambient "without exposing private
state" claim.

---

## R5 — Dual-drive overlap: the problem, and the clean-cutover fix

**The problem in detail.** Phase 3 makes collect append accepted handoffs to
the queue; Phase 5 removes static `on_success.enqueue` only "after handoff
collection is proven". In between, one successful run drives progression
twice: collect enqueues `on_success` targets (`engine/runner.py:459-462`),
and gate approval (`engine/engine.py:414-417`) and crash re-drive
(`engine/engine.py:446-466`) do the same — while handoff application appends
its own queue entries. The two mechanisms use different identity schemes
(causal `compute_run_id` vs `<source-run-id>:<handoff-key>`), so enqueue
idempotency cannot dedupe across them: you get the same downstream task
twice, or two different downstream tasks for one run. Separately, intake
hard-reads `intake_task["on_success"]["enqueue"][0]["task"]`
(`engine/runner.py:552`) — deleting `on_success` from task.yml files makes
intake crash with a KeyError, and no plan bullet rewires it.

**Your "pristine state" instinct is the fix.** Phase 0 already prefers a
clean bootstrap — there are no live tickets that need the old mechanism kept
running. So there is no reason for a deployed overlap window at all:

- **Cut over atomically.** The change that lands handoff collection also (a)
  converts every task definition and (b) stops the engine consuming
  `on_success` for agent tasks — one commit, proven by fixtures and the Phase
  11 sandbox, not by running both mechanisms live. "Proven" (PLAN.md line
  204) becomes a test criterion, not a production-observation period.
- **Validation backstop:** a task may declare `on_success.enqueue` XOR
  `handoff.allowed`, never both — enforced in `validate_library`
  (`engine/taskdefs.py:103-121`), mirroring the existing enqueue-target
  check at lines 114-120.
- **Rewire intake:** the initial task comes from config (e.g.
  `projects.yml: initial_task`), not from reading intake's on_success chain.
  Fixes the KeyError and removes the last chain assumption from engine code.

**Plan edits.** Move "remove static on_success.enqueue" from Phase 5 into the
Phase 3 cutover; add the XOR validation bullet to Phase 3; add the intake
rewiring bullet (with the `engine/runner.py:552` citation) to Phase 5.

---

## R6 + R7 — Tasks are generic and configured; the engine knows no task names

**Decision.** `design`, `frontend`, `backend`, `product`, `qa`, `review`,
`completion`/`finalize` are all just entries in the task library — the plan's
uses of those names are illustrative placeholders. The engine must contain no
task-name special cases, and correctness comes from validation, not naming.

**How close the code already is.** Exactly two task names are hardcoded in
`engine/` today: `finalize` (`engine/runner.py:385` — closing summary +
mark-PR-ready special case) and `intake` (`engine/runner.py:482`). Everything
else is already generic.

- **Retire the `finalize` special case structurally.** Under R1, "the queue
  emptied" is an engine-level transition — hang the closing summary,
  reviewer request, mark-PRs-ready, and DONE off that transition instead of
  off a magic task id. The completion behavior becomes engine code driven by
  state, and "finalize" as a task disappears (or remains as an ordinary
  configured task with no special engine handling).
- **`intake` entry point comes from config** (R5).

**The validation set (all at validate time, not runtime):**

1. **Library:** `handoff.allowed` targets resolve to registered task ids —
   extend `validate_library` exactly like the existing enqueue-target check
   (`engine/taskdefs.py:114-120`). Requires the `schemas/task.schema.json`
   addition (it is `additionalProperties: false`, so the new key is explicit).
2. **Handoff acceptance at collect (agent output = untrusted):** target task
   registered AND in the source task's `handoff.allowed`; target repo in
   `config.repos`; count ≤ `handoff.max`; depth/loop guard; keys unique
   within one control output (duplicates fail the whole set — review finding
   C10); declared artifact paths exist and are contained (R3).
3. **Ports close the qa gap:** tasks declare their required ports in
   `components` (field exists today); add a cross-check — every declared port
   of every registered task has a binding in config — to `agent-hq config
   validate`. Today only gate adapters get this check
   (`tests/test_task_library.py:82-92`), and qa's qa-env dependency is only a
   comment (`tasks/qa/task.yml:1`), invisible to every validator. Once qa
   declares `components: {qa-env: default}` (plus the `qa-env` key added to
   `schemas/components.schema.json`), an unbound adapter fails config
   validation — so qa simply cannot be registered until its adapter exists.
   This resolves review finding C8 without building the adapter now.
4. **Tests follow:** `tests/test_task_library.py`'s hardcoded `P0_CHAIN`
   graph pins are replaced by: library loads, handoff allowlists resolve,
   gate/port bindings resolve, zero concrete adapter names. (Pre-existing gap
   found in passing: the forbidden-adapter-names tuple at
   `tests/test_task_library.py:54` does not include `copilot-cli` — add it
   regardless of this refactor.)

**Plan edits.** Rewrite Phase 5 as "convert the library to the generic
handoff model": disposition line for every existing task (converted /
absorbed into the queue-empty transition / removed); replace the
placeholder-name bullets (lines 207–210) with the validation set above;
reword the Phase 5 exit and completion criteria to be config-generic ("an
issue whose handoffs route only through registered tasks…" — no named tasks).
QA leaves the completion criteria (criterion becomes "…passes gates and
reaches DONE"); qa stays in the library as an unwired P1 task behind the
port-binding validation.

---

## R8 — Carried findings (not covered by the notes above)

1. **Decision 2 — per-issue ledger branches (review's strategic finding).
   Decided: cut — the single global state branch remains.** The evidence
   points one way: the only recorded problem with the single branch is the
   120-minute lock hold, fixed by the Phase 4 job split independent of branch
   layout; state files are already per-ticket (`engine/state.py:132-137`);
   R2's cap fix is free on one branch and needs an extra global claims ref on
   many; C9 (every scan reads every branch ever created) and C11 (health
   aggregation has no producer) exist *only* in the per-branch design. Cutting
   Decision 2 deletes most of Phase 2, the Phase 0/11 migration items, and the
   health-aggregation machinery. Move per-issue ledgers to `docs/roadmap.md`
   with restore trigger "single-branch write serialization measurably
   throttles throughput after the job split". Phase 2 shrinks to: extend
   `GitJsonStateStore` for the new state document (queue, handoffs,
   approvals, lifecycle fields) and the per-ticket `artifacts/` directory.

   State and artifacts live where they do today — the single
   orphan `agent-hq-state` branch on the engine repo, per-ticket by
   directory (`engine/state.py:132-141`); the plan's per-branch ledger
   contents become per-directory contents:

   ```text
   agent-hq-state (orphan branch, engine repo)
     tickets/<ticket-key>/
       state.json          # queue, current task, handoffs, approvals, lifecycle
       events.jsonl        # per-ticket event log
       artifacts/          # orchestration artifacts (product.md, clinical.md, …)
     health/latest.json    # unchanged (C11 disappears)
   ```

   Work-repo artifacts are unaffected (stable `agent-hq/<ticket-key>` branch
   per Phase 6). Enumeration = one shallow fetch + list `tickets/*/` (kills
   C9); archive/hide = a status filter, no ref renames; reopen = flip
   `state.json` to ACTIVE; the R2 claim-CAS needs no extra ref. Costs:
   cross-ticket writes contend on one ref (absorbed by the push-CAS retry;
   seconds-long holds after the Phase 4 job split) and one branch's history
   grows with all tickets (shallow fetch keeps checkout cost flat).
2. **Moot under the R8.1 decision:** findings C9 (unbounded branch scans)
   and C11 (health events with no producer) dissolve with the single branch —
   enumeration is a directory listing on one checkout, and
   `health/latest.json` keeps working as-is.
3. **CLAUDE.md** joins the documentation register (lockstep with AGENTS.md —
   the two differ only in their title lines) so the refactor doesn't leave it
   prescribing the old architecture (C12).
4. **Operator commands & BLOCKED (C13):** expand the Phase 8 checkbox into
   per-command semantics — retry = `reenqueue_same` at attempt+1 for
   FAILED/BLOCKED terminal runs; reconcile = the sweep scoped to one ticket;
   block/unblock = lifecycle writes with an operator event, unblock → ACTIVE
   with queue intact; operators cannot edit pending queue entries (that stays
   the deferred feature). Add BLOCKED enter/exit edges to the lifecycle
   diagram.
5. **Cut the `superseded` handoff event type (C14)** — nothing in the plan can
   emit it; it returns with human queue editing.

---

## R9 — Fold checklist (review round 3, all decided)

The re-review of the amended plan surfaced nine follow-on issues. Items 1 and
2 are folded into R2 and R3 above; the rest are decided here.

1. **State-write retries (folded into R2).** Transactional replay stays and
   is promoted from safety net to concurrency model: bounded attempts with
   jittered backoff, declined claims abort without committing, invariant
   docs rewritten. Per-file merge/rebase conflict detection rejected — see
   the note in R2.
2. **Ledger artifacts (folded into R3).** Documents destined for the state
   branch are a third named transfer payload; collect commits them to
   `tickets/<key>/artifacts/`.
3. **Queue-empty completion.** Task libraries are authored so the last task
   in a ticket's queue is a finalize-style *configured* task whose declared
   ledger artifact is the closing `summary.md` — the engine still knows no
   task names; it checks for the artifact, not the task. When any pass
   (collect, gate resolution, or sweep) observes the queue, current task,
   and gates empty on an ACTIVE ticket — keyed
   `{ticket}:{terminal-run-id}:done`, no-op otherwise:
   - `summary.md` present → post it as the closing comment, mark required
     PRs ready, close the issue, set DONE.
   - `summary.md` absent → update the pinned comment ("tasks complete, no
     closing summary — awaiting human input") and take no terminal action;
     the check re-runs idempotently on later passes. A human resolves it by
     closing the issue themselves (a non-engine `issues: closed` event is
     accepted as "human declared done") or by re-driving a task that
     produces the summary.
4. **Reopen made safe.** Reopen is a lifecycle-guarded transition: it acts
   only on a DONE ticket, so the `issues: reopened` echo caused by the
   engine's own PAT reopening the issue finds the ticket already ACTIVE and
   no-ops. The self-actor filter covers `issues` events as well as
   `issue_comment`.
5. **Reopen after work branches are gone.** If a reopen arrives and any
   recorded work PR is merged or closed (its branch gone), the engine does
   not resume work: it posts a comment — deduped by the triggering comment
   id — stating it cannot work on this ticket further (open a new ticket for
   follow-up work) and leaves the ticket DONE. Reopen is honored only when
   every recorded work PR is still open, or none exist (e.g. a product-only
   ticket). Phase 6's one-branch/one-open-PR rule stays intact with no
   branch-recreation machinery.
6. **Cutover sequencing.** Library conversion merges into the Phase 3 atomic
   cutover; the phase tracker rows and dependencies are re-sequenced to
   match. `on_success.enqueue` is deleted from the task schema outright —
   nothing consumes it post-cutover — and the transitional XOR check is
   dropped along with the field.
7. **Lifecycle remnants.** The target-lifecycle diagram is rewritten: queue/
   gates empty → DONE + issue closed; reopen edge (guarded per R9.4/R9.5);
   BLOCKED enter/exit edges; no READY_FOR_MERGE, no merge-driven DONE.
   Phase 7's READY_FOR_MERGE bullet and Phase 11's merge-transition test are
   replaced with queue-empty-DONE / close / reopen tests.
8. **Cut-feature remnants.** Documentation-register rows for merge tracking,
   per-issue ledger refs, and repo-qualified identity are rewritten; Phase 8
   enumeration bullets and the layout health paragraph are replaced with
   directory-listing wording. The canonical ticket key becomes the
   engine-repo issue number — ref-safe by construction, shortening every
   branch and directory name.
9. **Approval-append idempotency.** The approval-time queue append for gated
   handoffs is keyed by the same handoff identity
   (`<source-run-id>:<handoff-key>`), so a re-delivered approval is a no-op.

## Decided (2026-07-21)

- R2: cap check inside the claim transaction, rejected push as CAS.
- R1.2: parent issues live in the engine repo.
- R1.6: the engine closes the issue at DONE; `issues: reopened` and the
  authorized reopen comment are equivalent reopen signals.
- R8.1: per-issue ledger branches are cut. The single global `agent-hq-state`
  branch remains the state store, tickets as directories; per-issue ledgers
  move to `docs/roadmap.md` with restore trigger "single-branch write
  serialization measurably throttles throughput after the job split".
- R9 (round 3): all nine fold-checklist items decided as recorded above.

## Open questions for the maintainer

None — all review-round-2 questions are decided.
