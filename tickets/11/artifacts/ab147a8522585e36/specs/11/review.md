# Review: Display patient age on encounter page using clinical age-format rules

## Round 1

- **blocker** `tests/` — No Playwright E2E tests added. Per tasks.md, the implementation requires test cases to verify: (1) age format for different age ranges, (2) tooltip content on hover, (3) deceased patient age calculation. Add tests in `tests/facility/patient/encounter/` directory.

## Round 2

- **blocker** `src/Utils/utils.ts:297` — Condition `if (years < 18)` excludes 18-year-olds from pediatric format. Spec AC4 says "2 years to 18 years" should show "years + months", meaning a patient aged 18 years 3 months should display "18 Y 3 mo" not "18 Y". Change to `if (years <= 18)`. Also add test case for the 18-year boundary (e.g., 18 years 3 months) to verify this critical age threshold.
- **should-fix** `tests/facility/patient/encounter/patientAgeDisplay.spec.ts:120,170,220,271` — Tooltip assertions use overly broad regex patterns that don't verify exact calculated values. For example, line 120 checks `/weeks.*days/` which would pass for any week/day combination. Should verify specific expected values (e.g., "8 weeks, 4 days" for the 60-day test) to ensure age calculation correctness.

## Round 3

Clean — no findings.
