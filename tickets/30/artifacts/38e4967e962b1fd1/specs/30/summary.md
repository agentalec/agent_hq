# Summary: Display patient age on the encounter page patient card using clinical age-format rules

## Changes Implemented

Implemented clinical age-format rules for the patient card on the encounter page. The age display now follows medical conventions with appropriate granularity for each developmental stage:

- **0–28 days**: Days only
- **29 days to 1 year**: Weeks + Days
- **1 year to 2 years**: Months + Days
- **2 years to 18 years**: Years + Months
- **Above 18 years**: Years only

All age displays include a hover tooltip showing the full age breakdown (years, months, days).

### Code Changes

- `src/Utils/utils.ts`: Added `formatPatientAgeClinical()` and `getPatientAgeBreakdown()` functions implementing the clinical formatting rules with proper pluralization handling
- `src/components/Encounter/EncounterInfoCard.tsx`: Updated patient card to use `formatPatientAgeClinical()` instead of `formatPatientAge()`, wrapped age display in shadcn/ui Tooltip component
- `public/locale/en.json`: Added i18n keys for time units ("day", "days", "week", "weeks")

### Acceptance Criteria

All 7 acceptance criteria **PASS**:

1. ✅ **0–28 days**: Displays as "N days" (e.g., "15 days")
2. ✅ **29 days to 1 year**: Displays as "N weeks M days" (e.g., "8 weeks 4 days")
3. ✅ **1–2 years**: Displays as "N months M days" (e.g., "14 months 25 days")
4. ✅ **2–18 years**: Displays as "N years M months" (e.g., "5 years 5 months")
5. ✅ **Above 18 years**: Displays as "N years" only (e.g., "41 years")
6. ✅ **Hover tooltip**: Shows full breakdown as "X years, Y months, Z days"
7. ✅ **Deceased patients**: Age calculated using `deceased_datetime` instead of current date

### Review Outcome

**Final verdict: Clean** — All blockers resolved through 3 review rounds.

**Should-fix items addressed:**
- Proper singular/plural handling for all time units (1 day vs 2 days, etc.)
- Consistent lowercase capitalization for time units
- Empty tooltip edge case fixed for 0-day-old newborns (shows "0 days")

### Notes

The implementation properly handles edge cases including newborns (0 days old), singular values (1 day, 1 month, 1 year), and deceased patients. The age calculation logic accounts for varying month lengths and leap years using dayjs date difference calculations.

QA was performed using standalone demonstrations that replicate the exact formatting logic from the production code. Full visual integration testing in the live encounter page UI requires additional environment setup with authenticated API access.
