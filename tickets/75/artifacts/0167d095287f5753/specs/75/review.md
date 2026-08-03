# Review Findings

## Round 1

- **blocker** `src/components/Patient/PatientRegistration.tsx:203` — `required` parameter logic is inverted; should be `minGeoOrganizationLevelsRequired != null` instead of `== null` (when min level is null, organization is NOT required).
- **should-fix** `tests/PLAYWRIGHT_GUIDE.md:37-54` — Markdown formatting broken with concatenated backticks; restore proper line breaks and formatting for code examples.
