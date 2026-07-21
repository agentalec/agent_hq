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
necessarily holds a GitHub
credential, and the no-repo-access bot seat bounds its blast radius to
"model access only". It does not isolate the engine PAT held by the surrounding
job; see `docs/architecture.md`. Local testing uses `copilot login` instead --
no token/secret needed locally.

GitHub now recommends built-in `GITHUB_TOKEN` plus
`copilot-requests: write` for organization automation. Adopt that when execute
moves to its own read-only, secret-free job. Do not pass a write-scoped job
token into the current single-job agent process.

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
