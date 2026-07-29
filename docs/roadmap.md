# agent_hq — Roadmap & deferred work

Everything intentionally not in P0, with its restore trigger. Sources: the P0 scope-cut decisions (`.hyperclaude/decisions/20260718-p0-scope-cut.md`, 2026-07-18) and requirements.md §13 phasing.

## A. P0 scope cuts — restore when the trigger fires

| Deferred item | What it is | Restore trigger |
|---|---|---|
| TE-11 checkpoint / session resume | ≤20-min work+session checkpoints on a `agent-hq-ckpt/<run_id>` branch; killed runs resume the Claude session instead of retrying from scratch | Killed/expired runs measurably waste spend or wall-clock in the pilot |
| `github-environment` gate adapter | Native Actions environment approvals (register-job + workflow-run-id correlation, approval job) | A gate needs approvals outside PR review, or arch approvals outgrow artifact PRs |
| `github-issue-reactions` poll adapter | Reaction-based team polls on the ticket issue | The P1 `poll` task |
| `docker-compose` qa-env adapter | Compose stack up/down/capture for integration QA | The P1 `qa` task |
| Scheduled adapter healthchecks (PA-3) | `agent-hq health` probing every configured adapter on the 15-min schedule + failure alerts | First incident where a broken adapter stranded a ticket undetected (P0 records health only for adapters each run exercised) |
| GitHub App auth | Short-lived least-privilege App installation tokens replacing the pilot's fine-grained PAT | Before the first multi-repository production pilot |
| Reload-reapply state transactions | Conflict-safe field-merge transactions on the state branch | The Actions-concurrency serialization of state writes throttles throughput |
| Monthly budget tracking (CFG-5) | Monthly API-$ and Actions-minutes budgets, threshold alerts, cap-driven intake stop | First month-end surprise, or pilot exit |
| CI-green auto-undraft | Sweep polls PR checks, undrafts + requests reviewers when green | Human undrafting becomes a bottleneck |
| Gate half-timeout alerts | Warning ping at 50% of a gate's working-hours timeout | Gates routinely expiring without warning |

## B. P1 (requirements §13)

- `jira-mirror` tracker adapter — config + external sync, near-zero agent_hq code, zero JIRA credentials (PD-9/JM-1..6).
- Managed executors — `copilot-coding-agent`, `claude-partner-agent` — and the executor bake-off on comparable tickets (PD-3). The bake-off now has its second adapter: `copilot-cli` (P0 default) alongside `claude-code-headless` (fallback); the managed `copilot-coding-agent` remains the P1 item.
- `slack-message` / `slack-reactions` adapters (if GitHub-canonical messaging proves insufficient — open question §12.8).
- Task library: `clinical`, `poll`, `docs` (with their gates, PHI lint, docs-drift blocking). Task definitions + minimal skills exist under `tasks/` (validated, not wired into the live chain); still pending: the `github-issue-reactions` adapter, and the one-line `handoff.allowed` edits that activate them. `qa` is now **wired** (`review` → `qa` → `finalize`) — it runs Playwright from the repo's own tooling inside the devcontainer and screenshots each acceptance criterion onto the PR, so it did not wait on the `docker-compose` qa-env adapter; that adapter stays deferred in section A for the stacks the devcontainer can't stand up.
- Multi-repo implement fan-out + input-join (`parallel_ok`).
- Ops alerts (failures + gates past half-timeout via messaging).

## C. P2 (requirements §13)

- `jira-direct` and `slack-buttons` (relay-based; only on measured mirror/reaction shortfall).
- `prebuilt-image` / `remote-preview-env` qa-env adapters.
- Demo-video task (QA video artifacts as raw material).
- OTEL export.
- Self-hosted runners (if GitHub-hosted limits bite).
- Packaging task definitions for reuse by other organizations.

## D. Hardening backlog

- Split prepare/execute/collect into separate jobs so the agent job has no engine secret and no repository write token; use GitHub Agentic Workflows or reproduce its safe-output boundary directly.
- Cross-repository intake webhook/forwarder plus canonical repo-qualified ticket identity; current engine-repo `issues` trigger cannot observe product-repo events. Work-repo PR state and PR comments no longer need it — the sweep polls them (`engine.engine.resolve_awaiting_merge`/`poll_pr_feedback`); what still does is *intake* from a product repo, e.g. an `@agent-hq` mention in a repo no ticket references.
- Notification-inbox reader (`GET /notifications`) as an alternative to per-ticket PR polling. Rejected for now on three counts: read-state is mutable and shared, so a human opening the inbox silently consumes the engine's queue; `/notifications` is user-scoped, which would block the GitHub App migration above; and the ledger already holds the subscription list (`work_repos[*].pr_ref`). Restore trigger: ticket count grows until per-ticket polling is measurably expensive.
- Egress-restricted agent execution using the GitHub Agentic Workflows firewall or an equivalent enforced proxy.
- Claude CLI sandbox network-allowlist enforcement (verify per pinned CLI version).
- SHA-pinned Actions references (currently major-version tags).
- TE-11 literal session-resume verification spike (`claude -p --resume` from a restored transcript) — prerequisite for restoring row 1 of section A.
