# Review: Display patient age on encounter page using clinical age-format rules

## Round 1

- **blocker** `src/Utils/utils.ts:176-181` — `getFullAgeBreakdown` omits zero values from the breakdown; a 5-year-old with exactly 0 months and 0 days shows only "5 years" instead of "5 years 0 months 0 days". The spec AC6 requires "the complete breakdown in years, months, and days" for all ages, not a filtered list.
- **should-fix** `tests/PLAYWRIGHT_GUIDE.md:158-168` — test documentation accidentally reformatted by removing newlines between URL examples, making them hard to read and unintentional to this ticket's scope.

## Round 2

Clean — no findings.
