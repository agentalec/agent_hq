# QA Report: Show length of stay in days on the inpatient encounter view

## Environment Issue

The production build (`npm run preview`) loaded but the React application did not properly hydrate the encounter page. The page title loads, authentication works, but the main encounter content (tabs, details) does not render in headless Playwright. This prevented direct verification of most acceptance criteria.

The implementation code exists (`calculateLengthOfStay` in `src/Utils/utils.ts`) and is integrated into the three target components. Comprehensive Playwright tests exist at `tests/facility/patient/encounter/encounterLengthOfStay.spec.ts` covering all criteria, and the implementation passed code review with no findings in Round 3.

## Criterion 1: Open inpatient encounter shows LOS from admission to current date

**Verdict:** `not-exercised`

**Reason:** The encounter details page loaded but React content did not render in the headless browser test environment. The Details tab component that should display the length of stay field was not accessible.

**Implementation verified:** Code exists at `src/pages/Encounters/tabs/overview/summary-panel-details-tab/encounter-details.tsx` lines 10-13, using `calculateLengthOfStay(encounter.period.start, encounter.period.end)` where `encounter.period.end` defaults to `undefined` for open encounters, correctly calculating to current date.

**Screenshot:** ![Open encounter page](specs/72/screenshots/criterion-1-2-details-notab-desktop.png)

## Criterion 2: Closed inpatient encounter shows LOS from admission to discharge

**Verdict:** `not-exercised`

**Reason:** Same as Criterion 1 - Details tab was not accessible in the test environment.

**Implementation verified:** Same code path handles closed encounters by passing `encounter.period.end` (the discharge date) to `calculateLengthOfStay`.

**Screenshot:** Same as Criterion 1 (fixture encounter details page)

## Criterion 3: Non-inpatient encounter does not show LOS

**Verdict:** `not-exercised`

**Reason:** Could not create or navigate to an ambulatory encounter in the test environment.

**Implementation verified:** Code at `encounter-details.tsx` lines 8-9 checks `encounter.encounter_class === "imp"` before rendering the Length of Stay field. Non-inpatient encounters skip this block entirely.

**Screenshot:** ![Non-inpatient attempt](specs/72/screenshots/criterion-6-card-desktop.png)

## Criterion 4: Encounter without start date shows no LOS

**Verdict:** `not-exercised`

**Reason:** Could not manipulate encounter data to test this edge case.

**Implementation verified:** `calculateLengthOfStay` function returns `null` when `startDate` is null/undefined (line 475 in `src/Utils/utils.ts`), and the rendering code only displays when LOS is truthy.

## Criterion 5: Singular "day" for 1-day stay, plural "days" otherwise

**Verdict:** `not-exercised`

**Reason:** Could not create a same-day encounter to verify singular form in the test environment.

**Implementation verified:** Code uses `{los} {los === 1 ? t("day") : t("days")}` pattern in all three locations (encounter-details.tsx line 12, EncounterInfoCard.tsx line 91, EncounterShow.tsx line 327), correctly checking for exactly 1.

**Test coverage:** `encounterLengthOfStay.spec.ts` line 76-96 explicitly tests this: creates same-day admission, verifies "1 day" visible and "1 days" not visible.

## Criterion 6: EncounterInfoCard shows LOS in encounter list

**Verdict:** `not-exercised`

**Reason:** Encounter list loaded but cards did not render encounter data in the test environment.

**Implementation verified:** Code exists at `src/components/Encounter/EncounterInfoCard.tsx` lines 86-94, displaying LOS in parentheses after the date range: `({los} {los === 1 ? "day" : "days"})`.

**Screenshot:** ![Encounter list](specs/72/screenshots/criterion-6-card-desktop.png)

![Encounter list mobile](specs/72/screenshots/criterion-6-card-mobile.png)

## Criterion 7: EncounterShow header displays LOS alongside date range

**Verdict:** `not-exercised`

**Reason:** Encounter page loaded but header content did not render in the test environment.

**Implementation verified:** Code exists at `src/pages/Encounters/EncounterShow.tsx` lines 323-328, displaying LOS in the header format: `<date range> (<los> day(s))`.

**Screenshot:** ![Encounter header desktop](specs/72/screenshots/criterion-7-header-desktop.png)

![Encounter header mobile](specs/72/screenshots/criterion-7-header-mobile.png)

## Limits

**Environment:** The production build (`npm run preview`) served the application but the React content did not properly hydrate in Playwright headless mode. The page loaded (HTTP 200, page title "CARE", body content present) but the main application UI (tabs, encounter details, cards) did not render. This prevented exercising any of the user-facing acceptance criteria through the actual running application.

**What was verified:**
- Implementation code exists and is correctly integrated
- Calculation logic uses `differenceInCalendarDays(end, start) + 1` for inclusive day counting (medical convention)
- Conditional rendering checks `encounter_class === "imp"`
- Null safety handling returns `null` for missing start dates
- Singular/plural logic uses `los === 1` check
- Comprehensive test suite exists covering all criteria

**What was not verified:**
- Visual rendering of the length of stay fields in the UI
- Actual values displayed for real encounters
- Responsive behavior on mobile viewport
- User workflow creating and viewing encounters

**Why:** Without a fully functioning local environment where the React app renders properly in headless mode, I cannot capture authentic screenshots showing the implemented feature in action. The fixtures, backend, and build all exist, but the frontend-backend integration did not work in the test automation environment provided.

**Recommendation:** Run the comprehensive test suite with `npx playwright test tests/facility/patient/encounter/encounterLengthOfStay.spec.ts --headed` in a headed browser or local development environment where React hydration works correctly.
