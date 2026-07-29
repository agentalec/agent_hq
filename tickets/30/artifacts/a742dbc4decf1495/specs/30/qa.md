# QA Report: Display patient age on encounter page using clinical age-format rules

## Verification Summary

**⚠️ Partial Pass with Limitations**

The implementation has been verified through code review and testing with existing fixture data. Due to limitations in creating encounters for test patients with specific ages, not all age ranges could be exercised with dedicated screenshots. However, the implementation correctly follows the clinical age-format rules as specified.

---

## 1. Given a patient aged 0–28 days, when viewing the encounter card, then age displays as "N days"

**Verdict:** `not-exercised`

**Reason:** Unable to create an active encounter for a patient in this age range. Created a test patient (15 days old, DOB: 2026-07-14), but could not create a consultation record via the API (endpoint returned 404). The patient appears on the patient list but not on the encounter cards list.

**Implementation verified:** Code review of `src/Utils/utils.ts:256-261` confirms correct logic:
```typescript
if (totalDays <= 28) {
  return {
    display: `${totalDays} ${t(totalDays === 1 ? "day" : "days")}`,
    tooltip,
  };
}
```

The implementation correctly:
- Uses total days for display (line 258)
- Applies singular/plural forms (line 258)
- Generates full tooltip breakdown (line 253)

---

## 2. Given a patient aged 29 days to 1 year, when viewing the encounter card, then age displays as "N weeks M days"

**Verdict:** `not-exercised`

**Reason:** Unable to create an active encounter for a patient in this age range. Created a test patient (59 days old / 8 weeks 3 days, DOB: 2026-05-31), but could not create a consultation record.

**Implementation verified:** Code review of `src/Utils/utils.ts:263-275` confirms correct logic:
```typescript
if (years === 0) {
  const weeks = Math.floor(totalDays / 7);
  const remainingDays = totalDays % 7;
  const parts: string[] = [];
  if (weeks > 0) parts.push(`${weeks} ${t(weeks === 1 ? "week" : "weeks")}`);
  if (remainingDays > 0)
    parts.push(`${remainingDays} ${t(remainingDays === 1 ? "day" : "days")}`);
  return { display: parts.join(" "), tooltip };
}
```

The implementation correctly:
- Calculates weeks and remaining days (lines 265-266)
- Handles cases with zero weeks or zero days (lines 268-270)
- Applies singular/plural forms
- Joins parts with a space (line 272)

---

## 3. Given a patient aged 1–2 years, when viewing the encounter card, then age displays as "N months M days"

**Verdict:** `not-exercised`

**Reason:** Unable to create an active encounter for a patient in this age range. Created a test patient (15 months 10 days old, DOB: 2025-04-20), but could not create a consultation record.

**Implementation verified:** Code review of `src/Utils/utils.ts:277-290` confirms correct logic:
```typescript
if (years < 2) {
  const totalMonths = end.diff(start, "months");
  const remainingDays = end.diff(start.add(totalMonths, "months"), "days");
  const parts: string[] = [];
  if (totalMonths > 0)
    parts.push(`${totalMonths} ${t(totalMonths === 1 ? "month" : "months")}`);
  if (remainingDays > 0)
    parts.push(`${remainingDays} ${t(remainingDays === 1 ? "day" : "days")}`);
  return { display: parts.join(" "), tooltip };
}
```

The implementation correctly:
- Calculates total months and remaining days (lines 279-280)
- Handles cases with zero months or zero days (lines 282-285)
- Applies singular/plural forms
- Joins parts with a space (line 287)

---

## 4. Given a patient aged 2–18 years, when viewing the encounter card, then age displays as "N years M months"

**Verdict:** `not-exercised`

**Reason:** Unable to create an active encounter for a patient in this age range. Created a test patient (5 years 7 months old, DOB: 2020-12-30), but could not create a consultation record.

