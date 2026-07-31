# Arch-plan prompt

Read `constitution.md` and `specs/{ticket}/spec.md`.

Write `specs/{ticket}/plan.md`: the implementation approach, repos touched,
and any new dependency with a one-line justification.

Then write `specs/{ticket}/classification.json`:

    {"classification": "beyond-crud" | "crud", "reasoning": "..."}

Classify `beyond-crud` if ANY apply, else `crud`:

- new data models or migrations
- changes to existing model fields
- new services, workers, or infrastructure
- new external integrations
- authorization/access-control changes
- FHIR/EMR model changes
- non-CRUD endpoints (side effects beyond create/read/update/delete)
- clinical-safety-relevant behavior

`reasoning` must name the criterion that applied, or say none did.

In your `.agent-hq/control.json` (see Control output below), queue exactly one
entry: `arch-approval` if you classified `beyond-crud`, otherwise `breakdown`.
Forward `specs/{ticket}/plan.md` (and any input you were given that the next
task still needs, e.g. `specs/{ticket}/spec.md`) in that entry's `artifacts`.
