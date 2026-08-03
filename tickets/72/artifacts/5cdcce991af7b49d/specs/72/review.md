# Review: Show length of stay in days on the inpatient encounter view

## Round 1

- **blocker** `src/Utils/utils.ts:50` — Length of stay calculation is off by one; medical convention requires inclusive counting (admission day counts as day 1). A same-day admission/discharge should show "1 day", not "0 days". Add 1 to the result: `return differenceInCalendarDays(end, start) + 1;`.

## Round 2

- **blocker** `tests/PLAYWRIGHT_GUIDE.md:87-98` — Formatting corruption removed all newlines in code block, making URL examples unreadable. Restore original formatting with one URL per line.
- **blocker** Missing tests — Custom instructions require "Every implementation task ships tests for the code it adds." Need Playwright test to verify LOS display in EncounterInfoCard, EncounterDetails, and EncounterShow for both open and closed inpatient encounters.
- **should-fix** `src/Utils/utils.ts:473` — The `calculateLengthOfStay` function is not covered by unit tests. While Playwright E2E tests are primary, a utility function used in multiple places warrants a unit test for edge cases (null dates, same-day admission/discharge, multi-day stays).

## Round 3

Clean — no findings.
