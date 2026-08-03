# Implementation Tasks: Hide SNOMED codes from observations on patient overview

## Task 1: Update observation display components to hide SNOMED codes

**Repository:** `agentalec/care_fe`

**Dependencies:** None

**Scope:**
Update three React components to remove SNOMED codes from observation displays:

1. **Observations tab** (`src/pages/Encounters/tabs/observations.tsx`, lines 160-164)
   - Change: `{item.main_code?.display || item.main_code?.code || t("unknown")}` 
   - To: `{item.main_code?.display || t("unknown")}`
   - Remove the fallback to `main_code?.code`

2. **ObservationHistoryTable** (`src/components/Common/Charts/ObservationHistoryTable.tsx`, lines 126-127)
   - Change: `{codes.find((c) => c.code === observation.main_code?.code)?.display || observation.main_code?.code}`
   - To: `{codes.find((c) => c.code === observation.main_code?.code)?.display || t("unknown")}`
   - Remove the fallback to `observation.main_code?.code`

3. **VitalsTable verification** (`src/components/Patient/vitals/VitalsTable.tsx`, lines 42-68)
   - Verify that the current implementation is correct (already displays only `code.display` in headers)
   - Verify that the info popover still shows both display name and code (e.g., "Body Temperature (8310-5)")
   - No changes needed, but confirm existing behavior matches requirements

**Acceptance criteria coverage:**
- AC1: Observations tab shows only `display` value
- AC2: Observations tab shows "unknown" when no `display` (code not used as fallback)
- AC3: Vitals table popover shows both display name and code
- AC4: Vitals table header shows only display name
- AC5: ObservationHistoryTable shows only `display` value
- AC6: Data structure unchanged (verified by not touching type definitions)
- AC7: No SNOMED codes in primary UI (all three components updated)

**Testing:**
- Manually verify in patient dashboard that observations show only human-readable names
- Verify observations without display names show "unknown" instead of codes
- Verify vitals table headers show only display names
- Verify vitals table info popovers show both name and code
- Run existing Playwright tests to ensure no regressions

**Estimated size:** ~10 lines changed across 2 files (plus verification of 1 file)
