# Spec: Hide SNOMED codes from observations on the patient overview

## Problem statement

The Patient Dashboard Overview displays SNOMED codes (e.g., "8310-5") alongside observation names in the vitals list and observations tab. These technical identifiers are meaningless to clinical users who rely on human-readable terms like "Body Temperature" during patient rounds. Showing both the display name and code clutters the interface, making it harder to scan critical patient data efficiently.

## Acceptance criteria

1. Given an observation with a `main_code` containing both `display` and `code`, when rendered in the observations tab, then only the `display` value is shown.
2. Given an observation with a `main_code` containing only a `code` and no `display`, when rendered in the observations tab, then the `code` value is shown as fallback.
3. Given a vital sign observation in the overview tab vitals table header, when the info popover is triggered, then the popover shows both the display name and code (e.g., "Body Temperature (8310-5)").
4. Given a vital sign observation in the overview tab vitals table header, when displayed without user interaction, then only the display name is shown, not the code.
5. Given an observation displayed in the ObservationHistoryTable component, when the code column is rendered, then only the `display` value is shown.
6. Given the underlying observation data structure, when observations are fetched or stored, then the `main_code.code` field remains unchanged in the data model.
7. Given any component that displays observations, when formatting for display, then no SNOMED codes appear in the primary UI unless explicitly required for debugging or administrative views.

## Capability notes

- `src/pages/Encounters/tabs/observations.tsx:160-164` -- displays `main_code?.display || main_code?.code || "unknown"`, needs updating to remove fallback to code in primary display
- `src/components/Common/Charts/ObservationHistoryTable.tsx:126-127` -- displays `display || code` fallback pattern, needs updating
- `src/components/Patient/vitals/VitalsTable.tsx:42-68` -- vitals table header shows display only; popover shows both display and code; this pattern is correct
- `src/types/emr/observation/observation.ts:56` -- defines `main_code?: Code | null` structure (system, code, display); structure remains unchanged
- `src/types/base/code/code.ts:19-23` -- Code interface defines display and code fields; exists

## Open questions

None.
