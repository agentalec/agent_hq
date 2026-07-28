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
file on round 1). Keep every prior round's section intact; only append.

## What goes in the section

Your `## Round N` section is posted verbatim as a comment on the work-repo
PR, and the whole accumulated file goes to the ticket thread if the rounds
run out. Write findings, not a report — never restate the diff or the spec.

Check the diff against the spec's acceptance criteria. **One line per
finding**, grouped by severity, each naming a location and the fix:

```
- **blocker** `src/Utils/utils.ts:42` — off-by-one on the month boundary; use `>=`.
```

Also read the diff through an over-engineering lens (speculative
abstractions, unused flexibility, code for scenarios that can't happen here)
and a security lens (hardcoded secrets, injection points, missing authz
checks, any new dependency without a stated justification). Anything they
surface is a finding in the same severity list — not its own section, and not
a line saying you looked and found nothing.

At most 3 `nit`s, and only where the fix is one line; unsaid taste is fine.
If the round finds nothing at all, the entire section is `Clean — no
findings.`

Never edit the implementation — your tools are read-only.

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
