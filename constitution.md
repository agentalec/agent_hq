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

## Agent rules

- **Structured control output** -- every task run ends by writing exactly
  one control outcome to `.agent-hq/control.json` (`handoff`, `complete`, or
  `blocked`); never end silently, and never invent a fourth outcome.
- **Explicit repository targets** -- work only inside the repository the
  engine names for this run (the injected `run.repo`, resolved from
  configured `repos.yml` entries); never guess, infer, or touch a repository
  the run wasn't scoped to.
- **Public-safe artifacts** -- assume every artifact, comment, and handoff
  reason is public; never write secrets, credentials, or content that isn't
  safe for a public issue, PR, or Pages site.
- **No direct mutation** -- agents propose, they never execute: no editing
  the run queue, triggering workflows, reading/writing secrets, or changing
  repository permissions directly. A handoff is a proposal the engine
  validates and applies -- it is never a queue edit performed by the agent
  itself.

## Engineering conventions

- Every implementation task ships tests for the code it adds.
- Commits are Conventional Commits (`feat:`, `fix:`, `test:`, `chore:`, ...).
- No secrets in code, config, or commit messages -- credentials come from
  environment variables, never files under version control.
- Work branches are named `agent-hq/<issue-number>` -- one stable branch per
  ticket per repository, reused by every task on that ticket.
