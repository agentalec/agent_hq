# Summary: Display patient age on encounter page using clinical age-format rules

## What was done

Implemented clinical age-format rules for patient age display on the encounter page patient card. The age format now varies by developmental stage to support accurate clinical decision-making:

- **0–28 days:** Display days only (e.g., "14d")
- **29 days to 1 year:** Display weeks + days (e.g., "12w 3d")
- **1 year to 2 years:** Display months + days (e.g., "18mo 15d")
- **2 years to 18 years:** Display years + months (e.g., "5Y 8mo")
- **Above 18 years:** Display years only (e.g., "42Y")

Added tooltip on hover showing complete age breakdown in years, months, and days.

## Changes

- Updated `formatPatientAge()` in `src/Utils/utils.ts` to implement clinical age-format logic
- Added `getFullAgeBreakdown()` helper function for tooltip content
- Extended `getRelativeDateSuffix()` to support weeks abbreviation
- Modified `EncounterInfoCard.tsx` to wrap age display with Tooltip component
- Added i18n key `age_full_breakdown` for tooltip format

## Acceptance criteria

**Met:**
- ✅ AC1: 0–28 days display as days only
- ✅ AC2: 29 days to 1 year display as weeks + days
- ✅ AC3: 1 year to 2 years display as months + days
- ✅ AC4: 2 years to 18 years display as years + months
- ✅ AC5: Above 18 years display as years only
- ✅ AC7: Use abbreviated suffixes (d, w, mo, Y)

**Not fully exercised:**
- ⚠️ AC6: Tooltip hover functionality — implementation verified in code review, but automated testing could not reliably trigger tooltip in Playwright. Manual verification recommended.

## Review outcome

Clean after round 2. All blockers resolved:
- Fixed `getFullAgeBreakdown()` to include zero values for complete breakdown
- Reverted unintentional formatting changes to test documentation
