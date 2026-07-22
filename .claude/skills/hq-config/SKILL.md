---
name: hq-config
description: Preview or update the agent_hq deployment configuration (config/*.yml - projects, repos, approvers, components, budgets). Use when the user says "show the config", "who can approve", "add a work repo", "change approvers", "swap the executor", "update budgets", or asks how intake routes tickets to repos.
---
# hq-config

Render the effective deployment configuration, or make a config edit and validate it — the five files in `config/` plus their consequences across `tasks/` and the engine repo.

## Steps

1. Pick the mode. No edit requested → PREVIEW. Any change requested → UPDATE (do the preview relevant to the field being changed first, so you edit with context).

### PREVIEW (default)

Read all five `config/*.yml` files, then report the *effective* configuration — resolved, cross-referenced, not raw yaml:

2. **Engine repo and intake** (`projects.yml`): `engine_repo` (the engine's own issue tracker — distinct from work repos), `intake_label`, `initial_task`, `intake.min_body_words`, `intake.excluded_labels`, and `public` / `public_safe_label` (when `public: true`, every ticket needs the safe label).
3. **Work repos** (`repos.yml`, keyed by `org/repo`): for each, show `product_area` — the routing keyword intake substring-matches against a ticket's title+body+labels to pick the target repo (`engine/engine.py:resolve_target_repo`; no match = ticket ineligible at intake) — plus `base_branch`, `branch_prefix`, `role`. Note which repos appear in `projects.yml:repos` (they must agree).
4. **Approvers** (`approvers.yml:groups`): each group with its members, AND which gate it decides — cross-reference `tasks/*/task.yml` `gates.post` entries (`approvers: <group>`; currently `spec` → `product-owners`, `arch-approval` → `architects`, `clinical` → `clinical-reviewers`). Call out `escalation` separately: it is always live (mentioned on every engine escalation), gate or no gate. Include `working_hours`.
5. **Component bindings** (`components.yml`): the adapter behind each port (`tracker`, `executor`, `agent-session`, `messaging`, `gate`), executor/agent-session `settings.model`, and gate logical names under `gate.named` (resolution precedence: allowlisted `hq:<port>=` ticket label → named gate binding → port default; `engine/config.py:resolve_binding`).
6. **Budgets** (`budgets.yml`): `ticket_cap_usd`, `in_flight_cap`, `loop_guard.max_runs` / `loop_guard.max_depth` — with the caveat that under the default `copilot-cli` binding, USD caps (`ticket_cap_usd`, per-task `budget.max_cost_usd`) do not bind because runs record `cost_usd: 0.0` (`docs/architecture.md`, deviation 9); retries, loop guard, in-flight cap, and runtime deadlines still do.
7. **Placeholder scan**: `grep -rn "example-" config/` — any hit means the deployment still has placeholder org/repo/username values (`docs/operations.md` §4) and is not live-ready.

### UPDATE

8. Work on a feature branch (`git status` first; never edit on `main`).
9. Make the edit, matching the field names above exactly (`schemas/*.schema.json` are the source of truth for shape).
10. Always run `.venv/bin/agent-hq config validate`. Also run `.venv/bin/agent-hq tasks validate` when the change touches `initial_task`, gate bindings/named gates, approver group names, or anything a `task.yml` references.
11. Check the two traps:
    - **Labels are not auto-created.** A new or renamed label (`intake_label`, `public_safe_label`, `excluded_labels`) must exist on the engine repo: `gh label list --repo <engine_repo>` and create it if missing (`docs/setup-new-repo.md` §5).
    - **Config is inert until merged to `main`.** Workflows and the run dispatch ref resolve against the default branch — an edit on a feature branch changes nothing until a human merges it.
12. If the change was a repo addition, remember the token consequence: `AGENT_HQ_TOKEN` must be scoped to the new work repo too (`docs/operations.md` §1-2).

## Hard rules

- Never commit to `main` directly — feature branch, human merge.
- Never put a concrete adapter name where a logical name is expected (task files and gate names stay logical; concrete adapters live only in `components.yml`).
- Approver usernames must be real GitHub logins — a wrong username means approvals silently never count.
- Validation checks shape, not truth: `config validate` passing does not mean the repos, users, or labels exist.

## References

- `docs/setup-new-repo.md` §3-5 — full field-by-field config walkthrough, secrets, labels.
- `docs/operations.md` §1-2 (credentials/secrets), §4 (placeholders), §6 (kill switch).
- `docs/architecture.md` — deviation ledger (deviation 9: Copilot billing vs USD caps).
- For run/ticket state repair use `hq-recover`; for deployment health checks use `hq-doctor`; for task-graph questions ("what triggers X") use `hq-task-graph`.
