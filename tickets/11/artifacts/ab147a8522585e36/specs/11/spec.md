# Display patient age on encounter page using clinical age-format rules

## Problem statement

The encounter page patient card currently displays patient age without following clinical standards. Healthcare workflows require age display that reflects developmental stages: neonatal (days), infant (weeks+days), toddler (months+days), pediatric (years+months), and adult (years only). This ensures clinicians can quickly assess age-appropriate protocols and dosing.

## Acceptance criteria

1. Given a patient aged 0–28 days, when viewing the encounter card, then display age as days only (e.g., "15 days").
2. Given a patient aged 29 days to 1 year, when viewing the encounter card, then display age as weeks + days (e.g., "8 weeks 3 days").
3. Given a patient aged 1 year to 2 years, when viewing the encounter card, then display age as months + days (e.g., "13 months 5 days").
4. Given a patient aged 2 years to 18 years, when viewing the encounter card, then display age as years + months (e.g., "5 years 3 months").
5. Given a patient aged above 18 years, when viewing the encounter card, then display age as years only (e.g., "42 years").
6. Given any patient age display, when hovering over the age, then show tooltip with full breakdown (years, months, days).
7. Given a deceased patient, when calculating age, then use deceased_datetime instead of current date as the end date.

## Capability notes

- `src/Utils/utils.ts:formatPatientAge()` -- exists; implements clinical age-format rules
- `src/Utils/utils.ts:getPatientAgeBreakdown()` -- exists; calculates years, months, days breakdown
- `src/Utils/utils.ts:formatPatientAgeTooltip()` -- exists; formats tooltip with full age breakdown
- `src/Utils/utils.ts:getRelativeDateSuffix()` -- exists; handles singular/plural forms and abbreviation
- `src/components/Encounter/EncounterInfoCard.tsx` -- exists; displays patient age on encounter card (line 67)

## Open questions

None.
