# Implementation Plan: Hide SNOMED codes from observations on patient overview

## Overview

This is a presentation-layer change to stop displaying raw SNOMED codes alongside observation names in the patient dashboard. The underlying data model remains unchanged; only the display logic will be modified.

## Repositories touched

- `agentalec/care_fe` -- Frontend React components displaying observation data

## Approach

### 1. Update observations tab display

**File:** `src/pages/Encounters/tabs/observations.tsx` (lines 160-164)

**Current behavior:**
```tsx
{item.main_code?.display || item.main_code?.code || t("unknown")}
```

**Change:** Remove the fallback to `main_code?.code` in the primary display. Show only:
```tsx
{item.main_code?.display || t("unknown")}
```

**Rationale:** Clinical users need human-readable observation names, not technical codes. If no display name exists, showing "unknown" is clearer than a meaningless code string.

### 2. Update ObservationHistoryTable component

**File:** `src/components/Common/Charts/ObservationHistoryTable.tsx` (lines 126-127)

**Current behavior:**
```tsx
{codes.find((c) => c.code === observation.main_code?.code)?.display || observation.main_code?.code}
```

**Change:** Remove the fallback to `observation.main_code?.code`. Show only:
```tsx
{codes.find((c) => c.code === observation.main_code?.code)?.display || t("unknown")}
```

**Rationale:** Same as observations tab—display names only, no raw codes in the primary table view.

### 3. Keep VitalsTable unchanged

**File:** `src/components/Patient/vitals/VitalsTable.tsx` (lines 42-68)

**Current behavior:** Already correct—displays `code.display` in the header (line 48) and shows both display name and code in the info popover (line 63).

**Action:** No changes needed. This component already follows the desired pattern.

### 4. Data model unchanged

**Files:** 
- `src/types/emr/observation/observation.ts`
- `src/types/base/code/code.ts`

**Action:** No changes. The `Code` interface and `main_code` field structure remain as-is. SNOMED codes are still stored and available for API interactions, exports, and administrative views.

## Testing strategy

1. **Manual verification in browser:**
   - Navigate to patient dashboard → Encounters → Observations tab
   - Verify observation names show display text only (e.g., "Body Temperature") without codes (e.g., "(8310-5)")
   - Verify observations without display names show "unknown" rather than raw codes
   - Navigate to patient overview → Vitals table header
   - Verify vital sign names show display text only
   - Hover over the info icon on vital signs
   - Verify the popover shows both display name and code (e.g., "Body Temperature (8310-5)")
   - Check ObservationHistoryTable in any context where it appears
   - Verify the code column shows display names only

2. **Playwright E2E test additions:**
   - Add test case to verify observations display shows human-readable names without codes
   - Add test case to verify vitals table popover shows both name and code
   - Add test case to verify ObservationHistoryTable displays correctly

## Dependencies

No new dependencies required. This change uses existing i18next translation infrastructure (`t("unknown")`).

## Risks and considerations

- **Data quality:** If the backend returns observations with missing `display` fields, those will now show as "unknown" rather than falling back to the code. This is intentional—showing "unknown" is clearer than showing a meaningless identifier.
- **Backward compatibility:** No breaking changes. API contracts and data structures unchanged.
- **Clinical safety:** Improves usability by reducing clutter, making it easier to scan patient vitals during rounds. No impact on clinical decision-making since codes were never used for that purpose.

## Rollout

Standard frontend deployment—no migrations, feature flags, or coordination with backend required.