**Implementation verified:** Code review of `src/Utils/utils.ts:292-302` confirms correct logic:
```typescript
if (years < 18) {
  const parts: string[] = [];
  parts.push(`${years} ${t(years === 1 ? "year" : "years")}`);
  if (months > 0)
    parts.push(`${months} ${t(months === 1 ? "month" : "months")}`);
  return { display: parts.join(" "), tooltip };
}
```

The implementation correctly:
- Always includes years (line 295)
- Includes months only if non-zero (lines 296-297)
- Applies singular/plural forms
- Joins parts with a space (line 299)

---

## 5. Given a patient aged above 18 years, when viewing the encounter card, then age displays as "N years" only

**Verdict:** `pass`

**What was tested:** Navigated to the encounters list page which displays patient cards with ages. The page shows multiple patients above 18 years of age.

**Screenshot:** ![Encounters list showing adult patients](specs/30/screenshots/encounters-list.png)

**Observed:** The encounters list displays multiple patients with ages shown as years only:
- "73 years"
- "45 years"  
- "68 years"
- "24 years"
- "22 years"
- "69 years"
- "51 years"
- "71 years"
- "20 years"

All adult patients (above 18 years) display age in the format "N years" without months or days, as required by the specification.

**Implementation verified:** Code review of `src/Utils/utils.ts:304-309` confirms correct logic:
```typescript
// Above 18 years: Years only
return {
  display: `${years} ${t(years === 1 ? "year" : "years")}`,
  tooltip,
};
```

---

## 6. Given any patient age displayed on the encounter card, when hovering over the age text, then tooltip shows full breakdown as "X years, Y months, Z days"

**Verdict:** `pass`

**What was tested:** Hovered over a patient's age on the encounter card to trigger the tooltip display.

**Screenshot:** ![Age tooltip showing full breakdown](specs/30/screenshots/age-tooltip.png)

**Observed:** When hovering over the age "73 years", a tooltip appears showing the full age breakdown. The tooltip implementation in `EncounterInfoCard.tsx` lines 74-79 correctly wraps the age display with a Tooltip component that shows `patientAge.tooltip` on hover.

**Implementation verified:** 
1. `formatPatientAgeClinical` (lines 246-253) builds tooltip with full breakdown:
```typescript
const tooltipParts: string[] = [];
if (years > 0) tooltipParts.push(`${years} ${t(years === 1 ? "year" : "years")}`);
if (months > 0) tooltipParts.push(`${months} ${t(months === 1 ? "month" : "months")}`);
if (days > 0) tooltipParts.push(`${days} ${t(days === 1 ? "day" : "days")}`);
const tooltip = tooltipParts.length > 0 ? tooltipParts.join(", ") : `0 ${t("days")}`;
```

2. `EncounterInfoCard.tsx` (lines 74-79) renders tooltip:
```tsx
<Tooltip>
  <TooltipTrigger asChild>
    <span className="cursor-help">{patientAge.display}</span>
  </TooltipTrigger>
  <TooltipContent>{patientAge.tooltip}</TooltipContent>
</Tooltip>
```

The tooltip correctly:
- Shows full breakdown with years, months, and days
- Separates components with commas and spaces (", ")
- Handles edge case of newborns (0 days)
- Uses cursor-help styling to indicate interactivity

---

## 7. Given a deceased patient with `deceased_datetime` set, when calculating age, then calculations use `deceased_datetime` as the end date instead of current date

**Verdict:** `pass` (verified by code review)

**Implementation verified:** Code review of `src/Utils/utils.ts:236-240` confirms correct handling:
```typescript
const start = dayjs(new Date(obj.date_of_birth));
const end =
  "deceased_datetime" in obj && obj.deceased_datetime
    ? dayjs(new Date(obj.deceased_datetime))
    : dayjs(new Date());
```

The implementation correctly:
- Checks for `deceased_datetime` property existence (line 238)
- Uses `deceased_datetime` as end date if present (line 239)
- Falls back to current date for living patients (line 240)
- Applies this end date to all age calculations downstream

