#!/usr/bin/env bash
set -euo pipefail

# scripts/run-phases.sh <run_id> <phase> [execute_outcome] -- drives ONE
# phase of a run (D1, D7). Each phase is a separate, ISOLATED GitHub Actions
# JOB (.github/workflows/run.yml, hardening plan Task 12): prepare and
# collect are credentialed (AGENT_HQ_TOKEN) and run directly on the runner;
# execute is credential-free (permissions: {}, only COPILOT_GITHUB_TOKEN)
# and runs inside the project devcontainer -- it's the only phase that needs
# the `copilot`/`claude` CLI. The bundle/execute-output artifacts transport
# between jobs as plain files (actions/upload-artifact / download-artifact)
# at the deterministic paths engine/runner.py already agrees on
# (`_prepare/<run_id>`, `_target/<run_id>`, `_execute/<run_id>`) -- no
# custom tar.

run_id="${1:?usage: run-phases.sh <run_id> <phase> [execute_outcome]}"
phase="${2:?usage: run-phases.sh <run_id> <phase> [execute_outcome]}"
execute_outcome="${3:-}"
REPO="${AGENT_HQ_ENGINE_REPO:-${GITHUB_REPOSITORY:-}}"

pip install .

if [[ "$phase" == "execute" ]]; then
  # Check matches the default executor binding (config/components.yml:
  # copilot-cli). Swapping the executor back to claude-code-headless means
  # swapping this check back to `claude --help | grep -q -- --output-format`.
  if ! copilot help 2>/dev/null | grep -Eq -- '(^|[[:space:]])-p([,=[:space:]]|$)'; then
    echo "copilot CLI missing/incompatible" >&2
    exit 1
  fi
fi

# Read-only for execute (no AGENT_HQ_TOKEN in that job's env -- the engine
# repo hosting agent-hq-state is public, PD-5, so an anonymous clone/pull
# works); prepare/collect push through this same script with the token set.
bash scripts/checkout-state.sh

args=(run --run-id "$run_id" --phase "$phase" --state ./_state)
if [[ -n "$execute_outcome" ]]; then
  args+=(--execute-outcome "$execute_outcome")
fi
out=$(agent-hq "${args[@]}" | tail -1)
echo "$out"

if [[ "$phase" == "prepare" && -n "${GITHUB_OUTPUT:-}" ]]; then
  # scripts/run-phases.sh's "claimed=true/false" line IS the job output the
  # workflow gates execute/collect on.
  echo "$out" >> "$GITHUB_OUTPUT"
fi

if [[ "$phase" == "collect" ]]; then
  # Explicit wake-up (PLAN.md decision 5: commits are checkpoints, not
  # triggers), scoped to this run's ticket so the dispatcher's fast path
  # reconciles it immediately instead of waiting for the 15-minute cron.
  ticket_id=$(echo "$out" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ticket_id') or '')")
  if [[ -n "$ticket_id" ]]; then
    curl -s -X POST \
      -H "Authorization: Bearer $AGENT_HQ_TOKEN" \
      -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/$REPO/dispatches" \
      -d "{\"event_type\":\"agent-hq-dispatch\",\"client_payload\":{\"issue\":\"$ticket_id\"}}" || true
  fi
  # No dashboard nudge here: the site is deployed from the `gh-pages` branch
  # and reads state at view time, so a state write is not a reason to
  # redeploy it (docs/architecture.md deviation 6).
fi
