# Implement prompt

Read `constitution.md` and `specs/{ticket}/spec.md` (handed to you -- see
Available inputs below).

If `specs/{ticket}/review.md` was also handed to you, this is a re-implement
round: read its **latest** `## Round N` section and resolve every `blocker`
it raises (address `should-fix` items where reasonable). Otherwise implement
the spec from scratch.

Implement the spec's acceptance criteria that apply to your assigned
repository (see Work repo below); skip criteria scoped to a different
repo -- another `implement` run handles those. For each criterion that
applies:

- write the code and its tests
- commit with a Conventional Commits message (`feat:`, `fix:`, `test:`, ...)
- keep the diff scoped to that criterion; don't fold in unrelated changes

Never touch files outside your assigned repository. Commit as you go rather
than batching everything into one commit at the end.

When the work is committed, propose a single `review` handoff in your
`.agent-hq/control.json` (see Control output below), forwarding
`specs/{ticket}/spec.md` in `artifacts` -- and also `specs/{ticket}/review.md`
if it was handed to you, so the reviewer keeps its round history.
