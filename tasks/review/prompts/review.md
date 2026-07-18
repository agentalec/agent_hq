# Review prompt

Read `constitution.md`, `specs/{ticket}/spec.md`, `specs/{ticket}/plan.md`,
and **`.agent-hq/diff.patch`** — the full diff the implement task produced,
materialized for you by the engine (your worktree is checked out at the
implement result, and you have no git tool).

Check the diff against the spec and plan. Classify each finding `blocker`,
`should-fix`, or `nit`.

Also run:
- an over-engineering pass -- flag speculative abstractions, unused
  flexibility, or code for scenarios that can't happen here
- a security pass -- hardcoded secrets, injection points, missing authz
  checks, and any new dependency without a stated justification

Write findings to `specs/{ticket}/review.md`, grouped by severity. Your
tools are read-only -- do not edit the implementation.
