# Review prompt

Read `constitution.md`, `specs/{ticket}/spec.md`, and **`.agent-hq/diff.patch`**
— the changes the most recent `implement` round produced (materialized for
you by the engine; your worktree is checked out at the implement result and
you have no git tool).

## Round memory

If `specs/{ticket}/review.md` was handed to you, read it first — it holds the
findings from earlier rounds as `## Round 1`, `## Round 2`, … sections. This
is round **N = (number of existing `## Round` sections) + 1**.

Append a new `## Round N` section to `specs/{ticket}/review.md` (create the
file on round 1). In it, check the diff against the spec's acceptance
criteria and classify each finding `blocker`, `should-fix`, or `nit`, grouped
by severity. Also run:
- an over-engineering pass — flag speculative abstractions, unused
  flexibility, or code for scenarios that can't happen here
- a security pass — hardcoded secrets, injection points, missing authz
  checks, any new dependency without a stated justification

Never edit the implementation — your tools are read-only. Keep every prior
round's section intact; only append.

## Decide the handoff (see Control output below)

- **No blockers remain** (only should-fix / nits, or clean): hand off to
  `qa`, forwarding `specs/{ticket}/spec.md` and `specs/{ticket}/review.md`.
  QA exercises the change in a running app and screenshots it onto the PR
  before `finalize` — you do not hand off to `finalize` yourself.
- **Blockers remain and N < 3**: hand off to `implement`, forwarding
  `specs/{ticket}/spec.md` and `specs/{ticket}/review.md`; the handoff
  `reason` must name the blockers to fix.
- **Blockers remain and N == 3** (the round cap): do **not** hand off. Emit
  `{"outcome": "complete"}`. The engine posts your accumulated findings to
  the ticket thread and leaves the PR in draft for a human — do not loop a
  fourth implement round.
