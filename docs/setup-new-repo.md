# Setting up agent_hq as a new deployment

The zero-to-first-ticket runbook: stand up a fresh agent_hq instance from
this codebase for your own org and work repos. Day-to-day operation —
credential rotation, the kill switch, `branch_conflict` recovery,
clean-state cutover — lives in [operations.md](operations.md); this doc
links to it rather than restating it. For what a task definition is, see
[task-definition.md](task-definition.md); for writing new tasks, see
[building-tasks.md](building-tasks.md) and the mechanics deep-dive in
[task-authoring.md](task-authoring.md).

## 1. Prerequisites

- **A GitHub org** that will host the engine repo and the work repos.
- **Public repos only** — the engine repo and every work repo. `run.yml`'s
  `execute` job runs the agent with `permissions: {}` and no
  `AGENT_HQ_TOKEN` at all (the isolated-job credential boundary,
  [architecture.md](architecture.md) "Credential boundary"): it checks out
  the engine repo and clones the work repo with no credential, which only
  works when both are public. Public deployment is also the pilot's
  governance stance ([operations.md](operations.md) §9).
- **A dedicated bot account** with a GitHub Copilot seat and **no write
  access** to any repo — the default `copilot-cli` executor authenticates
  as this seat. Details: [operations.md](operations.md) §2.
- **Ability to mint fine-grained PATs** in the org (classic PATs are not
  supported by the Copilot CLI, and `AGENT_HQ_TOKEN` needs fine-grained
  repo scoping).

## 2. Create the engine repo

Create a new public repo in your org from this codebase (fork, template, or
push a copy). Everything must land on the **default branch (`main`)**:

- `intake.yml` (`issues: [labeled, opened]`), `dispatch.yml` (`schedule` +
  `repository_dispatch`), and `pages.yml` (`schedule`) only trigger for
  workflow files on the default branch — that's how GitHub resolves those
  event types.
- The engine itself dispatches `run.yml` with a hardcoded `"ref": "main"`
  (`engine/runner.py`, `GithubWorkflowApi.trigger_run`).

Nothing executes from a feature branch. A config change on a branch is
inert until it merges to `main`.

Enable GitHub Pages on the repo (Settings > Pages > Source: GitHub
Actions) so `pages.yml` can deploy the dashboard.

## 3. Configure `config/*.yml`

Three of the five files (`projects.yml`, `repos.yml`, `approvers.yml`)
ship with `example-*` placeholders that **must** be replaced before the
first real intake; `components.yml` and `budgets.yml` ship with usable
pilot defaults you may keep or tune. `agent-hq config validate` (also run in CI)
checks shape against `schemas/`, not that the values are real — see
[operations.md](operations.md) §4.

**`projects.yml`** — the deployment's identity:

- `repos`: the work repos code lands in (must each appear in `repos.yml`).
- `engine_repo`: `org/repo` of the engine repo itself — hosts intake
  issues, pinned comments, gate comments, and the `agent-hq-state` branch.
  Set it to the repo you just created.
- `intake_label`: the label that makes an issue a ticket (`hq:intake` in
  the pilot config).
- `initial_task`: the task id a newly accepted ticket enqueues (`spec`).
- `intake.min_body_words` / `intake.excluded_labels`: eligibility filter
  applied before any state write (30 words / `hq:excluded` in the pilot).
- `public: true` plus `public_safe_label` (`hq:public-safe`): when public,
  intake rejects any ticket missing that label.

**`repos.yml`** — one entry per work repo:

- `role`: one of `be`/`fe`/`docs` (schema-enforced enum,
  `schemas/repos.schema.json`), used as a tag only.
- `branch_prefix`: required by the schema, but the work branch name is
  currently hardcoded to `agent-hq/<issue-number>` regardless — keep it
  `agent-hq`.
- `product_area`: the routing keyword — intake matches it (case-insensitive
  substring) against the ticket's title, body, and labels to pick the
  target repo (`engine/engine.py:resolve_target_repo`). No match means the
  ticket is blocked as ineligible, so pick words authors will actually use.
- `base_branch`: where the work branch forks from (`main`).

**`approvers.yml`** — GitHub usernames authorized to decide gates:

