# Summary: Add infinite pagination in Dispense History selector

## What was done

Added infinite pagination to the dispense history selector in Encounter → Medicine → Dispense History. The selector now loads dispense orders progressively as the user scrolls instead of loading all records at once.

**Implementation:**
- Converted `DispenseOrderListSelector.tsx` from `useQuery` to `useInfiniteQuery`
- Integrated `useInView` hook from `react-intersection-observer` for scroll detection
- Added loading indicator with spinner and internationalized text
- Implemented auto-selection of first order when no dispense order is selected
- Used 14-item page size with offset-based pagination

**Acceptance criteria met:**
- ✅ AC1: Initial load shows only first 14 dispense orders
- ⚠️ AC2: Next page loads automatically when scrolling (not exercised due to insufficient test data)
- ⚠️ AC3: Loading indicator appears during page fetch (not exercised due to insufficient test data)
- ✅ AC4: No loading indicator when all orders loaded
- ✅ AC5: Skeleton loader displays during initial load
- ✅ AC6: First order auto-selected when dispense order ID not set

**Review outcome:** Clean after one round. Round 1 identified a formatting issue in `tests/PLAYWRIGHT_GUIDE.md` (URL concatenation); fixed in Round 2.

**QA outcome:** Passed all exercisable criteria. AC2 and AC3 could not be fully exercised due to test fixture containing only 4 dispense orders (less than the 14-item page size). Code review confirms correct implementation following the reference pattern from `EncounterHistorySelector.tsx`.

**Commits:**
- `65b2f61a0` feat: add infinite pagination to dispense history selector
- `61c3216bc` fix: restore newlines in URL examples in PLAYWRIGHT_GUIDE
