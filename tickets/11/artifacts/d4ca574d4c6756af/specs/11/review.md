# Review: Display patient age on encounter page using clinical age-format rules

## Round 1

### Acceptance Criteria Coverage

**AC1: Display age using clinical age-format rules** ✓
- 0-28 days: Implementation correctly displays "X days" (lines 245-248 in utils.ts)
- 29 days to 1 year: Implementation correctly displays "X weeks Y days" (lines 250-258)
- 1 year to 2 years: Implementation correctly displays "X months Y days" (lines 260-268)
- 2 years to 18 years: Implementation correctly displays "X years Y months" (lines 270-276)
- Above 18 years: Implementation correctly displays "X years" only (lines 278-279)

**AC2: Handle abbreviated format** ✓
- Implementation uses `getRelativeDateSuffix(abbreviated)` to provide abbreviated suffixes ("d", "w", "mo", "Y")

**AC3: Show full age breakdown on hover** ✓
- `formatPatientAgeTooltip()` function implemented to show full breakdown
- `TooltipComponent` integrated in `PatientInfoHoverCard.tsx` and `PatientHoverCard.tsx`

**AC4: Calculate age relative to death date for deceased patients** ✓
- Implementation checks for `deceased_datetime` and uses it as the end date (lines 229-232)

**AC5: Handle year-of-birth-only patients** ✓
- Implementation displays "Born YYYY" or "Born on YYYY" (lines 236-240)

**AC6: Maintain consistency across all age displays** ✓
- Changes to `formatPatientAge()` function apply to all usages throughout the application

### Blockers

**BLOCKER-1: Test expectations incorrect for non-abbreviated format**
Location: `tests/unit/formatPatientAge.spec.ts`, lines 530, 537-538, 547-548, 553-554, 562-563, 568-569, 574-575, 580-581

The tests expect abbreviated suffixes ("Y", "mo") when calling `formatPatientAge(patient)` without the abbreviated parameter (defaults to false). This is incorrect.

Examples:
- Line 530: `expect(formatPatientAge(patient)).toBe("2 Y");` should be `expect(formatPatientAge(patient)).toBe("2 years");`
- Line 537-538: Expects "5 Y" and "3 mo" but should expect "5 years" and "3 months"
- Line 547-548: Expects "10 Y" and "6 mo" but should expect "10 years" and "6 months"
- Line 553-554: Expects "17 Y" and "11 mo" but should expect "17 years" and "11 months"

All instances in the "2 years to 18 years" and "Above 18 years" test sections need correction. When `abbreviated=false` (the default), the function returns full words ("years", "months", "weeks", "days"), not abbreviated forms.

**BLOCKER-2: Test expectations incorrect for abbreviated format**
Location: `tests/unit/formatPatientAge.spec.ts`, lines 531, 563, 569, 575, 581

The tests expect abbreviated suffixes without spaces when calling `formatPatientAge(patient, true)`. Looking at the implementation, the function includes spaces between numbers and suffixes even in abbreviated mode.

Examples:
- Line 531: `expect(formatPatientAge(patient, true)).toBe("2Y");` but implementation returns `"2 Y"` (with space)
- Line 563: Expects "18Y" but implementation returns "18 Y"

The implementation at line 279 returns `${years} ${suffixes.year}` which includes a space. Tests should expect "2 Y" not "2Y".

**BLOCKER-3: PLAYWRIGHT_GUIDE.md formatting corrupted**
Location: `tests/PLAYWRIGHT_GUIDE.md`, lines 231-248

The diff shows malformed changes where multiple template strings were concatenated on single lines without proper separators:

```typescript
// Before (correct):
`/facility/${facilityId}/overview`
`/facility/${facilityId}/settings/locations`

// After (incorrect):
`/facility/${facilityId}/overview``/facility/${facilityId}/settings/locations`
```

This creates invalid TypeScript syntax. Each template string should be on its own line with proper commenting/formatting, or they should be properly separated if intended as code examples.

**BLOCKER-4: Test description doesn't match assertion**
Location: `tests/unit/formatPatientAge.spec.ts`, line 462