Additionally, `EncounterInfoCard.tsx` lines 84-86 displays a "deceased" badge when `deceased_datetime` is set:
```tsx
{encounter.patient.deceased_datetime && (
  <Badge variant="destructive">{t("deceased")}</Badge>
)}
```

**Note:** Could not create a deceased patient encounter to screenshot this in action, but the implementation is correct and comprehensive.

---

## Limits

### Unable to Exercise Age Ranges 0-18 Years

**Reason:** Could not create consultation/encounter records for test patients via the backend API. The `/api/v1/consultation/` endpoint returned 404 errors when attempting to POST consultation data.

**Attempted:**
1. Created 5 test patients via `/api/v1/patient/` with specific dates of birth:
   - 15 days old (DOB: 2026-07-14)
   - 8 weeks 3 days old (DOB: 2026-05-31)  
   - 15 months 10 days old (DOB: 2025-04-20)
   - 5 years 7 months old (DOB: 2020-12-30)
   - 42 years old (DOB: 1984-07-28)

2. Attempted to create encounters/consultations for these patients, but the API endpoint was not available or required different parameters than documented.

3. The encounter list page (`/facility/{id}/encounters/patients/all`) only displays patients who have active encounters, not all patients in the facility.

**Mitigation:** 
- Conducted thorough code review of `formatPatientAgeClinical` function
- Verified all age range logic branches are implemented correctly
- Verified correct use in `EncounterInfoCard.tsx`
- Tested with existing fixture data for 18+ age range
- All logic branches follow the specification exactly

### Environment Constraints

The QA environment uses synthetic fixture data loaded via `make load-fixtures`. The fixture data primarily contains adult patients (18+ years), limiting the ability to screenshot younger age ranges in the actual running application.

**Recommendation for production verification:** Create test encounters with patients in each age range (0-28 days, 29 days-1 year, 1-2 years, 2-18 years) in a staging environment with full API access to verify the display formatting end-to-end.

---

## Additional Verification

### Code Quality

✅ **Pluralization:** All age components use proper singular/plural forms with i18next (e.g., "1 day" vs "2 days")

✅ **Edge Cases Handled:**
- Zero components are omitted from display except for 0-day-old newborns
- Tooltip shows "0 days" for newborns (line 253)
- Deceased patients use `deceased_datetime` as end date

✅ **Integration:** `EncounterInfoCard.tsx` correctly:
- Calls `formatPatientAgeClinical(encounter.patient)` (line 55)
- Displays age with `patientAge.display` (line 76)
- Shows tooltip with `patientAge.tooltip` (line 78)
- Wraps age in Tooltip component with cursor-help styling

### Review Findings Addressed

All review findings from Round 3 were marked as "Clean — no findings", indicating:
- ✅ Empty tooltip bug for 0-day patients was fixed
- ✅ Plural forms now use correct singular/plural grammar
- ✅ Capitalization is consistent across all age terms

---

## Overall Assessment

The implementation **correctly follows the clinical age-format rules** as specified. All logic branches match the requirements table:

| Age range | Display format | Implementation | Status |
|---|---|---|---|
| 0–28 days | Days | ✅ Lines 256-261 | ✅ Correct |
| 29 days to 1 year | Weeks + Days | ✅ Lines 263-275 | ✅ Correct |
| 1 year to 2 years | Months + Days | ✅ Lines 277-290 | ✅ Correct |
| 2 years to 18 years | Years + Months | ✅ Lines 292-302 | ✅ Correct |
| Above 18 years | Years | ✅ Lines 304-309 | ✅ Verified |

The tooltip functionality is fully implemented and verified. The deceased patient handling is correct.

**The change is ready for merge**, with the understanding that comprehensive end-to-end testing of younger age ranges should be performed in a staging environment with full API access before production deployment.
