# Project review — 2026-07-21

## Verdict

The deterministic engine, schemas, idempotent event IDs, and local test suite
are a sound base. The pilot is not ready for untrusted or multi-repository
production tickets: intake cannot currently receive and preserve a
cross-repository issue identity, and the agent executes in the same job that
holds the engine's write credential.

## Findings

| Priority | Finding | Status / smallest correct next step |
|---|---|---|
| Blocker | `.github/workflows/intake.yml` only receives issue events from the engine repository, while `intake_repo()` reads the first configured product repository. A bare issue number is also used as the state key, so `repo-a#7` and `repo-b#7` collide and later reads can target the wrong repository. | Open. Use a GitHub App webhook or a tiny forwarding workflow in each product repo, pass `owner/repo#number`, and store a canonical repo-qualified source identity separately from the filesystem-safe ticket slug. |
| Blocker | `AGENT_HQ_TOKEN` is present in the devcontainer job while an unrestricted agent gets shell and network access. Removing the token from the direct child environment prevents accidental inheritance, but it is not a security boundary against a process that can inspect the same container or parent processes. | Open. Split prepare/execute/collect into separate jobs or use GitHub Agentic Workflows: agent job read-only and secret-free; output artifact; scoped write job. Do not run untrusted ticket text before this lands. |
| High | The global `agent-hq-state` job concurrency group covers the entire agent execution, not only state writes. A 90-minute task blocks intake and dispatch, and the configured in-flight cap of 3 is effectively 1. | Open. Keep short prepare/collect jobs under the state lock and run execute outside it, passing artifacts between jobs. |
| High | Task prompt/checklist files were validated but only their filenames reached the target-repo agent; required output paths were also absent. Finalize therefore had no instruction to create `summary.md`. | Fixed in this review: runtime prompt assembly now inlines instructions/constitution and lists substituted required outputs. |
| High | The review task denied every Copilot tool and omitted `Write`, although it must create `review.md`. | Fixed: Claude tool names map to Copilot `read`/`write`/`shell`, and review can write its declared artifact. |
| High | Finalize attempted `PATCH {"draft": false}` on the REST pull-request endpoint, which does not support changing draft state. | Fixed: fetch the PR node ID and call GraphQL `markPullRequestReadyForReview`; repeated calls are a no-op for an already-ready PR. |
| Medium | CI has no live GitHub, devcontainer, or Copilot smoke test; mocked REST tests cannot detect permission, CLI, billing, or workflow-event failures. | Open. Follow `docs/local-testing.md` in sandbox repos and add a scheduled sandbox canary after the two blockers are fixed. |
| Medium | Copilot CLI was pinned to `0.5.1` on Node 20, while current official installation requires Node 22 and a recent CLI. | Fixed: Node 22 and Copilot CLI 1.0.54 are pinned; the run script checks the documented `-p` interface. |
| Medium | Agent stdout/stderr and transcripts are discarded, making real failures difficult to diagnose. | Open. Upload a redacted `.agent-hq` diagnostic artifact on failure; do not commit it to the target branch. |
| Medium | Third-party Actions use mutable major tags, and idempotency lookups stop at 100 comments/reviews/runs. | Open, pilot ceiling. SHA-pin Actions before production; add Link-header pagination when a sandbox test exceeds the ceiling. |
| Low | Best-effort wake-up `curl` calls ignore all failures, so broken auth falls back silently to scheduled dispatch. Gate artifact PRs also remain open after approval. | Open. Add explicit warnings now; close/supersede artifact PRs when clutter becomes operationally visible. |

All 166 pre-change tests passed before edits; the post-change suite has 168
passing tests. The exact commands are documented in `docs/local-testing.md`.

## PAT answer

A PAT is not intrinsically required.

- The built-in `GITHUB_TOKEN` is short-lived and repository-scoped. It is
  enough for same-repository state/API work and can trigger
  `workflow_dispatch`/`repository_dispatch`, but it cannot access the other
  private pilot repositories.
- The current cross-repository P0 therefore needs `AGENT_HQ_TOKEN`; today that
  is a fine-grained PAT. The better production credential is a GitHub App
  installation token minted per job and limited to the configured repos.
- Copilot CLI can use built-in `GITHUB_TOKEN` with
  `copilot-requests: write`, which GitHub recommends for organization
  automation. Do this only after the agent is isolated in a read-only job;
  otherwise the same token also inherits that job's repository write scopes.
- Local Copilot testing should use `copilot login` OAuth. Copilot BYOK can run
  without GitHub authentication, but then provider authentication is still
  required.

## Recommended GitHub workflow shape

Keep agent_hq's deterministic task graph, causal IDs, state transitions, and
human gates. Replace only the privileged execution surface:

```text
prepare (short state lock + GitHub App token)
  -> sanitized prompt + source artifact
execute (no engine secret; contents read; copilot-requests write; firewall)
  -> patch/result artifact
collect (short state lock + scoped GitHub App token)
  -> validate outputs, push branch, create/update PR, record state
```

[GitHub's Copilot Actions guidance](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli-in-actions)
recommends GitHub Agentic Workflows instead of invoking Copilot directly.
[Agentic Workflows](https://github.github.com/gh-aw/) are still Public Preview,
so adopt them first as an `executor`/`agent-session` backend rather than
rewriting the engine. Their useful pieces are the
[read-only agent and safe-output write jobs](https://github.github.com/gh-aw/introduction/architecture/),
[network firewall](https://github.github.com/gh-aw/introduction/architecture/),
[built-in Copilot permission](https://github.github.com/gh-aw/reference/permissions/),
and [short-lived GitHub App tokens](https://github.github.com/gh-aw/reference/auth/).

The fallback, if Public Preview is unacceptable, is to reproduce the same
three-job boundary directly in `run.yml`. Do not preserve the current
single-job credential model.

## Official sources checked

- [Copilot CLI in GitHub Actions: authentication, billing, and recommendation](https://docs.github.com/en/copilot/concepts/agents/copilot-cli/copilot-cli-in-github-actions)
- [Using Copilot CLI with built-in GITHUB_TOKEN](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli-in-actions)
- [Copilot CLI authentication and supported token types](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli)
- [GITHUB_TOKEN scope and event behavior](https://docs.github.com/en/actions/concepts/security/github_token)
- [GitHub Agentic Workflows security architecture](https://github.github.com/gh-aw/introduction/architecture/)
- [GitHub Agentic Workflows authentication](https://github.github.com/gh-aw/reference/auth/)
- [REST pull-request update fields](https://docs.github.com/en/rest/pulls/pulls#update-a-pull-request)
- [GraphQL draft-to-ready mutation](https://docs.github.com/en/graphql/reference/mutations#markpullrequestreadyforreview)
