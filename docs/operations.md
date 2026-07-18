# Operations runbook (P0 pilot)

Setup and day-to-day operation of the GitHub Actions surface (Task 15,
`.github/workflows/*`, `scripts/checkout-state.sh`, `scripts/run-phases.sh`).
See `.hyperclaude/decisions/20260718-p0-scope-cut.md` for the decisions
(D4/D5/D7/D8) this runbook implements.

## 1. Fine-grained PAT (`AGENT_HQ_TOKEN`, D4)

Create one fine-grained personal access token, scoped to the pilot repos
(the two configured in `config/repos.yml`) **and** the engine repo (which
also hosts the orphan `agent-hq-state` branch). Permissions:

- Contents: Read and write
- Issues: Read and write
- Pull requests: Read and write
- Actions: Read and write

Store it as an Actions secret named `AGENT_HQ_TOKEN` on the engine repo. This
is a pilot-scale simplification (D4) -- a dedicated least-privilege GitHub
App installation is P1 (see `docs/roadmap.md`).

**Rotation:** PATs expire. Before expiry, mint a replacement with the same
scopes and update the `AGENT_HQ_TOKEN` secret; no code or workflow change is
needed. A silently expired token surfaces as `checkout-state.sh` failing
with "auth or network error" or as 401s from `agent-hq intake`/`dispatch`
workflow runs -- check those first if the pilot goes quiet.

## 2. Secrets and variables

On the engine repo, under Settings > Secrets and variables > Actions:

| Name | Kind | Purpose |
|---|---|---|
| `AGENT_HQ_TOKEN` | secret | fine-grained PAT, see above |
| `ANTHROPIC_API_KEY` | secret | passed into the agent's child env (run.yml only) |
| `AGENT_HQ_KILL_SWITCH` | variable | `dispatch.yml` env; set to `1` to pause all new dispatch (checked by `engine.engine.kill_switch_active`) |

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
`.devcontainer/devcontainer.json`, or the pinned Claude CLI version:

1. **`checkout-state.sh` round-trip against the private engine repo** --
   run it locally (or via `workflow_dispatch` on `dispatch.yml`) with
   `AGENT_HQ_TOKEN` set and confirm `./_state` clones/bootstraps and a
   subsequent `agent-hq intake`/`dispatch` write pushes cleanly.
2. **One real `claude -p --output-format json` run** -- confirm the pinned
   Claude CLI version's stream-json output shape still matches what
   `engine/adapters/claude_code_headless.py` parses (usage/session-id at
   exit). Re-check whenever `postCreateCommand` in
   `.devcontainer/devcontainer.json` bumps the `@anthropic-ai/claude-code`
   version.
3. **Devcontainer build** -- `devcontainer build --workspace-folder .` (or
   let `run.yml`'s `devcontainers/ci@v0.3` step build it) succeeds and
   `claude --help` inside it reports `--output-format`.

## 6. Kill switch

Set the `AGENT_HQ_KILL_SWITCH` repo variable to `1` to stop `dispatch.yml`
from triggering new runs (in-flight runs already dispatched still finish).
Unset it (or set to anything else) to resume. Intake still records/blocks
tickets while the switch is on; only dispatch is paused.
