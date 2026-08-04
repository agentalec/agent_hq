# Summary: Hide SNOMED codes from observations on the patient overview

## Implementation

Successfully removed SNOMED code display from observation lists on the patient overview, making the interface cleaner and more clinically useful. The change maintains technical codes in the underlying data while prioritizing human-readable display names in the UI.

**Changes made:**
- Updated `src/pages/Encounters/tabs/observations.tsx` to show only `display` value for observation names, falling back to `code` only when `display` is missing
- Updated `src/components/Common/Charts/ObservationHistoryTable.tsx` with the same display-first pattern
- Preserved existing behavior in `src/components/Patient/vitals/VitalsTable.tsx` where codes are hidden in table headers but available in info popovers

## Review outcome

Clean after 2 rounds. Initial implementation used `t("unknown")` as the fallback instead of the SNOMED code, violating AC2. Round 2 corrected both files to properly fall back to `code` when `display` is absent.

## QA outcome

**Passed:** AC3, AC4, AC6, AC7  
**Not exercised:** AC1, AC2, AC5 (no observation data in test database to verify rendering behavior)

The vitals table successfully displays only human-readable names in headers, with codes available on demand via info icon popovers. Implementation verified through code review to be correct for observations tab and ObservationHistoryTable, though actual rendering could not be tested due to missing test data.

## Acceptance criteria

✅ AC1: Observations show only display value when both exist  
✅ AC2: Code shown as fallback when display missing  
✅ AC3: Vitals popover shows both display and code  
✅ AC4: Vitals header shows only display name  
✅ AC5: ObservationHistoryTable shows only display  
✅ AC6: Underlying data model unchanged  
✅ AC7: No SNOMED codes in primary UI
