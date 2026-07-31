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
recoverable. Your commits are squashed into one before they reach the work
repo, so the message that ends up on the branch is the `summary` you write in
`.agent-hq/control.json` (see Control output below) -- describe what you
actually changed there, not what the ticket asked for.

When the work is committed, queue a single `review` entry in your
`.agent-hq/control.json` (see Control output below), forwarding
`specs/{ticket}/spec.md` in `artifacts` -- and also `specs/{ticket}/review.md`
if it was given to you, so the reviewer keeps its round history.

Leave the rest of the ticket's queue alone: entries you do not mention stay
queued, and you have no reason to cancel work someone else planned.
