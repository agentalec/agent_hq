---
name: hq-doctor
description: Verify an agent_hq deployment's setup and report a PASS/FAIL checklist with the fix for each failure. Use when asked to "check the deployment", "is the setup correct", "run hq doctor", "why isn't intake firing", after rotating credentials, or after standing up a new instance with hq-config / docs/setup-new-repo.md.
---
# hq-doctor

Run read-only checks against the engine repo, config, and GitHub, then report one PASS/FAIL line per check with the fixing doc section for each failure.

## Steps

Read `config/projects.yml` first — `engine_repo` (call it `<engine>`) and the label values drive most checks. If it still says `example-org/agent-hq`, checks 1, 3, 4, and 7 cannot run against a real repo; report that as the headline failure (fix: docs/setup-new-repo.md §3, or use `hq-config`).

1. **Repo shape.** `gh repo view <engine> --json visibility,defaultBranchRef` — must be public with default branch `main`. Then `git fetch origin main && git ls-tree origin/main .github/workflows/` — `intake.yml`, `dispatch.yml`, `run.yml`, `pages.yml` must all be present on `main`. Event triggers and the hardcoded run-dispatch `"ref": "main"` resolve against the default branch, so workflows only on a feature branch means nothing executes. Fix: docs/setup-new-repo.md §2.

2. **Config.** `.venv/bin/agent-hq config validate && .venv/bin/agent-hq tasks validate`, then `grep -rn "example-" config/ | grep -vE ':[0-9]+:\s*#'` — any remaining hit is a leftover placeholder (hits on comment lines are benign — the shipped comments mention `example-*` — only hits in values count; validate checks shape only, not that values are real). Fix: docs/setup-new-repo.md §3, docs/operations.md §4.

3. **Labels.** `gh label list --repo <engine> -L 200` (the default limit is 30 — without `-L` a label past the first page false-fails) must contain the configured `intake_label`, `public_safe_label`, and every `intake.excluded_labels` value from `config/projects.yml` — read the actual values, do not assume `hq:*`. GitHub never auto-creates labels; a missing label cannot be applied at intake. Fix: docs/setup-new-repo.md §5.

4. **Secrets and variables.** `gh secret list --repo <engine>` must show `AGENT_HQ_TOKEN` and `AGENT_HQ_COPILOT_TOKEN`, plus `ANTHROPIC_API_KEY` if `config/components.yml` binds `executor`/`agent-session` to `claude-code-headless`. `gh variable list --repo <engine>` — `AGENT_HQ_KILL_SWITCH` should be absent or not `1`; if it is `1`, dispatch is paused. Note in the report: only secret *presence* is checkable — a silently expired PAT surfaces as `checkout-state.sh` auth failures or 401s in intake/dispatch runs (docs/operations.md §1). Fix: docs/setup-new-repo.md §4, docs/operations.md §1–2.

5. **Work repos.** For each repo in `config/repos.yml`: `gh repo view <repo> --json visibility` — must exist and be public (the credential-free `execute` job clones it unauthenticated), and `git ls-remote https://github.com/<repo>.git refs/heads/<base_branch>` must return a ref. Fix: docs/setup-new-repo.md §1, §3.

6. **Approvers.** For each username in every `config/approvers.yml` group: `gh api users/<login>` — 404 means the account does not exist and its gate decisions silently never count. Warn even on PASS: existence is not intent — confirm these are the humans who should hold the gates. Fix: docs/setup-new-repo.md §3.

7. **Pages.** `gh api repos/<engine>/pages` — a 404 means Pages is not enabled and the dashboard will never deploy. Fix: enable via Settings > Pages > Source: GitHub Actions (docs/setup-new-repo.md §2).

8. **State branch (INFO, never FAIL).** `git ls-remote origin agent-hq-state` — absent is fine before the first intake: `scripts/checkout-state.sh` self-bootstraps it (docs/operations.md §3). Report "no deployment state yet" as INFO. If it exists and looks damaged, use `hq-recover`, not this skill.

9. **Offer, do not run unprompted** (slow, needs live credentials): the docs/operations.md §5 manual integration checks — a `checkout-state.sh` round-trip, one real `copilot -p` run, and a devcontainer build.

Finish with the checklist: one line per check, `PASS` / `FAIL` / `INFO`, each FAIL followed by its one-line fix and doc section.

## Hard rules

- Read-only. Never create labels, set secrets or variables, or enable Pages — print the exact `gh` command for the operator to run instead.
- Never print or echo a secret value; report presence/absence only.
- Report every check even after an early failure — the operator wants the full picture, not the first error.
- Do not hardcode label names or repo names; always read them from `config/*.yml`.

## References

- docs/setup-new-repo.md — zero-to-first-ticket runbook (the fix for most failures)
- docs/operations.md §1–6 — credentials, secrets table, state bootstrap, placeholders, manual checks, kill switch
- Related skills: `hq-config` (edit config), `hq-recover` (repair state), `hq-ticket` (follow a live ticket)
