# Spec prompt

Read `constitution.md` for repo conventions and the `specs/{ticket}/` layout.

Write `specs/{ticket}/spec.md` for this ticket. It is posted verbatim as a
comment on the ticket issue -- write what a reviewer reads in one scroll, not
a document:

- Problem statement, 2-3 sentences.
- Testable acceptance criteria, at most 7, **one line each**, phrased
  `Given X, when Y, then Z.`
- Capability notes, at most 5 bullets, each naming a real path --
  `src/Utils/utils.ts:formatPatientAge -- exists` or `-- needs building`.
  Name real files/functions, don't guess. No prose tour of the codebase.
- Open questions that **block** an acceptance criterion, each tagged `[open]`
  with who or what resolves it. Nothing blocked: write `None.`

Keep the whole file under 400 words. If a section repeats another, cut it.

Run through `checklists/spec-quality.md` before finishing.

In your `.agent-hq/control.json` (see Control output below), queue one
`implement` entry per repo that has real work in the spec (up to this task's
queue limit), each carrying that repo as the entry's `repo` and forwarding
`specs/{ticket}/spec.md` in `artifacts` so the corresponding `implement` run
can read it. A single-repo ticket queues just one entry.

If the ticket needs no change at all, do not queue an empty queue -- an empty
queue from you reads as "the route finished here", which only the route's
final task may say. Emit `{"outcome": "blocked", "reason": "..."}` naming why
no change is needed, and say the same in the spec. A human confirms it.

Do not write outside `specs/{ticket}/`. Do not implement code -- this task
only produces the spec.
