# Docs prompt

Read `constitution.md`, `specs/{ticket}/spec.md`, and `specs/{ticket}/qa.md`
if it exists.

Update the user and developer docs for this change under the target repo's
own `docs/` directory, plus a changelog entry. Include screenshots from the
QA run when they're available.

Docs/spec/tests drift is a BLOCKER: if the docs you'd write would contradict
`spec.md` or the shipped tests, stop -- do not paper over the mismatch.
Instead record the drift in `specs/{ticket}/docs.md` and leave the docs
files unchanged.

Otherwise, record what changed and where in `specs/{ticket}/docs.md`.

Run through `checklists/docs-drift.md` before finishing.
