# Operations runbook (P0 pilot)

Setup and day-to-day operation of the GitHub Actions surface (Task 15,
`.github/workflows/*`, `scripts/checkout-state.sh`, `scripts/run-phases.sh`).
See `.hyperclaude/decisions/20260718-p0-scope-cut.md` for the decisions
(D4/D5/D7/D8) this runbook implements.

## 1. GitHub write credential (`AGENT_HQ_TOKEN`, D4)

The current multi-repository P0 wiring expects a fine-grained PAT in
`AGENT_HQ_TOKEN`, scoped to the configured pilot repos **and** the engine repo
(which hosts `agent-hq-state`). Permissions:

- Contents: Read and write
- Issues: Read and write
- Pull requests: Read and write
- Actions: Read and write

Store it as an Actions secret named `AGENT_HQ_TOKEN` on the engine repo. A PAT
is not required by the engine API: this variable can hold any accepted bearer
token. For same-repository workflows, the built-in `GITHUB_TOKEN` is enough.
For the actual cross-repository design, a short-lived GitHub App installation
token minted per job is the production target. The checked-in workflows do
not mint that token yet; see the blockers in `docs/project-review.md`.

**Rotation:** PATs expire. Before expiry, mint a replacement with the same
scopes and update the `AGENT_HQ_TOKEN` secret; no code or workflow change is
needed. A silently expired token surfaces as `checkout-state.sh` failing
with "auth or network error" or as 401s from `agent-hq intake`/`dispatch`
workflow runs -- check those first if the pilot goes quiet.

## 2. Secrets and variables

On the engine repo, under Settings > Secrets and variables > Actions:

| Name | Kind | Purpose |
|---|---|---|
| `AGENT_HQ_TOKEN` | secret | current cross-repo fine-grained PAT; replace with per-job GitHub App installation tokens before production |
| `AGENT_HQ_COPILOT_TOKEN` | secret | dedicated bot-seat fine-grained PAT with the account-level Copilot Requests permission; passed into the child as `COPILOT_GITHUB_TOKEN` |
| `ANTHROPIC_API_KEY` | secret | only needed when the `executor`/`agent-session` binding is swapped back to `claude-code-headless` (see `config/components.yml`) |
| `AGENT_HQ_KILL_SWITCH` | variable | `dispatch.yml` env; set to `1` to pause all new dispatch (checked by `engine.engine.kill_switch_active`) |

**`AGENT_HQ_COPILOT_TOKEN` setup:** create a dedicated GitHub account (a bot
seat, not a human's), assign it a GitHub Copilot seat, and give it **no
write access** to any pilot or engine repo -- it only needs model access.
Mint a fine-grained PAT with the **Copilot Requests** account permission and
store it as `AGENT_HQ_COPILOT_TOKEN`; classic PATs are not supported by the
current Copilot CLI. This is the PD-5 deviation: the Copilot child process
necessarily holds a GitHub credential, and the no-repo-access bot seat bounds
its blast radius to "model access only". Since the hardening plan's Task 12
isolated-job cutover, `execute` (the job that runs this child) is its own
credential-free Actions job -- `AGENT_HQ_TOKEN` is never in its environment
at all, not merely absent from the child's allowlist; see
`docs/architecture.md` "Credential boundary". Local testing uses `copilot
login` instead -- no token/secret needed locally.

GitHub now recommends built-in `GITHUB_TOKEN` plus
`copilot-requests: write` for organization automation. Adopt that in a
future pass to drop `AGENT_HQ_COPILOT_TOKEN` entirely; do not pass a
write-scoped job token into `execute` meanwhile.

## 3. Orphan state branch bootstrap

`scripts/checkout-state.sh` self-bootstraps `agent-hq-state` on first run --
no manual branch creation needed. It's an empty orphan branch with a single
`.keep` file until the first ticket writes state.

## 4. Config placeholders

`config/repos.yml`, `config/projects.yml`, and `config/approvers.yml` ship
with `example-*` placeholder org/repo/username values pending requirements
§12 answers (real pilot repos and approver usernames). Replace them before
the first real intake; `agent-hq config validate` (also run in CI) only
checks shape, not that the values are real.

## 5. Manual integration checks

These aren't covered by CI (`actionlint` lints workflow syntax; it doesn't
exercise live GitHub auth or the agent CLI) and should be run once after
setup, and again after any change to `scripts/checkout-state.sh`,
`.devcontainer/devcontainer.json`, or the pinned Copilot/Claude CLI versions:

