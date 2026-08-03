# Review: Show length of stay in days on the inpatient encounter view

## Round 1

- **blocker** `src/Utils/utils.ts:50` — Length of stay calculation is off by one; medical convention requires inclusive counting (admission day counts as day 1). A same-day admission/discharge should show "1 day", not "0 days". Add 1 to the result: `return differenceInCalendarDays(end, start) + 1;`.
