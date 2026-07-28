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
- commit it
- keep the diff scoped to that criterion; don't fold in unrelated changes

Never touch files outside your assigned repository. Commit as you go rather
than batching everything at the end -- it keeps your own working state
recoverable. Your commits do not reach the work repo individually, though:
the engine squashes this run into one commit and writes its message from the
ticket, so don't spend effort composing them.

When the work is committed, propose a single `review` handoff in your
`.agent-hq/control.json` (see Control output below), forwarding
`specs/{ticket}/spec.md` in `artifacts` -- and also `specs/{ticket}/review.md`
if it was handed to you, so the reviewer keeps its round history.
