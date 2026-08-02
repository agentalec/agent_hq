# Review: Highlight medicine dosages which aren't 1

## Round 1

- **blocker** `tests/PLAYWRIGHT_GUIDE.md:90` — URLs accidentally concatenated without newlines or commas; restore original formatting with separate lines.

## Round 2

- **blocker** No tests included — Engineering conventions require "Every implementation task ships tests for the code it adds." Add unit tests for `isNonStandardDosage()` covering: value="1" returns false, value="2"/"0.5"/"1.5" return true, dose_range with non-1 values, and undefined/missing values.
- **should-fix** `src/components/Medicine/utils.ts:27` — String comparison `value !== "1"` will incorrectly flag "1.0" or "1.00" as non-standard; use numeric comparison: `parseFloat(dose_quantity.value) !== 1` (same for dose_range.low and dose_range.high).
