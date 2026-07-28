# Specification: Display patient age on encounter page using clinical age-format rules

## Problem Statement

The encounter page's patient card currently displays patient age using a simplified format: years only for patients above 1 year, and months + days for those below 1 year. This does not meet clinical requirements for precision at different age ranges. The Clinical Team requires age display to follow medical conventions that provide appropriate granularity for each developmental stage, with hover tooltips showing full breakdown.

## Acceptance Criteria

1. Given a patient aged 0–28 days, when viewing the encounter card, then age displays as "N days" (e.g., "15 days").

2. Given a patient aged 29 days to 1 year, when viewing the encounter card, then age displays as "N weeks M days" (e.g., "8 weeks 3 days").

3. Given a patient aged 1–2 years, when viewing the encounter card, then age displays as "N months M days" (e.g., "15 months 10 days").

4. Given a patient aged 2–18 years, when viewing the encounter card, then age displays as "N years M months" (e.g., "5 years 7 months").

5. Given a patient aged above 18 years, when viewing the encounter card, then age displays as "N years" only (e.g., "42 years").

6. Given any patient age displayed on the encounter card, when hovering over the age text, then tooltip shows full breakdown as "X years, Y months, Z days".

7. Given a deceased patient with `deceased_datetime` set, when calculating age, then calculations use `deceased_datetime` as the end date instead of current date.

## Capability Notes

- `src/Utils/utils.ts:formatPatientAge` — exists; current implementation supports years/months/days logic but needs updating to clinical format rules
- `src/components/Encounter/EncounterInfoCard.tsx` — exists; line 67 calls `formatPatientAge(encounter.patient, true)` with abbreviated flag
- `src/components/ui/tooltip.tsx` — exists; shadcn/ui Tooltip component available for hover display
- `dayjs` library — already imported in `src/Utils/utils.ts`; provides date difference calculations needed for weeks/months/years
- Deceased patient handling — exists in `formatPatientAge` at lines 159-162; already calculates age using `deceased_datetime` when present

## Open Questions

None.