1. **`checkout-state.sh` round-trip against the private engine repo** --
   run it locally (or via `workflow_dispatch` on `dispatch.yml`) with
   `AGENT_HQ_TOKEN` set and confirm `./_state` clones/bootstraps and a
   subsequent `agent-hq intake`/`dispatch` write pushes cleanly.
2. **One real `copilot -p "say hi" -s` run** -- logged in locally via
   `copilot` (or with `COPILOT_GITHUB_TOKEN` set to the bot-seat PAT in CI)
   -- confirms the pinned Copilot CLI version still runs non-interactively
   and exits cleanly, and that its billing shows up as a Copilot premium
   request rather than direct Anthropic spend. Re-check whenever
   `postCreateCommand` in `.devcontainer/devcontainer.json` bumps the
   `@github/copilot` version. The current pin is `1.0.54` on Node.js 22.
3. **Devcontainer build** -- `devcontainer build --workspace-folder .` (or
   let `run.yml`'s `devcontainers/ci@v0.3` step build it) succeeds and
   `copilot help` inside it reports the `-p` prompt option.

**Swapped-back fallback (`claude-code-headless`):** if the `executor`/
`agent-session` binding is swapped to `claude-code-headless`, re-run check 2
as one real `claude -p --output-format json` run instead, confirming the
Claude CLI's JSON result shape still matches what
`engine/adapters/claude_code_headless.py` parses, and check 3's grep target
becomes `claude --help` reporting `--output-format`. `ANTHROPIC_API_KEY`
must be set for this path (see the secrets table above).

## 6. Kill switch

Set the `AGENT_HQ_KILL_SWITCH` repo variable to `1` to stop `dispatch.yml`
from triggering new runs (in-flight runs already dispatched still finish).
Unset it (or set to anything else) to resume. Intake still records/blocks
tickets while the switch is on; only dispatch is paused.

## 7. Local validation

The exact offline, devcontainer, Copilot, and live sandbox checks are in
[`docs/local-testing.md`](local-testing.md). Do not start a production pilot
until the open blockers in [`docs/project-review.md`](project-review.md) are
closed.

## 8. Clean-state cutover

The hardening plan
(`.hyperclaude/plans/20260721-2056-harden-the-existing-plan-at.md`, Task 9)
replaces the current static `on_success.enqueue` chain with validated
handoffs and a new `runs`-only state shape (`docs/architecture.md`,
"Lifecycle"). That schema change must start from a clean `tickets/` area on
`agent-hq-state`, not a mix of old- and new-shape ticket directories:

1. Confirm no live ticket depends on an existing `tickets/<n>/` directory
   written under the pre-cutover schema (no `ACTIVE` ticket mid-flight when
   the cutover lands).
2. **MANUAL (operator):** on the `agent-hq-state` branch, archive those
   `tickets/<n>/` directories outside the active `tickets/` namespace (or
   remove them) before Task 9's commit lands. This is a direct edit to the
   orphan state branch, not something the engine does for you.
3. **Atomic-cutover rule:** the `on_success.enqueue` -> handoff swap lands in
   the single Task 9 commit. No production interval may run the old static
   enqueue and the new handoff progression side by side — do not dispatch
   against a `tickets/` area that mixes pre- and post-cutover run shapes.

## 9. Public-data governance

Per PLAN.md decision 15, the pilot targets public repositories only, and
intake must reject content that is not public-safe. The enforceable gate:
when `config/projects.yml`'s `public` is `true`, a configured
`public_safe_label` (e.g. `hq:public-safe`) is required on the parent issue;
intake rejects a ticket missing that label **before the first state or
artifact write** — so no unreviewed content ever reaches `agent-hq-state` or
a work-repo artifact. The `public`/`public_safe_label` config fields
(`schemas/projects.schema.json`) land in Task 6 of the hardening plan; the
enforcing intake-rejection logic lands in Task 9.

Private deployments do not get a public dashboard: use the operator CLI
(`agent-hq` commands, §2 and `docs/project-review.md`) instead of GitHub
Pages. `pages.yml` gating on `public: false` (skip new deploys, and the
one-time manual unpublish step for an install that was previously public)
lands in Task 17.

## 10. Isolated prepare/execute/collect jobs (Task 12)

`run.yml` runs each task's three phases as three separate Actions jobs
(`docs/architecture.md` "Flow"): `prepare` and `collect` are credentialed
(`AGENT_HQ_TOKEN`) and run directly on the runner; `execute` is
credential-free (`permissions: {}`, only `COPILOT_GITHUB_TOKEN`) and runs
inside the project devcontainer -- it's the only phase that needs the
`copilot`/`claude` CLI. `bundle-<run_id>` and `execute-out-<run_id>`
Actions artifacts transport prepare's manifest and execute's output between
jobs; both are pruned (`retention-days: 1`) since they're single-use
transport, not durable state.

**`branch_conflict` recovery.** Collect lands each task's work on the
ticket's stable `agent-hq/<issue-number>` branch with a plain fast-forward
push (`docs/architecture.md` "Work branches"). If that push is rejected and
the remote content doesn't match this run's own intended commit, the ticket
is set `BLOCKED` with reason `branch_conflict` rather than force-pushed
over. To recover:

1. Inspect the remote `agent-hq/<issue-number>` head in the target repo
   against `ticket.work_repos[repo].recorded_head` (state store) -- diff
   them to see what unexpected work landed on the branch.
2. If that unexpected work is worth keeping, **copy it to a separate branch
   first** (e.g. `git branch rescue/<issue-number> agent-hq/<issue-number>`
   and push `rescue/<issue-number>`).
3. **Reset** `agent-hq/<issue-number>` back to `recorded_head` (a
   force-push of that exact commit) -- do **not** hand-merge the two
   histories: a merge moves the remote head off `recorded_head`, so the
   next `retry` (which bases its attempt on `recorded_head`) would just
   re-block.
4. `retry` the terminally-`BLOCKED` run (it enqueues a replacement attempt
   built on `recorded_head`, now matching the reset branch). `unblock` is
   only for an operator/`issue_closed` block, not this one; `reconcile`
   would just reproduce the same conflict.

## 11. Push/replay as cross-ticket serialization (Task 13)

No lock guards `agent-hq-state` for correctness. The credentialed jobs
(dispatch, prepare, collect) do still take a short-held `agent-hq-state`
Actions concurrency group -- but that only reduces how often writers contend;
what actually serializes them is per-ticket run exclusivity (at most one
`RUNNING`/`WAITING_GATE` run per ticket, enforced in `claim_run`) plus every
state write being a short transaction -- read, mutate in memory, commit,
push. A write whose push is rejected (someone
else's commit landed first) just replays: fetch, `reset --hard`, re-run the
same mutation against fresh state (`engine/state.py`'s bounded retry). That
push/replay loop, not a separate lock, is what serializes concurrent writers
across *different* tickets sharing the one `agent-hq-state` branch.

Collect never holds that transaction open across its external side effects
(branch push, PR open, gate request) -- it does those first, then commits
whatever the result was in one final write. That gap between "did the
external thing" and "recorded it" is exactly why collect revalidates its own
claim twice before committing anything the ticket doesn't already know
about:

- **Early, read-only, immediately before the branch push/PR-open/gate
  request**: if the ticket isn't `ACTIVE` or this run isn't `RUNNING`
  anymore (superseded -- e.g. the dispatcher's lost-run sweep already
  retried it under a new run_id), collect stops before attempting any of
  them.
- **Final, inside the write transaction**: the same check, re-read fresh at
  commit time, is the authoritative fence -- even if a race let a push slip
  past the early check, the run's result is simply never recorded.

A re-driven (retried) lost run therefore never duplicates a comment, PR, or
state entry, even if its original attempt is still straggling: the
straggler observes its own claim is gone and stops, rather than relying
solely on the branch's fast-forward rejection to keep it harmless.
