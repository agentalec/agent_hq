# Review: Ticket 17 - Add Recall tab in mobile UI of queue board

## Round 1

### Acceptance Criteria Review

#### AC1: Add Recall tab on mobile UI ✅
**Status:** PASS

The implementation correctly adds three tabs to the mobile UI:
- Line 71-73: Updated `mobileSection` state to include `"recall"` type
- Line 162-169: Added third `TabsTrigger` with value "recall" displaying the translated label
- Line 143: The Tabs component is correctly scoped to mobile with `className="lg:hidden"`

#### AC2: Display recalled tokens in Recall tab ✅
**Status:** PASS

The Recall tab correctly displays recalled tokens:
- Line 301-327: New recall section div with conditional mobile display
- Line 308-326: Uses `QueueColumn` wrapper with `OngoingQueueTokenCardsList`
- Line 312-316: Query params correctly specify `status: TokenStatus.UNFULFILLED` and pass through filters
- Line 317-324: Appropriate empty state with `EyeIcon` and translated message using `t("no_tokens_awaiting_recall")`
- The `no_tokens_awaiting_recall` i18n key exists at line 3928 in `public/locale/en.json`

#### AC3: Maintain desktop behavior ✅
**Status:** PASS

Desktop behavior is correctly maintained:
- Line 143: Mobile tabs hidden on desktop with `className="lg:hidden"`
- Line 305: Recall section explicitly hidden on desktop with `"hidden lg:hidden"`
- Lines 213-223: Desktop `AwaitingRecallTrigger` remains intact in the "Called + Now Serving" column header
- The existing `AwaitingRecallDialog` functionality is unchanged

#### AC4: Token actions work correctly in Recall tab ✅
**Status:** PASS

Token actions will work correctly because:
- Line 309-326: Uses the standard `OngoingQueueTokenCardsList` component
- This component renders individual `OngoingQueueTokenCard` components with full action menu support
- All token actions (move to waiting, call to service point, mark as complete, cancel) are available via the card's context menu and dropdown menu

#### AC5: Badge count displays on Recall tab ✅
**Status:** PASS

Badge count is correctly implemented:
- Line 164-167: Badge displays count using `getTokenQueueStatusCount(summary, TokenStatus.UNFULFILLED)`
- Line 76-82: Summary data query with auto-refresh every 10 seconds when enabled
- The badge pattern matches the existing "Waiting" (lines 148-152) and "Called + Now Serving" (lines 156-160) tabs

### Blockers

#### 1. PLAYWRIGHT_GUIDE.md formatting corruption
**Severity:** blocker  
**Location:** `tests/PLAYWRIGHT_GUIDE.md` lines 90-94

The implementation accidentally removed line breaks from the "Common URLs" code block, concatenating all URLs into unreadable strings:

```typescript
// Before (correct):
`/facility/${facilityId}/overview`
`/facility/${facilityId}/settings/locations`

// After (broken):
`/facility/${facilityId}/overview``/facility/${facilityId}/settings/locations``/facility/${facilityId}/settings/departments`
```

This makes the documentation unreadable and breaks the code examples. The diff shows this was an accidental formatting change unrelated to the ticket's scope.

**Fix required:** Restore proper line breaks in the code block at lines 90-94.

### Should-Fix

None identified.

### Nits

#### 1. Unrelated whitespace change in tests/README.md
**Severity:** nit  
**Location:** `tests/README.md` line 140

The diff adds a newline at the end of the file. While this follows Unix conventions, it's unrelated to the ticket scope.

### Over-Engineering Pass

**Status:** PASS

The implementation is appropriately minimal:
- Reuses existing components (`OngoingQueueTokenCardsList`, `QueueColumn`, `Badge`)
- No new abstractions or utilities introduced
- No speculative features or unused flexibility
- Follows the established pattern from the existing "Waiting" and "Serving" tabs

### Security Pass

**Status:** PASS

No security concerns identified:
- No new dependencies introduced
- No hardcoded secrets or credentials
- Token status filtering happens server-side via the `tokenQueueApi` endpoint
- Uses standard query params with proper TypeScript typing
- No injection points or missing authorization checks

### Summary

The implementation successfully meets all five acceptance criteria and correctly implements the Recall tab for mobile UI. The code reuses existing components appropriately and follows established patterns. However, there is one blocking issue: accidental formatting corruption in `tests/PLAYWRIGHT_GUIDE.md` that must be fixed before the implementation can be accepted.

**Blockers:** 1  
**Should-fix:** 0  
**Nits:** 1