The test description says "should display '5 weeks 0 days' for 35-day-old" but the implementation at line 254-255 in utils.ts shows that when `remainingDays === 0`, it returns only weeks without days (e.g., "5 weeks"). The test assertion only checks for "5 weeks" which is correct, but the test description is misleading.

This should either:
1. Update the test description to match the actual behavior: "should display '5 weeks' for 35-day-old"
2. Or update the implementation to always show days even when 0: "5 weeks 0 days"

### Should-Fix Issues

**SHOULD-FIX-1: Inconsistent test precision expectations**
Location: `tests/unit/formatPatientAge.spec.ts`, lines 419, 427, 435-436

Some tests use range checks for day values while others expect exact values. This inconsistency makes it unclear whether the date calculation precision is reliable:
- Line 419: `expect(breakdown.days).toBeGreaterThanOrEqual(28);` - Why not exact?
- Line 427: `expect(breakdown.days).toBeLessThanOrEqual(1);` - Why a range?
- Line 435-436: Range check for 4-6 days

Consider using exact value assertions with proper mocking of dates, or document why ranges are necessary.

**SHOULD-FIX-2: Missing test for weeks-only display**
Location: `tests/unit/formatPatientAge.spec.ts`, line 462-467

The test at line 479 verifies "8 weeks" but doesn't verify the absence of days suffix. Add explicit assertion:
```typescript
expect(result).toBe("8 weeks"); // or "8w" for abbreviated
```

This would catch any implementation bugs that add unnecessary "0 days" suffix.

**SHOULD-FIX-3: E2E test uses generic pattern matching**
Location: `tests/organization/patient/encounter/patientInfoHoverCard.spec.ts`, line 293

The test uses a very generic regex pattern `expect(ageText).toMatch(/\d+[Ywmd]/);` which only verifies that some age unit exists. Consider more specific assertions based on the test patient's expected age to ensure the correct clinical format is applied.

### Nits

**NIT-1: Abbreviated year suffix uses capital "Y"**
Location: `src/Utils/utils.ts`, line 145

The abbreviated format uses "Y" (capital) instead of the more common lowercase "y". While this works, "y" or "yr" might be more conventional in medical contexts. This should be confirmed with the clinical team.

**NIT-2: Documentation could be more specific**
Location: `src/Utils/utils.ts`, lines 179-183

The `formatPatientAgeTooltip` JSDoc says "Always shows 'X years, Y months, Z days' format" but the implementation only shows non-zero values. For a 2-year-old with 0 months and 0 days, it shows "2 years" not "2 years, 0 months, 0 days". Consider updating the documentation to reflect the actual behavior.

**NIT-3: Tests missing newline at end of file**
Location: `tests/unit/formatPatientAge.spec.ts`, line 742

The test file appears to end at line 742 without a final newline. While this doesn't affect functionality, it's conventional to end files with a newline.

**NIT-4: Tests/README.md has formatting inconsistency**
Location: `tests/README.md`, line 260-262

The diff shows removal of the trailing newline (`\ No newline at end of file` changed to proper newline). This is good, but it's a diff artifact rather than an intentional change. Not an issue, just noting the change.

### Over-Engineering Pass

**No over-engineering detected.** The implementation is appropriately scoped:
- Three focused functions: `getPatientAgeBreakdown()`, `formatPatientAge()`, `formatPatientAgeTooltip()`
- No unnecessary abstractions or premature generalization
- Reuses existing `getRelativeDateSuffix()` helper
- Minimal changes to UI components (just wraps age text with tooltip)

### Security Pass

**No security issues detected:**
- No hardcoded credentials or secrets
- No SQL injection or XSS vulnerabilities
- Patient data (date_of_birth, deceased_datetime) handled appropriately
- No new dependencies introduced
- Uses existing Radix UI tooltip primitives (already in the project)
- No auth/authz changes

### Summary

The implementation correctly addresses all acceptance criteria with appropriate logic for each age range. However, there are **4 blocker issues** related to test expectations that must be fixed before the code can be considered working:
1. Tests expect abbreviated suffixes when calling with non-abbreviated mode
2. Tests expect no-space abbreviated format but implementation includes spaces  
3. PLAYWRIGHT_GUIDE.md has corrupted formatting
4. Test description doesn't match actual behavior

These are not implementation bugs but rather test bugs that would cause the test suite to fail.
