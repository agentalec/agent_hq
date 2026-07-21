#!/usr/bin/env bash
set -euo pipefail

# scripts/run-phases.sh <run_id> -- drives one run's prepare/execute/collect
# phases inside the devcontainer (D1, D7). Invoked by .github/workflows/run.yml
# via devcontainers/ci.

run_id="${1:?usage: run-phases.sh <run_id>}"
REPO="${AGENT_HQ_ENGINE_REPO:-${GITHUB_REPOSITORY:-}}"

pip install .

# Check matches the default executor binding (config/components.yml:
# copilot-cli). Swapping the executor back to claude-code-headless means
# swapping this check back to `claude --help | grep -q -- --output-format`.
if ! copilot help 2>/dev/null | grep -Eq -- '(^|[[:space:]])-p([,=[:space:]]|$)'; then
  echo "copilot CLI missing/incompatible" >&2
  exit 1
fi

bash scripts/checkout-state.sh

claimed=$(agent-hq run --run-id "$run_id" --phase prepare --state ./_state | tail -1)

if [[ "$claimed" == "claimed=true" ]]; then
  set +e
  agent-hq run --run-id "$run_id" --phase execute --state ./_state
  rc=$?
  set -e
  collect_out=$(agent-hq run --run-id "$run_id" --phase collect --state ./_state --execute-outcome "$rc")
  echo "$collect_out"

  # Explicit wake-up (PLAN.md decision 5: commits are checkpoints, not
  # triggers), scoped to this run's ticket so the dispatcher's fast path
  # reconciles it immediately instead of waiting for the 15-minute cron.
  ticket_id=$(echo "$collect_out" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ticket_id') or '')")
  if [[ -n "$ticket_id" ]]; then
    curl -s -X POST \
      -H "Authorization: Bearer $AGENT_HQ_TOKEN" \
      -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/$REPO/dispatches" \
      -d "{\"event_type\":\"agent-hq-dispatch\",\"client_payload\":{\"issue\":\"$ticket_id\"}}" || true
  fi
fi

# Best-effort: refresh the dashboard. A failed/absent Pages workflow must not
# fail the run.
curl -s -X POST \
  -H "Authorization: Bearer $AGENT_HQ_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/actions/workflows/pages.yml/dispatches" \
  -d '{"ref":"main"}' || true
