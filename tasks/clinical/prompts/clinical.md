# Clinical prompt

Read `constitution.md` and `specs/{ticket}/spec.md`.

Always write `specs/{ticket}/clinical.md`. There are exactly two valid
shapes for it:

1. **No clinical change** -- an explicit statement that this ticket does not
   touch clinical logic, terminology, care workflows, FHIR shapes, or
   health-data fields, with the reasoning for why not.
2. **Full clinical detailing**, covering:
   - Affected workflow -- actor, setting, sequence of events.
   - Terminology bindings -- SNOMED CT / LOINC / ICD-10 codes for any new
     or changed clinical fields.
   - References to the applicable national standard treatment guidelines
     (the guideline set is configuration per requirements §7 — until a
     config key exists, name the guideline + edition you relied on so a
     reviewer can verify it)
     and programme guidance.
   - Patient-safety failure modes and how they're mitigated.

Use synthetic data only in every example, code snippet, and fixture --
never real patient data.

Run through `checklists/clinical-safety.md` before finishing.
