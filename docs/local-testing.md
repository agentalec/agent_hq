# Local testing

Use three levels. The first is the required pre-PR check; the other two need
Docker, Copilot access, or GitHub access.

## 1. Offline checks (required)

Requires Python 3.11+ and Git. No PAT, Copilot login, network, or live GitHub
repository is used by the tests; state tests create real temporary local Git
repositories.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/agent-hq config validate
.venv/bin/agent-hq tasks validate
docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:1.7.7 -color
```

These are the same five checks run by `.github/workflows/ci.yml`. If Docker is
not available, run the first four and let CI run `actionlint`.

## 2. Devcontainer and agent smoke test

The devcontainer is the production agent runtime. Build it after changes to
`.devcontainer/devcontainer.json`, `scripts/run-phases.sh`, or an agent adapter:

```bash
devcontainer build --workspace-folder .
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . copilot version
devcontainer exec --workspace-folder . copilot help
```

The pinned Copilot CLI requires Node.js 22. For a harmless local inference
check, authenticate interactively and run a prompt that needs no tools:

```bash
copilot login
copilot -p "Reply exactly: OK" -s --no-ask-user --model claude-sonnet-4.5
```

Interactive OAuth is the preferred local authentication. Do not create or
export a PAT merely for this smoke test.

## 3. Live GitHub sandbox test

Do this only in throwaway private repositories. The current multi-repository
intake topology is a release blocker documented in `docs/project-review.md`;
do not point the pilot at production repositories until it is fixed.

For the state-branch round trip, authenticate the engine process with an
existing GitHub CLI login, run the checkout twice, and then clear the token:

```bash
export AGENT_HQ_ENGINE_REPO=owner/sandbox-engine
export AGENT_HQ_TOKEN="$(gh auth token)"
bash scripts/checkout-state.sh
bash scripts/checkout-state.sh
unset AGENT_HQ_TOKEN
```

Then use `workflow_dispatch` in this order: `Dispatch`, one generated `Run`,
and `Pages`. Confirm that:

1. `agent-hq-state` gets one state commit per transition.
2. Re-dispatching the same `run_id` creates no duplicate run, comment, or PR.
3. The agent job stops at its task deadline and the workflow stops at 120
   minutes.
4. A gated artifact PR waits for an allowed reviewer.
5. Finalize marks the implementation PR ready through the GraphQL mutation.

`actionlint` cannot prove any of these live authentication and API behaviors.

## Credential matrix

| Operation | Local | GitHub Actions today | Preferred target |
|---|---|---|---|
| Unit/config/task validation | None | Built-in `GITHUB_TOKEN` is unused | None |
| Engine Git/API writes, same repository | `gh auth token` for a sandbox only | Built-in `GITHUB_TOKEN` can work if wired into `AGENT_HQ_TOKEN` | Built-in `GITHUB_TOKEN` |
| Engine Git/API writes, multiple repositories | GitHub CLI login or fine-grained PAT | `AGENT_HQ_TOKEN` fine-grained PAT | Short-lived GitHub App installation token |
| Copilot CLI inference | `copilot login` OAuth | `AGENT_HQ_COPILOT_TOKEN` fine-grained PAT | Built-in `GITHUB_TOKEN` with `copilot-requests: write`, in a read-only agent job |
| Claude fallback | `ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` | OIDC/WIF where available |