- `groups.<name>.members`: the pilot tasks reference `product-owners`
  (spec approval), `architects` (arch approval), and `clinical-reviewers`
  (defined for the unwired `clinical` task). `escalation` is live — its
  members are @-mentioned on every engine escalation (blocked tickets,
  branch conflicts, gate rejections), so set it to real
  usernames. A gate decision comment from a
  username not in the run's group is ignored, so wrong usernames here mean
  approvals silently don't count.
- `working_hours`: timezone/start/end/days used to compute gate timeout
  deadlines (`timeout_working_hours` in task gates).

**`components.yml`** — port-to-adapter bindings
([architecture.md](architecture.md) "Ports and adapters"):

- `executor` / `agent-session` default to `copilot-cli` (model
  `claude-sonnet-4.5`), billed through the bot seat's Copilot subscription.
  Swap `adapter` to `claude-code-headless` — one line each — to run on a
  direct Anthropic API key instead: do this if you have no Copilot seat,
  want real per-run USD metering (see `budgets.yml` below), or need a model
  Copilot doesn't offer.
- `tracker: github-issues`, `messaging: github-comment`, and
  `gate: github-issue-comment` (with the named `spec-approval` binding)
  normally stay as-is.

**`budgets.yml`** — spend and runaway guards:

- `ticket_cap_usd` (25): per-ticket USD cap. **Does not bind under the
  default `copilot-cli` executor** — Copilot premium-request billing has no
  per-run USD metering, so runs record `cost_usd: 0.0`
  ([architecture.md](architecture.md) deviation 9). It binds again under
  `claude-code-headless`.
- `in_flight_cap` (3): max concurrently active tickets.
- `loop_guard.max_runs` (25) / `max_depth` (12): per-ticket run-count and
  handoff-chain-depth ceilings — the guards that still bound runaway work
  when USD metering doesn't.

## 4. Secrets and variables

On the engine repo, Settings > Secrets and variables > Actions. Full table
and scoping details: [operations.md](operations.md) §1–2.

- `AGENT_HQ_TOKEN` (secret): fine-grained PAT scoped to the engine repo
  **and** every work repo — Contents, Issues, Pull requests, Actions, all
  read/write.
- `AGENT_HQ_COPILOT_TOKEN` (secret): fine-grained PAT on the bot account
  with the account-level **Copilot Requests** permission and no repo
  access; the only credential the `execute` job ever holds.
- `ANTHROPIC_API_KEY` (secret): only if you swapped the executor to
  `claude-code-headless`.
- `AGENT_HQ_KILL_SWITCH` (variable): leave unset; set to `1` to pause
  dispatch ([operations.md](operations.md) §6).

## 5. Labels on the engine repo

Create the labels your config names — GitHub won't auto-create them, and a
label that doesn't exist can't be applied at intake. With the pilot
defaults:

- `hq:intake` — makes an issue a ticket (`intake_label`).
- `hq:public-safe` — required on every ticket while `public: true`
  (`public_safe_label`).
- `hq:excluded` — blocks a ticket from automation
  (`intake.excluded_labels`).

## 6. What bootstraps itself

- **The `agent-hq-state` branch**: `scripts/checkout-state.sh`
  self-bootstraps the orphan state branch on the first workflow run — no
  manual branch creation ([operations.md](operations.md) §3).
- **The dashboard**: `pages.yml` builds and deploys it on a `*/5` schedule
  and after intake/dispatch, once Pages is enabled (step 2).
- **The execute environment**: `run.yml`'s `execute` job builds the engine
  repo's own `.devcontainer/devcontainer.json` (pinned Node 22 +
  `@github/copilot`) via `devcontainers/ci` — the only phase that needs the
  `copilot`/`claude` CLI. Work repos need no devcontainer of their own, but
  the engine repo's must build; verify it below.

## 7. Verify, then run a first smoke ticket

First run the manual integration checks in
[operations.md](operations.md) §5 — a `checkout-state.sh` round-trip, one
real Copilot CLI run, and a devcontainer build. CI doesn't cover live auth
or the agent CLI.

Then open an issue in the **engine repo**:

- both labels: the intake label and the public-safe label;
- a body of at least `min_body_words` words (30 by default);
- title/body/label wording that contains a configured `product_area`
  string (e.g. "backend"), so `resolve_target_repo` finds a work repo.

What to watch, in order:

1. **Intake workflow run** (Actions > Intake), triggered by the label
   event.
