---
name: hq-ticket
description: Read-only inspection of agent_hq ticket state on the agent-hq-state branch. Use for "what's happening with ticket 42", "ticket status", "list tickets", "why is the ticket stuck", "pending gates", "what runs are queued", "how much has this ticket spent". Reports status, queue/current/history, gate approvals needed, work repos, artifacts, events, and spend. Never mutates anything — for repair use hq-recover.
argument-hint: "[issue-number]"
---
# hq-ticket

Inspect one ticket (or all tickets) from the `agent-hq-state` branch, read-only, without checking anything out.

## Steps

1. Refresh the state ref:
   ```
   git -C <engine-repo> fetch origin agent-hq-state
   ```
   - Fetch fails with "couldn't find remote ref": the branch doesn't exist — report "no deployment state yet" and stop (see `docs/setup-new-repo.md` §6 for bootstrap).
   - No `origin` remote at all: report that this clone has no remote; nothing to inspect.
   - All reads below use `git show` / `git ls-tree` against `origin/agent-hq-state` (or `FETCH_HEAD`) — no checkout, no worktree.

2. List tickets:
   ```
   git ls-tree -d --name-only origin/agent-hq-state tickets/
   ```

3. Read one ticket:
   ```
   git show origin/agent-hq-state:tickets/<n>/state.json
   ```
   `runs` is the single source of truth — there is no stored queue/current/history. Derive:
   - **queue**: runs with `state: QUEUED`, in array (insertion) order.
   - **current**: the one run in `RUNNING` or `WAITING_GATE`.
   - **history**: terminal runs — `SUCCEEDED` / `FAILED` / `BLOCKED`.

4. Report:
   - **Ticket status**: `ACTIVE` / `BLOCKED` / `DONE`; if `BLOCKED`, include `block_reason` and `block_source`.
   - **Current run**: `task_id`, `attempt`, `deadline`, and gate fields (`gate_requested_at`, `gate_request_id`).
   - **If `WAITING_GATE`**: list the run's `pending_handoffs` (each `key`, `target_task`, `reason`), then give the exact unblock comment to post on the engine-repo issue:
     - `/agent-hq approve <run-id>`
     - `/agent-hq request-changes <run-id> <reason>`
     - `/agent-hq reject <run-id> <reason>`

     Who may decide: the group named by `gates.post[0].approvers` in `tasks/<task_id>/task.yml`, resolved to usernames via `groups.<name>.members` in `config/approvers.yml`. Note the latency: decisions are picked up by the dispatch cron (`*/15` minutes), not instantly.
   - **Work repos**: each `work_repos` entry's `repo`, `branch`, `pr_ref`, `recorded_head`, `base_branch`.
   - **Ledger artifacts**:
     ```
     git ls-tree -r --name-only origin/agent-hq-state tickets/<n>/artifacts/
     ```
   - **Recent events** (tail of the append-only log):
     ```
     git show origin/agent-hq-state:tickets/<n>/events.jsonl | tail -20
     ```
   - **Spend**: sum `cost_usd` over runs where `usage_known` is true. Under the `copilot-cli` binding this is always `0.0` (premium-request billing has no USD metering) — say so rather than reporting "free".

5. Adapter health:
   ```
   git show origin/agent-hq-state:health/latest.json
   ```
   Keys are `<port>/<adapter>` with `ok`, `detail`, `ts`. If the path does not exist yet (the file is first written at collect), report "no health recorded yet (no run collected)" instead of surfacing the git error.

## Hard rules

- STRICTLY read-only. Never write, commit, or push to `agent-hq-state`; never comment on, label, or close any issue or PR. If the user asks you to fix, retry, or unblock anything, hand off to `hq-recover`.
- `DONE` means engine-complete — the engine finished its chain. Never present it as "merged"; merge is a human action.
- Do not post the `/agent-hq approve ...` comment yourself — print it for the human approver.
- Trust `state.json` field names as-is (`schemas/state.schema.json`); don't invent fields like `queue` or `current` in output — label them as derived views.

## References

- `docs/architecture.md` — "Lifecycle" (run states, gate flow)
- `docs/operations.md` §11 — state-branch serialization
- `docs/setup-new-repo.md` §7–8 — smoke ticket walkthrough, operating limits
- `schemas/state.schema.json` — exact field shapes
