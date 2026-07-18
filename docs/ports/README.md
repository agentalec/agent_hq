# Ports and adapters (§4)

Every side effect the engine performs crosses one of these ports. Task
definitions and engine code bind to a port, never to a concrete adapter
(PA-2); `engine.registry.build_adapter(port, adapter_name, settings)`
resolves the config-selected adapter at runtime. `engine.ports` declares the
structural (`typing.Protocol`) contract for each port -- adapters implement
matching methods, no inheritance required.

`state-store` is not a port (PD-7): it's a single fixed implementation,
`engine.state.GitJsonStateStore`, constructed directly. See
[`state-store.md`](state-store.md).

## Roadmap

| Port | Canonical (P0) | Staged | Direct (planned) |
|---|---|---|---|
| `tracker` | `github-issues` | `jira-mirror` (P1) | `jira-direct` (P2) |
| `executor` | `claude-code-headless` | `copilot-coding-agent`, `claude-partner-agent` (P1) | Codex, Jules |
| `agent-session` | `claude-code-headless` | `copilot-cli` | -- |
| `messaging` | `github-comment` | `slack-message` (P1) | email |
| `poll` | -- (protocol only, D3) | `github-issue-reactions`, `slack-reactions` (P1) | `slack-buttons` (P2) |
| `gate` | `pr-review` | `github-environment` (P1) | `jira-transition`, `slack-approval` |
| `qa-env` | -- (protocol only, D3) | `docker-compose` (P1) | `prebuilt-image` (P2), `remote-preview-env` |
| `state-store` | `git-json` (fixed, not a port) | -- | -- |

**PA-1**: a written contract per port (this directory) covers inputs,
outputs, error semantics, idempotency expectations; a contract change
applies to every adapter of that port.
**PA-2**: adapter selection is pure configuration (`config/components.yml`);
swapping adapters touches zero task-definition and zero engine code.
**PA-3**: P0 records adapter health from outcomes of adapters a run actually
exercised (`health/latest.json`), not a scheduled healthcheck sweep (D3
defers PA-3's scheduled form to P1).

## Files

- [tracker.md](tracker.md)
- [executor.md](executor.md)
- [agent-session.md](agent-session.md)
- [messaging.md](messaging.md)
- [poll.md](poll.md)
- [gate.md](gate.md)
- [qa-env.md](qa-env.md)
- [state-store.md](state-store.md)
