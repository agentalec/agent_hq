# Implementation Plan: Display patient age on encounter page using clinical age-format rules

## Overview

This is a frontend-only change to improve the patient age display on the encounter page's patient card. All required utility functions (`formatPatientAge`, `getPatientAgeBreakdown`, `formatPatientAgeTooltip`, `getRelativeDateSuffix`) already exist in `src/Utils/utils.ts` and implement the clinical age-format rules correctly. The implementation simply needs to add a tooltip to the existing age display.

## Repositories Touched

- **agentalec/care_fe** — Frontend repository where the encounter card lives

## Implementation Approach

### 1. Update EncounterInfoCard Component

**File:** `src/components/Encounter/EncounterInfoCard.tsx`

The component currently displays patient age at line 67:
```typescript
{formatPatientAge(encounter.patient, true)}
```

**Changes required:**
1. Wrap the age text with a Tooltip component from `src/components/ui/tooltip.tsx` (shadcn/ui)
2. Set the tooltip content to use `formatPatientAgeTooltip(encounter.patient, false)` to show the full age breakdown (years, months, days)
3. Ensure the tooltip appears on hover as specified in acceptance criteria #6

**Implementation pattern:**
```typescript
<Tooltip>
  <TooltipTrigger className="cursor-default">
    {formatPatientAge(encounter.patient, true)}
  </TooltipTrigger>
  <TooltipContent>
    {formatPatientAgeTooltip(encounter.patient, false)}
  </TooltipContent>
</Tooltip>
```

### 2. Verify Utility Functions

The following functions in `src/Utils/utils.ts` already implement the clinical age-format rules per spec:

- **`formatPatientAge(obj, abbreviated)`** (lines 245-306)
  - 0-28 days: Shows days only ✓
  - 29 days to 1 year: Shows weeks + days ✓
  - 1 year to 2 years: Shows months + days ✓
  - 2 years to 18 years: Shows years + months ✓
  - Above 18 years: Shows years only ✓
  - Handles deceased patients correctly using `deceased_datetime` ✓

- **`getPatientAgeBreakdown(obj)`** (lines 177-199)
  - Calculates years, months, days breakdown ✓
  - Handles deceased patients correctly ✓

- **`formatPatientAgeTooltip(obj, abbreviated)`** (lines 208-232)
  - Formats full age breakdown as "X years, Y months, Z days" ✓
  - Handles edge cases (0 values, abbreviated format) ✓

- **`getRelativeDateSuffix(count, unit, abbreviated)`** (lines 140-170)
  - Handles singular/plural forms ✓
  - Supports abbreviated format ✓

No changes needed to these utility functions.

### 3. Testing Strategy

**Manual testing:**
- Test all age ranges specified in acceptance criteria (0-28 days, 29 days-1 year, 1-2 years, 2-18 years, 18+ years)
- Verify hover tooltip shows full breakdown
- Verify deceased patients use deceased_datetime for age calculation

**Playwright E2E tests:**
- Add test cases to verify age display format for different age ranges
- Add test case to verify tooltip content on hover
- Add test case to verify deceased patient age calculation

Test file location: `tests/facility/encounter/` (create new test file or extend existing encounter tests)

## Dependencies

No new dependencies required. Uses existing:
- `src/components/ui/tooltip.tsx` — shadcn/ui Tooltip component (already exists)
- `src/Utils/utils.ts` — utility functions (already exist)

## Acceptance Criteria Coverage

| AC # | Description | Implementation |
|------|-------------|----------------|
| 1 | 0-28 days → days only | Already implemented in `formatPatientAge` |
| 2 | 29 days-1 year → weeks + days | Already implemented in `formatPatientAge` |
| 3 | 1-2 years → months + days | Already implemented in `formatPatientAge` |
| 4 | 2-18 years → years + months | Already implemented in `formatPatientAge` |
| 5 | 18+ years → years only | Already implemented in `formatPatientAge` |
| 6 | Tooltip with full breakdown | Add Tooltip component wrapping age display |
| 7 | Deceased patients use deceased_datetime | Already implemented in `getPatientAgeBreakdown` |

## Implementation Notes

- This is a UI-only change with no backend modifications
- All business logic already exists and is tested
- The change is minimal: wrap existing age text with a Tooltip component
- No i18n changes required (utility functions already handle localization)
- No accessibility concerns (Tooltip component from shadcn/ui is WCAG compliant)
