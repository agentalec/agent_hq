# agent_hq — ROADMAP

What has been built, in the order it was built, and what is planned next.
Update the Shipped table in the same PR that ships a feature.

Related: `docs/roadmap.md` holds the *deferred* backlog (P0 scope cuts, P1/P2
phasing, hardening) with a restore trigger per item — this file is the
built-over-time record plus a pointer to what's next. `docs/architecture.md`
holds the deviation ledger.

## Shipped

Everything before PR #1 landed as direct commits during the P0 build-out; from
#1 on, every change is a merged PR.

### 2026-07-18 — P0 engine skeleton

| Feature | Where |
|---|---|
| Package + devcontainer scaffold | `pyproject.toml`, `.devcontainer/` |
| JSON Schemas for config, task defs, state, events, health | `schemas/` |
| Engine domain models — causal `run_id`, immutable deadline | `engine/models.py` |
| Git-JSON state store on the orphan `agent-hq-state` branch, serialized writes, idempotent events | `engine/state.py` |
| Config registry loader with logical gate bindings + pilot config | `engine/config.py`, `config/` |
| Task-definition loader and generic library validator | `engine/taskdefs.py` |
| Port Protocols + adapter registry (the P0 adapter set) | `engine/ports/`, `engine/registry.py` |
| `github-issues` tracker adapter on a PAT-authenticated client | `engine/adapters/` |
| `github-comment` messaging adapter | `engine/adapters/` |
| `pr-review` gate adapter with working-hours expiry | `engine/adapters/` |
| `claude-code-headless` executor — credential-free child, JSON result parsing | `engine/adapters/` |
| Structured predicate eval; causal enqueue; concurrency / loop / budget / kill guards | `engine/predicates.py`, `engine/engine.py` |
| Dispatcher sweep, three-phase prepare/execute/collect runner, declarative intake | `engine/engine.py`, `engine/runner.py` |
| P0 task library (intake → finalize) with logical gate bindings + constitution | `tasks/`, `constitution.md` |
| Actions surface: intake / dispatch / run / CI workflows, devcontainer agent job | `.github/workflows/` |
| Minimal XSS-safe static dashboard + Pages workflow | `engine/dashboard.py`, `.github/workflows/pages.yml` |
| Architecture doc, README, config-swap acceptance test | `docs/architecture.md`, `tests/test_config_swap.py` |

### 2026-07-19 → 07-20 — P1 definitions and the Copilot executor

| Feature | Where |
|---|---|
| P1 task definitions (`clinical`, `poll`, `qa`, `docs`) with extensible skills — defined, not wired | `tasks/` |
| CLAUDE.md + extension recipe | `CLAUDE.md`, `docs/building-tasks.md` |
| `copilot-cli` executor adapter — Claude billed through GitHub Copilot, now the default binding | `engine/adapters/` |

### 2026-07-22 — the handoff cutover

The fixed task chain became agent-chosen handoffs, validated by the engine.

| Feature | Where |
|---|---|
| Engine-repo issue tracker separated from work repos (`engine_repo` vs `repos.yml`) | `config/projects.yml`, `engine/engine.py` |
| Schema work: run `repo`/`handoff_key`/`pending_handoffs`, `work_repos`, lifecycle block; conditional three-outcome control output + execute-result; `handoff.allowed`/`max`, `initial_task`, intake config, `base_branch` | `schemas/` |
| State: ledger artifact storage, handoff/block helpers, bounded transactional replay | `engine/state.py` |
| Handoff validation with path containment (no absolute paths, `..`, or symlink escape) | `engine/handoff.py` |
| Atomic cutover to validated handoffs with full completion paths | `engine/engine.py`, `engine/runner.py` |
| Claim-time in-flight cap, per-ticket exclusivity, issue-scoped wake-ups | `engine/engine.py` |
| Isolated prepare/execute/collect jobs transporting validated files between them | `.github/workflows/run.yml`, `scripts/` |
| Collect-side claim revalidation + idempotent re-drive | `engine/runner.py` |
| Task-authoring guide, dispositions, handoff + concurrency docs | `docs/task-authoring.md`, `docs/operations.md` |
| `hq-*` operator skills — setup, authoring, inspection, recovery | `.claude/skills/` |

### 2026-07-22 → 07-28 — pilot hardening (live smoke tests)

Every row here is a merged PR — the live smoke-test rounds against a real
work repo, and the fixes each round surfaced.

