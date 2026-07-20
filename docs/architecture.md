# Architecture (P0)

## Flow

1. A GitHub issue labeled `hq:intake` is the entry point. `intake.yml`
   (triggered on issue label/edit) reads it via the `tracker` port, records a
   ticket on the state branch, and enqueues the `spec` task.
2. State lives on an orphan `agent-hq-state` branch (`engine.state.GitJsonStateStore`,
   plain JSON files, one fixed implementation per PD-7 — not a port, no
   adapter to swap). All state-writing workflows share the
   `agent-hq-state` Actions `concurrency` group (`cancel-in-progress: false`),
   so writes serialize instead of racing (D5).
3. `dispatch.yml` runs on a 15-minute schedule (plus `repository_dispatch`/
   `workflow_dispatch`). It sweeps the state store for queued runs, gate
   timeouts, and orphaned/stale running work, then triggers `run.yml` via
   `workflow_dispatch` for anything ready to execute.
4. `run.yml` executes one task phase for a run inside the project
   devcontainer (`devcontainers/ci`, D7 — Codespaces parity), running
   `scripts/run-phases.sh`: **prepare** (clone target repo, build the prompt
   bundle) -> **execute** (spawn `copilot -p "<prompt>" -s --no-ask-user
   --model claude-sonnet-4.5`, billed through a GitHub Copilot seat rather
   than a direct Anthropic key) -> **collect** (parse
   `.agent-hq/execute-result.json`, commit outputs, open/update the artifact
   PR, record adapter health).
