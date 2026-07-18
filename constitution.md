# Constitution

Conventions every agent-hq task and agent run follows.

## specs/<ticket>/ layout

Every ticket's working artifacts live under `specs/<ticket>/`:

- `spec.md` -- the specification (acceptance criteria, capability notes, open questions)
- `plan.md` -- the architecture/implementation plan
- `classification.json` -- `{"classification": "crud"|"beyond-crud", "reasoning": "..."}`
- `tasks.md` -- the ordered implementation breakdown
- `review.md` -- review findings
- `summary.md` -- the closing summary

Don't write ticket artifacts anywhere else, and don't touch another ticket's
`specs/` directory.

## Gates

- **Spec approval** -- `product-owners` review `spec.md` before `arch-plan` runs.
- **Architecture approval** -- `architects` review `plan.md`, but only when
  `classification.json` says `beyond-crud`. CRUD-classified tickets skip
  straight from `arch-plan` to `breakdown`.
- **Merge** -- always a human. No task auto-merges a PR.

## Engineering conventions

- Every implementation task ships tests for the code it adds.
- Commits are Conventional Commits (`feat:`, `fix:`, `test:`, `chore:`, ...).
- No secrets in code, config, or commit messages -- credentials come from
  environment variables, never files under version control.
- Branches are named `agent-hq/<run_id>`.
