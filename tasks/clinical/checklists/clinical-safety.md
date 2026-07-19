# Clinical safety checklist

Before finishing `specs/{ticket}/clinical.md`, confirm:

- [ ] The "is it clinical" call is justified: does the ticket touch
      clinical logic, terminology, care workflows, FHIR shapes, or
      health-data fields? If not, the reasoning for "no clinical change"
      is stated, not assumed.
- [ ] Every new or changed clinical field has a terminology binding
      (SNOMED CT / LOINC / ICD-10) -- no field left unbound.
- [ ] Patient-safety failure modes are enumerated, not just the happy path.
- [ ] Applicable national standard treatment guidelines / programme
      guidance are cited by name, not paraphrased from memory.
- [ ] Zero PHI -- every example, code snippet, and fixture uses synthetic
      data only.
