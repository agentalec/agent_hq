# Architecture (P0)

## Flow

1. A GitHub issue labeled `hq:intake` is the intended entry point. `intake.yml`
   (triggered on issue open/label in the engine repo) calls
   `engine.runner.intake_ticket` -- engine entry logic, not a task file. It
   reads the ticket via the `tracker` port, checks eligibility from
   `config.projects["intake"]`/`["public"]`/`["public_safe_label"]` (rejecting
   before any state/artifact write), records the ticket on the state branch,
   and enqueues `config.projects["initial_task"]` (`spec` in the pilot config)
   with the root run's repo resolved from the ticket.
   Cross-repository event delivery and repo-qualified ticket identity are not
   implemented; this is a pilot blocker in `docs/project-review.md`.

   The parent issue's repository is a configured value,
   `config.projects["engine_repo"]` (PLAN.md decision 3) — distinct from the
   work repositories tasks target — and that issue number is the ticket's
   canonical key. Every tracker/messaging call that needs the engine's own
   issue tracker routes through `engine.engine.intake_repo(config)`, which
   returns `engine_repo`; `resolve_target_repo` separately selects a work
   repo for code and PRs.
2. State lives on an orphan `agent-hq-state` branch (`engine.state.GitJsonStateStore`,
   plain JSON files, one fixed implementation per PD-7 — not a port, no
   adapter to swap). All state-writing workflows share the
   `agent-hq-state` Actions `concurrency` group (`cancel-in-progress: false`),
   so writes serialize instead of racing (D5).
3. `dispatch.yml` runs on a 15-minute schedule (plus `repository_dispatch`/
   `workflow_dispatch`). It sweeps the state store for queued runs, gate
   timeouts, and orphaned/stale running work, then triggers `run.yml` via
   `workflow_dispatch` for anything ready to execute.