| PR | Feature | Where |
|---|---|---|
| #1 | `schemas/` shipped as package data so non-editable installs load them | `pyproject.toml` |
| #2 | Minimal wired route `spec → implement`; care work repos configured | `tasks/`, `config/repos.yml` |
| #4 | Devcontainer base image pinned to bookworm | `.devcontainer/` |
| #6 | `spec` and `implement` prompts route their handoffs explicitly | `tasks/*/prompt.md` |
| #8 | `apply_patch` addresses the patch relative to git's cwd | `engine/runner.py` |
| #9 | Round-3 full-route validation recorded | `docs/live-smoke-test.md` |
| #10 | `implement` ↔ `review` loop with round memory, plus a park endpoint | `tasks/implement/`, `tasks/review/` |
| #12 | Round-4 review-loop + park validation recorded | `docs/live-smoke-test.md` |
| #13 | `review` reflects its findings onto the work-repo PR — new `post_pr_comment` engine capability, called from the credentialed collect phase (the read-only review agent holds no push credential, PD-5); one comment per review round | `engine/engine.py`, `engine/runner.py` |
| #34 | A run that exhausts its retries now escalates. `_handle_failure` blocked the ticket silently while its sibling unknown-spend path escalated — so the ticket stopped dead, only a manual re-enqueue could restart it, and the issue still read "work has been queued". Found by ticket #30's QA blocking unnoticed | `engine/engine.py` |
| #29 | **Per-repo environment setup**: `repos.yml` gains a `setup` map (task id -> shell command, `default` for the rest) run in the worktree before the agent starts. Structured setup costs no agent requests under per-request billing, fails loudly into the ordinary retry path instead of handing the agent a half-built environment, and is config so another project configures its own. care_fe's entry stands up the care backend with fixtures, mirroring the repo's own playwright workflow | `config/repos.yml`, `engine/engine.py`, `engine/runner.py`, `schemas/repos.schema.json` |
| #27 | **Directory artifacts**: an `outputs.artifacts` entry ending in `/` collects whatever files it holds, for output a task can't name in advance. Ledger artifacts are now stored as bytes, so QA screenshots moved out of the work repo (where they polluted the PR diff and would have merged into the product) into `specs/<ticket>/screenshots/`, linked from the state branch. An image referenced but never produced renders as an explicit "missing" note instead of a broken image | `engine/runner.py`, `engine/state.py`, `schemas/task.schema.json`, `tasks/qa/` |
| #23 | Workflow concurrency keyed to what each job owns (`run-<run_id>`, `intake-<issue>`, `agent-hq-dispatch`) instead of one shared `agent-hq-state` group. GitHub keeps a single pending slot per group, so bursts cancelled each other: task runs starved (a ticket never last in a batch might never start) and intakes were dropped outright. `_MAX_WRITE_ATTEMPTS` 5 → 12 for the higher concurrent-writer count that follows | `.github/workflows/`, `engine/state.py` |
| #22 | Gate approvals made usable: the request inlines every artifact the gated run produced (collapsed `<details>`, truncated past 20000 chars, each linked to its ledger copy on the state branch); a `WAITING_GATE` run labels its issue `hq:waiting-gate` until a decision lands; the run id in the approval grammar became optional — a bare `/agent-hq approve` decides the open gate, made safe by ignoring any comment predating `gate_requested_at`; and `gates.post[].auto_approve` lets a task decide its own gate without a human — honored both at gate-open and by the sweep for runs already parked, still posting the artifact-carrying comment (as a record, not a request) and a `gate.decided` event. The pilot's `spec` gate is now auto-approved | `engine/adapters/github_issue_comment_gate.py`, `engine/engine.py`, `engine/runner.py`, `engine/state.py`, `schemas/task.schema.json` |
| #15 | `qa` wired into the route (`review` → `qa` → `finalize`): stands the app up with the work repo's own tooling, screenshots each acceptance criterion, and posts `qa.md` to the PR with its images. Collect rewrites repo-relative image links to raw URLs on the landed commit; the work patch now carries binary files (`git diff --binary`), without which no screenshot could land at all | `tasks/qa/`, `tasks/review/`, `engine/runner.py`, `engine/adapters/claude_code_headless.py` |
| #24 | `spec` and `review` prompts write for the comment they become, not a document: each says where its file is posted, criteria are capped one-liners, capability notes are path-named bullets, findings are one line with a location and a fix, and the over-engineering / security passes became lenses feeding the severity list instead of two sections reporting nothing every round | `tasks/spec/`, `tasks/review/` |
| #25 | Work-repo PRs link back to the agent-hq ticket. The body was the ticket's raw issue body alone, leaving a PR in a work repo with no reference to the engine-repo issue that produced it. A plain reference, never a `Closes` keyword — the engine closes the issue itself once the whole ticket finishes, and one ticket can open a PR per work repo. Written where the PR is actually opened (collect, behind the `agent-session` port), so it covers every task declaring `opens_pr` | `engine/runner.py` |
| #26 | Landed commits describe the work instead of the run. Every commit on every work branch read `agent-hq: <run_id>`; the subject is now `<task>: <ticket title>` with ticket and run id as trailers, built in collect and passed through the `agent-session` port (`land_branch` gains a `message`). The `implement` prompt stopped asking for Conventional Commits per criterion — `materialize_work_patch` squashes the run into one diff, so those messages never reached the work repo | `engine/runner.py`, `engine/adapters/claude_code_headless.py`, `tasks/implement/` |
| #32 | The landed commit's subject became the run's own `control.summary` (a new optional field on the control schema) instead of the ticket title #26 used — a title describes the request, not the change, and repeated verbatim on every commit a ticket landed. Collect already parses `control.json` before landing, so nothing new crosses the job boundary; the engine asks every task for a summary in the generic control-output contract, and falls back to the ticket title when a run declares none | `engine/runner.py`, `schemas/control.schema.json`, `tasks/implement/` |

## Planned

Near-term, in rough order:

0. A **config-level** auto-approve override. `gates.post[].auto_approve`
   ships in the task definition (#22), so it applies to every deployment of
   the library; a gate that should be automatic in a pilot and staffed in
   production needs the switch in `config/`, not in `tasks/`.

1. Wire the staged tasks that already have definitions — `arch-plan`,
   `arch-approval`, `breakdown` (each `task.yml` header names its activation
   edit), then `clinical` / `poll` / `docs`.
2. `github-issue-reactions` (poll) adapter — the blocker for `poll`. The
   `docker-compose` qa-env adapter stays deferred: `qa` ships without it, and
   only a stack the devcontainer can't stand up would justify restoring it.
3. Multi-repo `implement` fan-out + input-join (`parallel_ok`).
4. Ops alerts — run failures and gates past half-timeout, via messaging.
5. GitHub App auth replacing the pilot PAT — before the first multi-repo
   production pilot.

Everything else — the full deferred backlog with its restore trigger per
item, P1/P2 phasing, and the hardening list — lives in
[`docs/roadmap.md`](docs/roadmap.md). Don't restore a deferred item without
its trigger firing.