2. **Pinned comment** on the issue: "Accepted by agent-hq; work has been
   queued." A rejection instead pins the eligibility reasons (too short,
   missing label, no product-area match, or a prompt-injection flag) —
   fix the issue and re-apply the intake label to retry.
3. **Dispatch**: intake wakes the dispatcher immediately via
   `repository_dispatch`, which triggers a **Run** workflow named
   `agent-hq/<run_id>` — the `spec` run's three prepare/execute/collect
   jobs.
4. **The spec result**: `specs/<ticket>/spec.md` is persisted as a ledger
   artifact at `tickets/<issue>/artifacts/<run_id>/specs/<issue>/spec.md`
   on the engine repo's `agent-hq-state` branch — declared outputs are
   deliberately excluded from the work-repo patch, so the work repo only
   gains an (initially empty) `agent-hq/<issue-number>` branch at this
   stage. A **gate request comment** appears on the issue: "Approval
   requested: `spec` (<run-id>)", mentioning the `product-owners` members.

To approve, reply on the same issue as a member of the gate's approver
group (the request comment shows these exact commands with the run id
filled in):

```
/agent-hq approve <run-id>
/agent-hq request-changes <run-id> <reason>
/agent-hq reject <run-id> <reason>
```

The command must be its own line; the latest authorized decision for that
run id wins (`engine/adapters/github_issue_comment_gate.py`). There is no
comment-triggered fast path yet: decisions are noticed by the next
`dispatch.yml` sweep, so expect **up to ~15 minutes** (the `*/15` cron)
before the ticket moves.

From there the pilot route runs: `spec` (fans out one `implement` handoff
per affected repo) → `implement` (the only task that opens a PR, one draft
PR per repo per ticket) → `review`, which loops back to `implement` while it
finds blockers (prompt-capped at 3 rounds — on the cap the engine posts the
accumulated findings to the ticket thread and parks awaiting a human, PR
left in draft) or hands to `finalize` when clean. The fuller route
(`arch-plan` → `arch-approval` → `breakdown`) is staged — each task's header
names its activation edit. When `finalize` completes and the queue is empty,
the engine posts the closing summary from `specs/<ticket>/summary.md`,
marks each recorded PR ready for review, closes the issue, and sets the
ticket `DONE`. **DONE means engine-complete**: the PRs are ready but not
merged — merging is a human action, and merge status is deliberately never
tracked ([architecture.md](architecture.md) deviation 10).

## 8. Operating limits of the current build

The hardening plan's Tasks 1–13 are landed; the operator-command and
event-routing work (Tasks 14+) is not. Honest caveats until it is:

- **Gate decisions are polled, not pushed.** No `issue_comment` event
  routing exists, so every approval waits for the dispatch cron — up to
  ~15 minutes of latency per gate.
- **Do not close or relabel the parent issue mid-flight.** Close events
  are invisible to the engine (`intake.yml` only listens to
  `labeled`/`opened`), so closing the issue does not stop the ticket —
  runs keep executing against a closed issue. And a label event on a
  ticket with no non-terminal runs re-enters intake: a `DONE` ticket still
  carrying the intake label can re-enqueue a whole new lifecycle. To pause
  work, use the kill switch ([operations.md](operations.md) §6) — it stops
  new dispatch while in-flight runs finish.
- **No operator retry/block/unblock/reopen CLI yet.** The `agent-hq` CLI
  has only `config validate`, `tasks validate`, `intake`, `dispatch`,
  `run`, and `dashboard`; `/agent-hq reopen` is planned, not live
  ([architecture.md](architecture.md) "Approval and reopen commands").
  Recovery from a `BLOCKED` ticket today means editing the
  `agent-hq-state` branch by hand — the `branch_conflict` procedure in
  [operations.md](operations.md) §10 shows the shape of it.
- **Completion side effects that crash need manual state repair.** If the
  process dies partway through queue-empty completion (summary posted, PRs
  marked ready, issue closed, then the `DONE` write), the ticket can be
  left `ACTIVE` with some side effects already done and nothing re-driving
  the rest; finishing it is a manual state-branch edit.
- **Do not run untrusted tickets.** The execute job is credential-free but
  has unrestricted network egress; the firewall is future work
  ([architecture.md](architecture.md) "Credential boundary",
  [project-review.md](project-review.md)).
