# Implementation Tasks: Display patient age on encounter page using clinical age-format rules

## Task 1: Add tooltip to patient age display in EncounterInfoCard

**Repository:** agentalec/care_fe  
**Estimated effort:** ~50 lines changed  
**Dependencies:** None

### Description

Wrap the existing patient age display in the EncounterInfoCard component with a Tooltip component to show the full age breakdown (years, months, days) on hover.

### Changes Required

**File:** `src/components/Encounter/EncounterInfoCard.tsx`

1. Import Tooltip components from shadcn/ui:
   ```typescript
   import {
     Tooltip,
     TooltipContent,
     TooltipTrigger,
   } from "@/components/ui/tooltip";
   ```

2. Import the tooltip formatter utility:
   ```typescript
   import { formatPatientAgeTooltip } from "@/Utils/utils";
   ```

3. Replace the current age display (line 67):
   ```typescript
   // Current:
   {formatPatientAge(encounter.patient, true)}
   
   // New:
   <Tooltip>
     <TooltipTrigger className="cursor-default">
       {formatPatientAge(encounter.patient, true)}
     </TooltipTrigger>
     <TooltipContent>
       {formatPatientAgeTooltip(encounter.patient, false)}
     </TooltipContent>
   </Tooltip>
   ```

### Acceptance Criteria Covered

- **AC #6:** Tooltip with full age breakdown (years, months, days) on hover
- Indirectly verifies **AC #1-5:** The existing `formatPatientAge` utility already implements all the clinical age-format rules correctly
- Indirectly verifies **AC #7:** The existing `getPatientAgeBreakdown` utility already handles deceased patients using `deceased_datetime`

### Testing

**Manual verification:**
1. Navigate to an encounter page for patients in different age ranges:
   - Neonate (0-28 days): Age displays as "X days"
   - Infant (29 days-1 year): Age displays as "X weeks Y days"
   - Toddler (1-2 years): Age displays as "X months Y days"
   - Child (2-18 years): Age displays as "X years Y months"
   - Adult (18+ years): Age displays as "X years"
2. Hover over each age display and verify tooltip shows full breakdown
3. Test with a deceased patient and verify age calculation uses deceased_datetime

**Playwright E2E test:**
- Add test case in `tests/facility/encounter/` to verify:
  - Age format for different age ranges
  - Tooltip content on hover
  - Deceased patient age calculation

### Notes

- All utility functions (`formatPatientAge`, `getPatientAgeBreakdown`, `formatPatientAgeTooltip`, `getRelativeDateSuffix`) already exist and implement the specification correctly
- Tooltip component is from shadcn/ui and is WCAG compliant
- No backend changes required
- No i18n changes required (utilities already handle localization)
- No new dependencies required

---

## Summary

This ticket requires a single implementation task in the `agentalec/care_fe` repository. The implementation is minimal (~50 lines) because all the age-formatting logic already exists in utility functions. The only change is to wrap the existing age display with a Tooltip component to show the full age breakdown on hover.

All 7 acceptance criteria are covered by this task:
- AC #1-5: Already implemented in `formatPatientAge` utility
- AC #6: Implemented by adding the Tooltip component
- AC #7: Already implemented in `getPatientAgeBreakdown` utility