5. Tasks with a `gates.post` entry (e.g. `spec`'s `spec-approval`) stop after
   collect until the gate's adapter reports `APPROVED`; `dispatch.yml`'s
   sweep polls gate status and advances the ticket via `on_success.enqueue`
   once approved. Merge is always a human action — no task auto-merges a PR.
6. `pages.yml` renders a static dashboard (ticket/run state table, spend,
   waiting-on-humans list) after intake/dispatch/collect and on a `*/5`
   schedule.

## Ports and adapters

Every side effect crosses a port; task definitions and engine code bind to
the port name, and `engine.registry.build_adapter(port, adapter_name,
settings)` resolves the config-selected concrete adapter (PA-2). Full
contracts: [`docs/ports/README.md`](ports/README.md).

| Port | P0 adapter | Notes |
|---|---|---|
| `tracker` | `github-issues` | issue read/comment/label |
| `executor` | `copilot-cli` | spawns `copilot -p` (Claude Sonnet 4.5, billed through Copilot); one-line config swap to `claude-code-headless` (spawns `claude -p` on a direct Anthropic key) |
| `agent-session` | `copilot-cli` | worktree prepare/run/collect (same class as `executor`); `CopilotCli` subclasses `ClaudeCodeHeadless` and inherits its git/PR plumbing unchanged |
| `messaging` | `github-comment` | status/escalation comments |
| `gate` | `pr-review` | spec and architecture approval are both PR reviews on the artifact PR (D2) |
| `poll` | — | Protocol only (`engine.ports.Poll`); no adapter ships in P0 (D3) |
| `qa-env` | — | Protocol only (`engine.ports.QaEnv`); no adapter ships in P0 (D3) |
| `state-store` | `git-json` | fixed implementation, not a port (PD-7) — `engine.state.GitJsonStateStore` is constructed directly, never through the registry |

## Credential boundary (PD-5)

The child `claude` process (fallback `claude-code-headless` binding) gets an
env built key-by-key from an allowlist (`PATH`, `HOME`, `TMPDIR`, `LANG`,
`TERM`, `LC_*`, `CLAUDE_CONFIG_DIR`, `ANTHROPIC_API_KEY`) plus
`--disallowedTools WebFetch,WebSearch`. GitHub credentials (`AGENT_HQ_TOKEN`)
and the ambient `GITHUB_TOKEN`/`GH_TOKEN` never reach the child env —
`engine/adapters/claude_code_headless.py` asserts this at construction time
as a documented boundary, not real defense (the allowlist already makes
leakage structurally impossible; the assert just fails loudly if that ever
stops being true).

**Copilot-billed deviation (default binding, `copilot-cli`):** the child
`copilot` process gets the same style of from-scratch allowlist env (`PATH`,
`HOME`, `TMPDIR`, `LANG`, `TERM`, `LC_*`, `XDG_CONFIG_HOME`) but, unlike the
Anthropic-key child, it necessarily also holds a GitHub credential —
`COPILOT_GITHUB_TOKEN` — because Copilot CLI authenticates against a GitHub
Copilot seat rather than a model-provider API key. This is assessed and
accepted, not accidental: blast radius on compromise is that seat's account's
GitHub access, which the dedicated bot seat (Copilot access only, **no write
access** to any pilot or engine repo — see `docs/operations.md`) reduces to
"model access only". `AGENT_HQ_TOKEN` — the engine's own PAT — never reaches
the child process either way; `engine/adapters/copilot_cli.py` asserts
`AGENT_HQ_TOKEN`/`GITHUB_TOKEN`/`GH_TOKEN` stay out of the child env, same as
the fallback adapter.

**Stated honestly, this is a partial boundary.** The child process still runs
on the GitHub-hosted runner with that runner's filesystem and network access
— it can reach the internet directly (subject to `--disallowedTools`, which
is an application-level instruction to the CLI, not a network firewall).
Egress restriction requires self-hosted runners with an enforced network
allowlist, which is out of scope for P0 (see [`docs/roadmap.md`](roadmap.md)
§D, "Egress-restricted agent execution"). The NFR-SEC residual risk for the
pilot is: no GitHub/App/API credential can leak out of the child process, but
a compromised or misbehaving child agent is not network-isolated.

## Retry semantics (D1)

P0 has no checkpoint/resume. A killed or expired run is not resumed from a
saved session — it retries from scratch, bounded by the task's
`budget.retries`. `dispatch.yml`'s sweep re-drives runs left in `RUNNING`
with no active workflow (orphaned enqueues) into a fresh attempt, or marks
the ticket `BLOCKED` once retries are exhausted.

## Deviation ledger

The full decision record is `.hyperclaude/decisions/20260718-p0-scope-cut.md`
(gitignored — a local planning artifact, not part of the committed history).
Summarized here so this doc is self-contained:

1. **TE-11 waived** — no checkpoint/resume; see "Retry semantics" above.
2. **Gates: `pr-review` only** — no `github-environment` native-approval
   adapter in P0; both spec and architecture approval are PR reviews.
3. **Six adapters, not eight** — `poll` (`github-issue-reactions`) and
   `qa-env` (`docker-compose`) ship as Protocols only; no P0 task consumes
   them.
4. **Fine-grained PAT, not a GitHub App** — one `AGENT_HQ_TOKEN` secret
   scoped to the pilot repos, not a dedicated least-privilege App
   installation.
5. **Serialized state writes, not transactions** — the `agent-hq-state`
   Actions concurrency group serializes writes; no reload-and-reapply
   conflict resolution.
6. **Minimal dashboard** — one static state table (ticket/run, spend,
   artifact/PR links, waiting-on-humans), not the full kanban/timeline/spend
   breakdown view.
7. **Operational extras cut** — no monthly budget alerts, no CI-green
   auto-undraft sweep, no `pull_request: closed` closing-summary path, no
   gate half-timeout alerts.
8. **Devcontainer kept for the agent job** — `run.yml`'s execute job still
   runs `scripts/run-phases.sh` inside the project devcontainer via
   `devcontainers/ci` (Codespaces parity honored), even though lighter jobs
   (intake/dispatch/pages/CI) use direct setup.
9. **Copilot-billed executor by default** — `executor`/`agent-session` bind
   to `copilot-cli` (spawns `copilot -p ... --model claude-sonnet-4.5`,
   billed through a dedicated GitHub Copilot seat), not
   `claude-code-headless` (direct Anthropic API key), which stays registered
   as a one-line-swap fallback. Copilot's premium-request subscription
   billing has no per-run USD metering, so runs record `cost_usd: 0.0`,
   `usage_known: true` — per-ticket USD budget caps (`budgets.yml`) don't
   bind under this binding; runaway work is still bounded by
   `budget.retries`, the loop guard (25 runs / depth 12), the in-flight cap,
   and runtime deadlines (see "Credential boundary" above for the PD-5
   assessment of the resulting `COPILOT_GITHUB_TOKEN` in the child env).

See [`docs/roadmap.md`](roadmap.md) for restore triggers on each of these.
