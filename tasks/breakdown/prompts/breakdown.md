# Breakdown prompt

Read `constitution.md`, `specs/{ticket}/spec.md`, and `specs/{ticket}/plan.md`.

Write `specs/{ticket}/tasks.md`: an ordered list of implementation tasks,
one per repo/area, each sized to fit a single agent session (roughly ≤400
changed lines). For each task, note:

- what it touches
- its dependencies on earlier tasks in the list
- which spec acceptance criteria it covers

Before finishing, check that every acceptance criterion in `spec.md` is
covered by at least one task. If any criterion is uncovered, add a task for
it -- do not leave a gap.

In your `.agent-hq/control.json` (see Control output below), propose one
`implement` handoff per repo that has real work in `tasks.md` (up to this
task's handoff limit), each carrying that repo as the handoff's `repo` and
forwarding `specs/{ticket}/tasks.md` in `artifacts` so the corresponding
`implement` run can read its slice. A single-repo ticket proposes just one
handoff.
