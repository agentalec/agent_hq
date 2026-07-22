#!/usr/bin/env bash
set -euo pipefail

# scripts/checkout-state.sh -- create/refresh ./_state as a worktree of the
# orphan `agent-hq-state` branch (PD-6, D5, D7). Idempotent: re-running
# against an already-checked-out ./_state just fast-forwards it.
#
# Requires AGENT_HQ_TOKEN (fine-grained PAT, D4) in the environment; the
# token is never written to disk, only referenced by a credential-helper
# shell snippet.

REPO="${AGENT_HQ_ENGINE_REPO:-${GITHUB_REPOSITORY:-}}"
if [[ -z "$REPO" ]]; then
  echo "checkout-state: set AGENT_HQ_ENGINE_REPO or GITHUB_REPOSITORY" >&2
  exit 1
fi

URL="https://github.com/$REPO.git"
CRED_HELPER='!f(){ echo username=x-access-token; echo "password=$AGENT_HQ_TOKEN"; };f'

set_bot_identity() {
  git -C "$1" config user.name "agent-hq[bot]"
  git -C "$1" config user.email "agent-hq[bot]@users.noreply.github.com"
}

# Idempotent fast path: already checked out on the right branch.
if [[ -d ./_state/.git ]] && [[ "$(git -C ./_state rev-parse --abbrev-ref HEAD)" == "agent-hq-state" ]]; then
  set_bot_identity ./_state
  git -C ./_state pull --ff-only
  exit 0
fi

set +e
git -c credential.helper="$CRED_HELPER" ls-remote --exit-code --heads "$URL" agent-hq-state >/dev/null
exit_code=$?
set -e

case "$exit_code" in
  0)
    # --depth 1: checkout cost stays independent of state-branch history
    # (PLAN.md "State and branch layout"). Push/fetch/reset all work from a
    # shallow clone; later fetches deepen only by the session's new commits.
    git -c credential.helper="$CRED_HELPER" clone --depth 1 --branch agent-hq-state --single-branch "$URL" ./_state
    set_bot_identity ./_state
    git -C ./_state config credential.helper "$CRED_HELPER"
    ;;
  2)
    # First run ever: bootstrap the orphan branch.
    mkdir -p ./_state
    git -C ./_state init -b agent-hq-state
    set_bot_identity ./_state
    git -C ./_state remote add origin "$URL"
    git -C ./_state config credential.helper "$CRED_HELPER"
    : > ./_state/.keep
    git -C ./_state add .keep
    git -C ./_state commit -m "state: bootstrap agent-hq-state"
    if ! git -C ./_state push -u origin agent-hq-state; then
      # Race: another workflow bootstrapped first -- adopt their branch.
      git -C ./_state fetch origin agent-hq-state
      git -C ./_state reset --hard origin/agent-hq-state
      # A failed `push -u` never set upstream tracking; without it every
      # later bare `git push` from the state store dies with no-upstream.
      git -C ./_state branch --set-upstream-to=origin/agent-hq-state agent-hq-state
    fi
    ;;
  *)
    echo "checkout-state: git ls-remote failed (exit $exit_code) against $URL -- auth or network error, not a missing branch" >&2
    exit 1
    ;;
esac
