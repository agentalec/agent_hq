# Spec prompt

Read `constitution.md` for repo conventions and the `specs/{ticket}/` layout.

Write `specs/{ticket}/spec.md` for this ticket:

- Problem statement, 2-3 sentences.
- Testable acceptance criteria, phrased as Given/When/Then.
- Capability notes: what the repo already supports vs what needs building --
  name real files/functions, don't guess.
- Open questions, each tagged `[open]`, with who or what would resolve it.

Run through `checklists/spec-quality.md` before finishing.

In your `.agent-hq/control.json` (see Control output below), propose one
`implement` handoff per repo that has real work in the spec (up to this
task's handoff limit), each carrying that repo as the handoff's `repo` and
forwarding `specs/{ticket}/spec.md` in `artifacts` so the corresponding
`implement` run can read it. A single-repo ticket proposes just one handoff.
Emit `{"outcome": "complete"}` only when the ticket needs no change at all --
and say why in the spec.

Do not write outside `specs/{ticket}/`. Do not implement code -- this task
only produces the spec.