4. `run.yml` runs a task's three phases as three ISOLATED Actions jobs
   (`scripts/run-phases.sh`, hardening plan Task 12): **prepare**
   (credentialed; claims the run, restores any handoff `input_artifacts`
   from the source run's ledger, and writes the prompt bundle to
   `bundle.json` -- no work-repo clone) -> **execute** (credential-free,
   `permissions: {}`, only `COPILOT_GITHUB_TOKEN`; clones the public repo,
   spawns `copilot -p "<prompt>" --no-ask-user --model
   claude-sonnet-4.5` (no `-s`: silent mode would suppress the session
   trailer the run's spend is parsed from), and emits a work patch, the normalized
   `execute-result.json`, `control.json`, and staged declared/input
   artifacts, all as a transported Actions artifact -- runs inside the
   project devcontainer, the only phase that needs the `copilot`/`claude`
   CLI) -> **collect** (credentialed; parses `execute-result.json` first --
   on failure it stops there; on success it validates `control.json`
   against the three control outcomes, fresh-clones the repo, `git apply`s
   the work patch, lands it on the ticket's stable per-issue branch, opens
   a PR only when the task declares `opens_pr` and none is already
   recorded, persists declared outputs to this run's ledger namespace, and
   records adapter health).
5. A task's own transition is driven entirely by its validated
   `.agent-hq/control.json` outcome (`schemas/control.schema.json` --
   "Control outcomes" below), not a static `on_success` list. A `handoff`
   outcome on a task with a `gates.post` entry (e.g. `spec`'s
   `spec-approval`) stores the proposed handoffs pending and stops the run
   at `WAITING_GATE` until the gate's adapter reports `APPROVED`;
   `dispatch.yml`'s sweep polls gate status, applies the stored handoffs on
   approval, and completes the run. Merge is always a human action — no task
   auto-merges a PR.
6. `pages.yml` renders a static dashboard (ticket/run state table, spend,
   waiting-on-humans list) after intake/dispatch/collect and on a `*/5`
   schedule.

## Where work and memory live

The issue, agent workspace, PR, and state branch have different jobs:

| Concern | Location | Durable? | Role |
|---|---|---:|---|
| Request and human conversation | GitHub issue in the engine repo (`config.projects["engine_repo"]`) | Yes | Control plane: intake, status, escalation, gate approvals/reopen, and closing summary |
| Active agent workspace | Target-repo clone at `<workdir>/_target/<run_id>` inside execute's credential-free devcontainer job | No | Where the agent reads, edits, and tests during one run; never transferred (`.git` stays behind) |
| Job-boundary transport | `_prepare/<run_id>/bundle.json`+`inputs/`, `_execute/<run_id>/{execute-result.json,control.json,work.patch,outputs/}` | No | Plain-file Actions artifacts (`actions/upload-artifact`/`download-artifact`, no custom tar) handing prepare -> execute -> collect their inputs/outputs |
| Produced work | `agent-hq/<issue-number>` branch in the target repo (one per repo per ticket, reused across every task and rework attempt) | Yes | Canonical, ticket-stable output history; each task/rework bases on the branch's recorded head, never the base branch again |
| Human review | Draft PR in the target repo, only when a task declares `opens_pr: true` (create-or-get: at most one per repo per ticket) | Yes | Approval/review surface; not the engine state store |
| Orchestration memory | Orphan `agent-hq-state` branch in the engine repo | Yes | Canonical ticket, run, event, gate, artifact, cost, and adapter-health state |
| Dashboard | GitHub Pages projection of the state branch | Rebuildable | Read-only operator view, not a source of truth |
| Agent session/conversation memory | None in P0 | No | A retry starts a new process and clone; there is no saved LLM session to resume |

Every successful task's collect phase lands its result on
`agent-hq/<issue-number>` in its resolved work repo (`run.repo`) -- a plain
fast-forward push, since every attempt is built on the branch's own
recorded head (`ticket.work_repos[].recorded_head`). A PR is more selective:
only `implement` opens one, because it declares `opens_pr: true`, and only
the first task to do so on a given repo/ticket actually calls
`open_draft_pr` -- every later task reuses the recorded `pr_ref`. Every
other task -- including `spec` and `arch-approval`, which carry human gates
-- still lands on that same durable branch with no separate PR of its own;
their gates are authorized comments on the parent engine issue
(`github-issue-comment`, `docs/ports/gate.md`), not PR reviews. `finalize`
writes `specs/<ticket>/summary.md` and emits `complete`; queue-empty
completion (`engine.engine._complete_if_queue_empty`) is what then posts the
closing summary to the issue, marks every recorded work-repo PR ready
(`ticket.work_repos[].pr_ref` -- i.e. `implement`'s PR, if any), and closes
the issue. Merge remains human-only.

The state branch is the engine's durable memory, stored as:

- `tickets/<id>/state.json` — current ticket and run snapshots, including
  bindings, deadlines, artifacts, output commits, `pending_handoffs`, and
  PR/gate references.
- `tickets/<id>/artifacts/<run_id>/` — the ledger: each run's declared
  `outputs.artifacts` (plus any inherited artifact an accepted handoff
  forwards), namespaced by the producing run so a sibling handoff can never
  overwrite another run's snapshot.
- `tickets/<id>/events.jsonl` — append-only lifecycle, handoff
  (`proposed`/`accepted`/`rejected`), and rework events.
- `health/latest.json` — latest adapter health observations.

The next task reconstructs its context from the GitHub issue, its inlined task
instructions, the parent output commit/diff, checked-in artifacts such as
`specs/<ticket>/*.md`, and any rework event. GitHub Actions logs are useful
operational evidence, but they are not used as memory. P0 has no database,
vector store, transcript archive, or session checkpoint/resume mechanism.

## Lifecycle

Frozen by Phase 0 of the hardening plan
(`.hyperclaude/plans/20260721-2056-harden-the-existing-plan-at.md`, Task 1).
The control-outcome/handoff mechanics, gate-approval completion, queue-empty
completion, and the isolated-job/stable-per-issue-branch cutover below are
**live** as of Tasks 9 and 12; the mid-flight close/operator-block/reopen
edges are still **planned** (Tasks 14, 16, 18 of that plan) and marked as
such below.

A ticket carries one of three lifecycle states (`engine.models.TicketStatus`):

| State | Meaning |
|---|---|
| `ACTIVE` | Queued, running, or waiting-gate work remains. |
| `AWAITING_MERGE` | The engine is finished — summary posted, work PRs marked ready — but a recorded PR is still open. The issue stays **open**; the sweep watches the PRs. |
| `BLOCKED` | A non-engine issue close, an operator `block`, or a work PR closed unmerged interrupted active work; the queue and any pending gate are preserved for resume. |
| `DONE` | Every recorded work PR merged (or the ticket recorded none) — see below. |

A ticket also reaches `BLOCKED` **today** whenever a run's own accounting
says it must stop: a `blocked` control outcome, a rejected/expired gate, a
failed `apply_handoffs` guard, retries exhausted, or a tripped loop guard/
budget cap (`engine.engine._block_ticket` and its callers). The edges below
are the hardening plan's dedicated close/reopen machinery layered on top of
that:

- **[planned, Task 16]** `ACTIVE` -> `BLOCKED` — a non-engine issue close
  with work/gate/current remaining, or an operator `block`: the state fence
  commits first (terminalize any `RUNNING` run as `interrupted_run_id`; a
  `WAITING_GATE` run is left as-is), then the Actions run is cancelled and
  the pinned comment updated.
- **[planned, Tasks 14/16/18]** `BLOCKED` -> `ACTIVE` — an authorized
  `/agent-hq reopen <reason>` command, the native `issues: reopened` event,
  or operator `unblock`: retains the queue and pending gates, and enqueues
  attempt+1 of any `interrupted_run_id`.
- **[live]** `ACTIVE` -> `AWAITING_MERGE` — queue, current, and pending gates
  are exhausted and the terminal run's own recorded artifacts include the
  closing summary: the summary posts and every recorded work PR is marked
  ready (`engine.engine._complete_if_queue_empty`). The issue stays **open**.
  Engine-complete is not ticket-complete while a human still has to merge:
  closing here (the original Task 9 behaviour, reversing PLAN.md decision 12)
  told the tracker "done" over unreviewed code, and a reviewer arriving later
  found a closed ticket.
- **[live]** `ACTIVE` -> `DONE` — the same trigger on a ticket that recorded
  **no** work PR (it changed no code): nothing to wait on, so the issue
  closes immediately.
- **[live]** `AWAITING_MERGE` -> `DONE` — the sweep observes every recorded
  PR merged (`engine.engine.resolve_awaiting_merge`, via the `agent-session`
  port's `pr_state`): it posts the merge notice and closes the issue.
- **[live]** `AWAITING_MERGE` -> `BLOCKED` — any recorded PR closed
  **unmerged**: a human declined the work, so the ticket blocks and
  escalates rather than completing silently. Checked before the merge case —
  one abandoned PR outweighs merged siblings.
- **[live]** `AWAITING_MERGE` -> `ACTIVE` — an approver comments
  `/agent-hq request-changes <reason>` on a work PR
  (`engine.engine.poll_pr_feedback`): `projects.feedback_task` is enqueued
  with the reason threaded into its prompt.

Both PR-driven edges are **polled from the sweep**, not event-driven: the
engine repository's workflows cannot observe product-repo events at all, and
no cross-repo forwarder exists (`docs/roadmap.md`). The sweep already visits
every ticket, so a read per watched PR costs nothing new.
- **[planned, Task 16]** `DONE` -> `ACTIVE` — an authorized reopen/native
  reopen when every recorded work PR is still open or none exists: enqueues
  the configured `initial_task`. Any recorded PR already merged or closed
  keeps the ticket `DONE` and requires a new ticket.

### Control outcomes

Every completed task run emits exactly one control outcome
(`schemas/control.schema.json`), and the outcome alone drives the run's
transition — a schema-invalid control document rejects the run; it is never
silently ignored:

- **`handoff`** — `handoffs` required (non-empty). With no post-gate, accepted
  handoffs enqueue as `QUEUED` runs and this run finishes `SUCCEEDED`. With a
  post-gate, the proposals are stored pending (`run.pending_handoffs`) and the
  run stops at `WAITING_GATE`; a gate `APPROVED` applies the stored handoffs
  and completes the run `SUCCEEDED`.
- **`complete`** — `handoffs` forbidden; the run finishes `SUCCEEDED` with no
  children, feeding the `ACTIVE -> DONE` queue-empty check above.
- **`blocked`** — `handoffs` forbidden, `reason` required; the run is
  recorded blocked and the ticket moves to `BLOCKED` with that reason,
  escalating to a human with no auto-retry.

### Work branches [live, Task 12]

Each work repository a ticket touches gets exactly one stable branch,
`agent-hq/<issue-number>` (PLAN.md decision 4 — not `agent-hq/<run_id>`;
every task and rework attempt on that ticket reuses the same branch), created
once from that repository's configured `base_branch` (`repos.yml`) and
updated by every later task. At most one PR per ticket per repository is
opened against that `base_branch` (create-or-get: `engine.runner._collect_success`
reuses `ticket.work_repos[repo].pr_ref` once it's set).

**`base_commit` resolution:** `work_repos[repo].recorded_head` if the ticket
has already landed a task on that repo, else the repo's configured
`base_branch` -- the first task branches from base, every later task/rework
bases on the recorded head, and a downstream failure never resets this (the
branch persists; no special-casing needed). Each attempt is therefore built
on the branch's last recorded head, so collect's landing push is a **plain
fast-forward** (`git push origin HEAD:refs/heads/agent-hq/<issue-number>`,
creating the branch from `base_branch` on the first push) -- the recorded
head IS the lease; `--force-with-lease` adds no case a fast-forward doesn't
already cover. On a rejected push, collect revalidates this run's claim
(only the currently-`RUNNING` run may reconcile or block -- a stale/zombie
run's own rejected push is a no-op) and compares the remote branch's
tree/parent to this attempt's own: identical (a retry that got a fresh
timestamp -- different SHA, same content) is adopted; any real divergence
sets the ticket `BLOCKED` with reason `branch_conflict` rather than forcing
over unknown work (`docs/operations.md` has the operator recovery
procedure).

### Approval and reopen commands

Orchestration approvals and reopen use the same authorized-comment grammar on
the parent (engine-repository) issue, verified against the configured
approver group and deduped by comment id. The approve/request-changes/reject
grammar is **live** (`github_issue_comment_gate.py`'s `status()`, landed with
the Task 9 cutover); `reopen` is **planned** (Task 14/16) -- it needs the
`issue_comment`/`issues` event routing Task 14 adds and the guarded-reopen
transition Task 16 builds:

- `/agent-hq approve [<run-id>]` -> gate `APPROVED`.
- `/agent-hq request-changes [<run-id>] <reason>` -> gate `CHANGES_REQUESTED`
  (rework: the source task re-runs; its `pending_handoffs` are cleared, not
  applied).
- `/agent-hq reject [<run-id>] <reason>` -> gate `REJECTED` (terminal for that
  proposal; `pending_handoffs` are cleared).

The run id is **optional**: a bare `/agent-hq approve` decides whatever gate
is currently open, since per-ticket exclusivity means at most one run is
`WAITING_GATE` at a time. What makes that safe is the cutoff — only comments
created at or after the run's `gate_requested_at` can decide it. Without it a
bare approval left in the thread would satisfy every later gate on the
ticket, since every sweep re-reads the whole thread. An explicit id is still
honored, and is the way to be unambiguous in a thread a human is also using;
an id that isn't the open run's is treated as a decision about another gate
and skipped, not as the first word of a reason (real ids are `sha1[:16]`).
- **[planned]** `/agent-hq reopen <reason>` -> resumes a `BLOCKED` or `DONE`
  ticket per the edges above (PLAN.md decision 14); native
  `issues: reopened` is the equivalent signal, still subject to the same
  guards.

The request comment inlines every artifact the gated run declared, each in a
collapsed `<details>` block (truncated past 20000 characters, well beyond any
real spec) — an approver decides from the issue thread without opening the
state branch. While a run is `WAITING_GATE` the issue carries
`hq:waiting-gate` — one of the engine-owned lifecycle labels
(`engine.engine.STATUS_LABELS`: `hq:active`, `hq:waiting-gate`,
`hq:awaiting-merge`, `hq:blocked`, `hq:done`), applied one at a time by
`set_status_label` and swapped as soon as the status changes. A label is
always a *view* of state, never the source of it, and is written only after
the state write it reflects. Only labels in that map are ever removed:
`set_status_labels` replaces the whole `hq:`-prefixed set on the issue, so
filtering on the prefix instead would strip `hq:intake`, `hq:public-safe`,
and `hq:executor=`. Note that
`WAITING_GATE` counts against `in_flight_cap`, so un-actioned gates hold
slots that queued tickets need.

## Ports and adapters

Every side effect crosses a port; task definitions and engine code bind to
the port name, and `engine.registry.build_adapter(port, adapter_name,
settings)` resolves the config-selected concrete adapter (PA-2). Full
contracts: [`docs/ports/README.md`](ports/README.md).

| Port | P0 adapter | Notes |
|---|---|---|
| `tracker` | `github-issues` | issue read/comment/label |
| `executor` | `copilot-cli` | spawns `copilot -p` (Claude Sonnet 4.5, billed through Copilot); one-line config swap to `claude-code-headless` (spawns `claude -p` on a direct Anthropic key) |
| `agent-session` | `copilot-cli` | worktree prepare/run/collect (same class as `executor`); `CopilotCli` subclasses `ClaudeCodeHeadless` and inherits its git/PR plumbing unchanged |
| `messaging` | `github-comment` | status/escalation comments |
| `gate` | `github-issue-comment` | the `default`/`spec-approval` logical bindings resolve here (`config/components.yml`) -- an authorized-comment approval on the parent engine issue (`docs/ports/gate.md`); `pr-review` remains registered for a task that binds to it explicitly for code-review-style approval on a work-repo PR, but no wired P0 task currently does |
| `poll` | — | Protocol only (`engine.ports.Poll`); no adapter ships in P0 (D3) |
| `qa-env` | — | Protocol only (`engine.ports.QaEnv`); no adapter ships in P0 (D3) |
| `state-store` | `git-json` | fixed implementation, not a port (PD-7) — `engine.state.GitJsonStateStore` is constructed directly, never through the registry |

## Credential boundary (PD-5)

The child `claude` process (fallback `claude-code-headless` binding) gets an
env built key-by-key from an allowlist (`PATH`, `HOME`, `TMPDIR`, `LANG`,
`TERM`, `LC_*`, `CLAUDE_CONFIG_DIR`, `ANTHROPIC_API_KEY`) plus
`--disallowedTools WebFetch,WebSearch`. GitHub credentials (`AGENT_HQ_TOKEN`)
and the ambient `GITHUB_TOKEN`/`GH_TOKEN` are not directly inherited by the
child. This prevents accidental env propagation; it is not a security
boundary when the child has shell access in the same container as a parent
process holding those credentials.

**Copilot-billed deviation (default binding, `copilot-cli`):** the child
`copilot` process gets the same style of from-scratch allowlist env (`PATH`,
`HOME`, `TMPDIR`, `LANG`, `TERM`, `LC_*`, `XDG_CONFIG_HOME`) but, unlike the
Anthropic-key child, it necessarily also holds a GitHub credential —
`COPILOT_GITHUB_TOKEN` — because Copilot CLI authenticates against a GitHub
Copilot seat rather than a model-provider API key. This is assessed and
accepted, not accidental: blast radius on compromise is that seat's account's
GitHub access, which the dedicated bot seat (Copilot access only, **no write
access** to any pilot or engine repo — see `docs/operations.md`) reduces to
"model access only". `engine/adapters/copilot_cli.py` asserts that the engine
credential is absent from the direct child env.

**Isolated-job boundary (hardening plan Task 12, live):** unlike the P0
single-job runner this section originally described, `execute` is now its
own Actions job with `permissions: {}` and ONLY `COPILOT_GITHUB_TOKEN` in
its environment -- `AGENT_HQ_TOKEN` is never set in that job at all, not
merely absent from the child's allowlisted env. `prepare` and `collect` are
separate, credentialed jobs that never run agent code. A compromised or
prompt-injected agent in `execute` therefore cannot exfiltrate the engine
credential from its own job's environment or process tree, since it was
never there. This remains process/job hygiene, not full isolation: the
`execute` job still has its container's filesystem, shell, process
namespace, and direct network access (no egress firewall yet), and the
engine credential lives in the separate `prepare`/`collect` jobs' runners.
The remaining hardening (a network firewall around the agent process) is
tracked in [`docs/project-review.md`](project-review.md); until that lands,
do not run untrusted tickets.

## Retry semantics (D1)

P0 has no checkpoint/resume. A killed or expired run is not resumed from a
saved session — it retries from scratch, bounded by the task's
`budget.retries`. `dispatch.yml`'s sweep re-drives runs left in `RUNNING`
with no active workflow (orphaned enqueues) into a fresh attempt, or marks
the ticket `BLOCKED` once retries are exhausted.

## Deviation ledger

The full decision record is `.hyperclaude/decisions/20260718-p0-scope-cut.md`
(gitignored — a local planning artifact, not part of the committed history).
Summarized here so this doc is self-contained:

1. **TE-11 waived** — no checkpoint/resume; see "Retry semantics" above.
2. **Gates: `pr-review` only in the original P0 cut** — no
   `github-environment` native-approval adapter ships; the hardening plan's
   atomic cutover (Task 9) repoints the `default`/`spec-approval` bindings
   onto the authorized `github-issue-comment` gate instead
   (`docs/ports/gate.md`), keeping `pr-review` registered for a task that
   wants code-review-style approval on a work-repo PR explicitly.
3. **Six adapters, not eight** — `poll` (`github-issue-reactions`) and
   `qa-env` (`docker-compose`) ship as Protocols only; no P0 task consumes
   them.
4. **Fine-grained PAT, not a GitHub App** — one `AGENT_HQ_TOKEN` secret
   scoped to the pilot repos, not a dedicated least-privilege App
   installation.
5. **Replayed state writes, not transactions** — the bounded
   fetch/reset/reapply replay (`engine.state.GitJsonStateStore.write`,
   `_MAX_WRITE_ATTEMPTS`) on a confirmed non-fast-forward push rejection is
   the concurrency control (D5), not a general-purpose
   transaction/conflict-resolution layer. It was originally specified as a
   safety net *behind* a shared `agent-hq-state` Actions concurrency group;
   that group was removed once it proved to cancel bursts of pending runs
   (`docs/operations.md` §11), leaving the replay as the whole mechanism.
6. **Minimal dashboard** — one static state table (ticket/run, spend,
   artifact/PR links, waiting-on-humans), not the full kanban/timeline/spend
   breakdown view.
7. **Operational extras cut** — no monthly budget alerts, no CI-green
   auto-undraft sweep, no `pull_request: closed` closing-summary path, no
   gate half-timeout alerts.
8. **Devcontainer kept for the agent job** — `run.yml`'s execute job still
   runs `scripts/run-phases.sh` inside the project devcontainer via
   `devcontainers/ci` (Codespaces parity honored), even though lighter jobs
   (intake/dispatch/pages/CI) use direct setup.
9. **Copilot-billed executor by default** — `executor`/`agent-session` bind
   to `copilot-cli` (spawns `copilot -p ... --model claude-sonnet-4.5`,
   billed through a dedicated GitHub Copilot seat), not
   `claude-code-headless` (direct Anthropic API key), which stays registered
   as a one-line-swap fallback. Copilot bills the underlying input / cached /
   output tokens, converted to AI credits at published per-model rates
   (1 credit = $0.01), and `copilot -p` prints the session's credits and
   token counts as an end-of-session trailer on **stderr** — so
   `copilot_cli._parse_usage` records the *billed* USD per run, not an
   estimate, and the per-ticket USD caps in `budgets.yml` bind normally
   alongside `budget.retries`, the loop guard (25 runs / depth 12), the
   in-flight cap, and runtime deadlines. Two consequences worth knowing: the
   adapter must not pass `-s` (silent mode suppresses that trailer), and a
   run whose trailer never appears (kill, or a future format change) records
   `cost_usd: 0.0`, `usage_known: true` — deliberately understating rather
   than reporting unknown usage, which would block the ticket on every
   transient failure. See "Credential boundary" above for the PD-5
   assessment of the resulting `COPILOT_GITHUB_TOKEN` in the child env.
10. **`DONE` merge-tracking is a permanent decision, not a P0 cut —
    supersedes deviation 7.** Deviation 7's "no `pull_request: closed`
    closing-summary path" was recorded as an operational extra cut for P0;
    the hardening plan (PLAN.md decision 12, Task 1 of
    `.hyperclaude/plans/20260721-2056-harden-the-existing-plan-at.md`) makes
    it permanent: `DONE` means "engine complete; merge status not tracked",
    watching PR merge state is never added back, and reopen after a merged
    recorded PR requires a new ticket instead of resuming the old one.

See [`docs/roadmap.md`](roadmap.md) for restore triggers on each of these.
