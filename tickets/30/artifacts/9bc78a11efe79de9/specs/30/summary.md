# Summary: Display patient age on encounter page using clinical age-format rules

## What was done

Updated the encounter page patient card to display patient age using clinical age-format rules that provide appropriate granularity for each developmental stage. The implementation replaces the simplified "years only / months+days" format with medical conventions:

- **0–28 days:** Days only (e.g., "15 days")
- **29 days to 1 year:** Weeks + Days (e.g., "8 weeks 3 days")
- **1–2 years:** Months + Days (e.g., "15 months 10 days")
- **2–18 years:** Years + Months (e.g., "5 years 7 months")
- **Above 18 years:** Years only (e.g., "42 years")

Additionally:
- Hover tooltips now show the full age breakdown as "X years, Y months, Z days"
- Deceased patients correctly use `deceased_datetime` for age calculations
- Proper singular/plural forms for all time units (e.g., "1 day" vs "2 days")

## Acceptance criteria

All 7 acceptance criteria are met:
- ✅ AC1-5: Age format rules implemented for all age ranges
- ✅ AC6: Tooltip shows full breakdown with years, months, days
- ✅ AC7: Deceased patient handling uses `deceased_datetime`

## Review outcome

**Final review: Clean** (Round 3) — All blockers and should-fix items from earlier rounds were addressed:
- Fixed empty tooltip for 0-day-old patients
- Corrected plural forms to use singular/plural grammar appropriately
- Normalized capitalization across all age terms

## QA outcome

**Partial Pass with Limitations** — Implementation verified through code review and testing with existing fixture data showing adult patients (18+). Age ranges 0-18 years could not be exercised with screenshots due to API constraints preventing test encounter creation, but code review confirms all logic branches correctly implement the clinical age-format rules.

**Recommendation:** Perform end-to-end verification of younger age ranges in staging environment before production deployment.

## Files changed

- `src/Utils/utils.ts` — Created `formatPatientAgeClinical()` function with clinical age-format logic
- `src/components/Encounter/EncounterInfoCard.tsx` — Integrated tooltip display for patient age
- `public/locale/en.json` — Added i18n keys for time units (day, days, week, weeks, month, months, year, years)
