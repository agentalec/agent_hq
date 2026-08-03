# Spec: Show length of stay in days on the inpatient encounter view

## Problem Statement

Clinical staff manually count days between admission and discharge dates during rounds when reviewing inpatient encounters. The 10bedicu team reports that length of stay (LOS) is a critical metric discussed in every round, driving decisions about patient transfer, referral, and treatment escalation or de-escalation. This manual calculation wastes time and introduces risk of error during high-stakes clinical decision-making.

## Acceptance Criteria

1. Given an open inpatient encounter, when viewing the encounter details in `src/pages/Encounters/tabs/overview/summary-panel-details-tab/encounter-details.tsx`, then the length of stay in days is displayed, calculated from admission date to current date.
2. Given a closed inpatient encounter, when viewing the encounter details, then the length of stay in days is displayed, calculated from admission date to discharge date.
3. Given an encounter with `encounter_class` not equal to "imp", when viewing the encounter details, then the length of stay is not displayed.
4. Given an inpatient encounter without a start date, when viewing the encounter details, then no length of stay is displayed.
5. Given the length of stay is displayed, when the value is singular (1 day), then it shows "1 day", and when plural it shows "N days".
6. Given an inpatient encounter viewed in the EncounterInfoCard component at `src/components/Encounter/EncounterInfoCard.tsx`, when the encounter dates are shown, then the length of stay in days is also displayed.
7. Given an inpatient encounter on the EncounterShow page at `src/pages/Encounters/EncounterShow.tsx`, when the encounter metadata is shown in the header (lines 310-335), then the length of stay is displayed alongside the date range.

## Capability Notes

- `src/types/emr/encounter/encounter.ts:Period` -- defines `start` and `end` date fields used for LOS calculation; exists.
- `src/types/emr/encounter/encounter.ts:EncounterClass` -- defines encounter types including "imp" for inpatient; exists.
- `src/Utils/utils.ts` -- imports `differenceInMinutes` from date-fns; needs `differenceInDays` or `differenceInCalendarDays` added.
- `src/pages/Encounters/tabs/overview/summary-panel-details-tab/encounter-details.tsx` -- displays start and end dates (lines 73-111); needs LOS field added.
- `src/components/Encounter/EncounterInfoCard.tsx` -- shows encounter period dates (lines 86-91); needs LOS field added.

## Open Questions

None.
