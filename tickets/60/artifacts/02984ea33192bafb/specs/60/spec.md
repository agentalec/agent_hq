# Spec: Display patient age on encounter page using clinical age-format rules

## Problem statement

The encounter page patient card currently displays patient age using a simplified format: years only for ages above 1 year, and months + days for ages below 1 year. This does not meet clinical field requirements for age precision across different developmental stages. The Clinical Team requires a more granular age display format that varies by age range to support accurate clinical decision-making for pediatric and adult care.

## Acceptance criteria

1. Given a patient aged 0–28 days, when viewing the encounter card, then display age as days only (e.g., "14 days").
2. Given a patient aged 29 days to 1 year, when viewing the encounter card, then display age as weeks + days (e.g., "12 weeks 3 days").
3. Given a patient aged 1 year to 2 years, when viewing the encounter card, then display age as months + days (e.g., "18 months 15 days").
4. Given a patient aged 2 years to 18 years, when viewing the encounter card, then display age as years + months (e.g., "5 years 8 months").
5. Given a patient aged above 18 years, when viewing the encounter card, then display age as years only (e.g., "42 years").
6. Given any patient age on the encounter card, when hovering over the displayed age, then show a tooltip with the complete breakdown in years, months, and days.
7. Given the abbreviated age format is requested, when displaying age, then use shortened suffixes: "d" for days, "w" for weeks, "mo" for months, "Y" for years.

## Capability notes

- `src/Utils/utils.ts:formatPatientAge` — exists; current implementation displays years for ages ≥1 year, months + days for ages <1 year
- `src/components/Encounter/EncounterInfoCard.tsx:67` — exists; calls `formatPatientAge(encounter.patient, true)` to display abbreviated age on encounter card
- `src/components/ui/tooltip.tsx` — exists; Radix UI Tooltip component available for hover functionality
- `src/Utils/utils.ts:getRelativeDateSuffix` — exists; provides abbreviated suffixes for day/month/year units; needs extension for weeks
- `dayjs` calculation utilities — exist; used throughout `formatPatientAge` for date difference calculations

## Open questions

None.
