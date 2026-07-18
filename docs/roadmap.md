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
| GitHub App auth | Dedicated least-privilege App installation replacing the pilot's fine-grained PAT | Pilot exit / more repos / stricter least-privilege requirement |
| Reload-reapply state transactions | Conflict-safe field-merge transactions on the state branch | The Actions-concurrency serialization of state writes throttles throughput |
| Full dashboard | Kanban, per-ticket timelines, spend by task-type/adapter/month, effective-config view (P0 ships a single state-table page) | Someone actually asks for a view the minimal page lacks |
| Monthly budget tracking (CFG-5) | Monthly API-$ and Actions-minutes budgets, threshold alerts, cap-driven intake stop | First month-end surprise, or pilot exit |
| CI-green auto-undraft | Sweep polls PR checks, undrafts + requests reviewers when green | Human undrafting becomes a bottleneck |
| pr-merged closing summary | `pull_request: closed` path posting the closing summary + terminal status on human merge (P0: finalize posts it at ready-time) | Merge-time status fidelity matters to the tracker |
| Gate half-timeout alerts | Warning ping at 50% of a gate's working-hours timeout | Gates routinely expiring without warning |

## B. P1 (requirements §13)

- `jira-mirror` tracker adapter — config + external sync, near-zero agent_hq code, zero JIRA credentials (PD-9/JM-1..6).
- Managed executors — `copilot-coding-agent`, `claude-partner-agent` — and the executor bake-off on comparable tickets (PD-3).
- `slack-message` / `slack-reactions` adapters (if GitHub-canonical messaging proves insufficient — open question §12.8).
- Task library: `clinical`, `poll`, `qa`, `docs` (with their gates, PHI lint, Playwright QA, docs-drift blocking).
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

- Egress-restricted agent execution (network firewall — needs self-hosted runners); until then the child agent has runner-level network access, documented in `docs/architecture.md` (NFR-SEC assessment).
- Claude CLI sandbox network-allowlist enforcement (verify per pinned CLI version).
- SHA-pinned Actions references (currently major-version tags).
- TE-11 literal session-resume verification spike (`claude -p --resume` from a restored transcript) — prerequisite for restoring row 1 of section A.
