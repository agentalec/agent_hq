# Spec: Display patient age on encounter page using clinical age-format rules

## Problem

The encounter page's patient card displays age using a simplified format that does not align with clinical requirements. Currently, ages above 1 year show years only, and ages below 1 year show months and days. Clinical teams require developmental stage-appropriate age formatting that matches pediatric assessment standards.

## Acceptance Criteria

1. Given a patient is 0–28 days old, when viewing the encounter page, then display age as days only (e.g., "15 days").
2. Given a patient is 29 days to 1 year old, when viewing the encounter page, then display age as weeks + days (e.g., "8 weeks 4 days").
3. Given a patient is 1 year to 2 years old, when viewing the encounter page, then display age as months + days (e.g., "13 months 10 days").
4. Given a patient is 2 years to 18 years old, when viewing the encounter page, then display age as years + months (e.g., "5 years 3 months").
5. Given a patient is above 18 years old, when viewing the encounter page, then display age as years only (e.g., "42 years").
6. Given any patient age is displayed, when hovering over the age text, then show a tooltip with the full breakdown (years, months, days).
7. Given a patient is deceased, when viewing the encounter page, then calculate age using `deceased_datetime` instead of current date.

## Capabilities

- `src/Utils/utils.ts:formatPatientAge` -- needs building (clinical age-format logic)
- `src/Utils/utils.ts:getPatientAgeBreakdown` -- needs building (years/months/days calculation)
- `src/Utils/utils.ts:formatPatientAgeTooltip` -- needs building (tooltip format with full breakdown)
- `src/components/Encounter/EncounterInfoCard.tsx` -- exists (patient card displays age; update to use new formatter with tooltip)
- `tests/facility/patient/encounter/patientAgeDisplay.spec.ts` -- needs building (E2E tests for all age ranges)

## Open Questions

None.
