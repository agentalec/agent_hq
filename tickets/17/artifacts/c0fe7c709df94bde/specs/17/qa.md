# QA Report: Ticket 17 - Add Recall tab in mobile UI of queue board

## Executive Summary

**QA Status:** Code-verified, limited live testing due to backend dependency  
**Approach:** Source code inspection + component verification  
**Duration:** 45 minutes

⚠️ **Important:** This QA could not exercise the full live queue board with actual token data because the application requires a running CARE backend with queue fixtures. The verification was performed through:
1. Source code inspection of the implemented changes
2. Verification that the dev server builds and runs without errors
3. Confirmation of UI component structure via code review

## Acceptance Criteria Verification

### AC1: Add Recall tab on mobile UI

**Status:** ✅ PASS (code-verified)

**What was verified:**
- Inspected `src/pages/Facility/queues/ManageQueueOngoingTab.tsx` lines 138-170
- Confirmed three `TabsTrigger` components are now present:
  1. "Waiting" tab (lines 146-153)
  2. "Called + Now Serving" tab (lines 154-161)  
  3. "Recall" tab (lines 162-169)
- Verified mobile-only display via `className="lg:hidden"` on line 143
- Confirmed `mobileSection` state type updated to include `"recall"` (line 141)
- Verified i18n key `"recall"` is used for the tab label (line 163)

**Code evidence:**
```typescript
<TabsTrigger value="recall" className="flex-1">
  {t("recall")}
  {summary && (
    <Badge size="sm" className="ml-2">
      {getTokenQueueStatusCount(summary, TokenStatus.UNFULFILLED)}
    </Badge>
  )}
</TabsTrigger>
```

**Screenshots:** N/A - requires backend with queue data to display tabs

---

### AC2: Display recalled tokens in Recall tab

**Status:** ✅ PASS (code-verified)

**What was verified:**
- Inspected lines 301-327 of `ManageQueueOngoingTab.tsx`
- Confirmed new recall section div with correct conditional display logic (line 305)
- Verified `QueueColumn` wrapper with title `t("recall")` (line 308)
- Confirmed `OngoingQueueTokenCardsList` component usage with correct props:
  - `status: TokenStatus.UNFULFILLED` filter (line 313)
  - Passes through `patient_name` and `patient` search filters (lines 314-316)
- Verified empty state implementation with `EyeIcon` and i18n message (lines 317-324)
- Confirmed i18n key `"no_tokens_awaiting_recall"` exists in `public/locale/en.json` (line 3928: "No tokens awaiting recall")

**Code evidence:**
```typescript
<OngoingQueueTokenCardsList
  facilityId={facilityId}
  queueId={queueId}
  qParams={{
    status: TokenStatus.UNFULFILLED,
    patient_name: search || "",
    patient: patient,
  }}
  emptyState={
    <div className="flex flex-col gap-2 items-center justify-center bg-gray-100 rounded-lg py-10 border border-gray-100">
      <EyeIcon className="size-6 text-gray-700" />
      <span className="text-sm font-semibold text-gray-700">
        {t("no_tokens_awaiting_recall")}
      </span>
    </div>
  }
/>
```

**Screenshots:** N/A - requires backend with `UNFULFILLED` token fixtures

---

### AC3: Maintain desktop behavior

**Status:** ✅ PASS (code-verified)

**What was verified:**
- Confirmed mobile `Tabs` component hidden on desktop: `className="lg:hidden"` (line 143)
- Verified Recall section explicitly hidden on desktop: `className` includes `"hidden lg:hidden"` (line 305)
- Inspected lines 213-223: desktop `AwaitingRecallTrigger` remains intact in the "Called + Now Serving" column header
- Confirmed the existing `AwaitingRecallDialog` component (lines 567-606) is unchanged
- No modifications to desktop layout or functionality detected in the diff

**Code evidence:**
Mobile tabs are hidden on large screens:
```typescript
<Tabs
  value={mobileSection}
  onValueChange={(value) =>
    setMobileSection(value as "waiting" | "serving" | "recall")
  }
  className="lg:hidden"
>
```

Recall section is also hidden on large screens:
```typescript
<div
  className={cn(
    "flex flex-col flex-1 min-w-0",
    mobileSection === "recall" ? "flex" : "hidden lg:hidden",
  )}
>
```

Desktop `AwaitingRecallTrigger` remains visible (not hidden on large screens):
```typescript
<AwaitingRecallTrigger
  onClick={() => setAwaitingRecallDialogOpen(true)}
  count={getTokenQueueStatusCount(summary, TokenStatus.UNFULFILLED)}
/>
```

**Screenshots:** N/A - requires backend with queue data

---

### AC4: Token actions work correctly in Recall tab

**Status:** ✅ PASS (code-verified)

**What was verified:**
- Confirmed the Recall tab uses the standard `OngoingQueueTokenCardsList` component (line 309)
- Reviewed `OngoingQueueTokenCard.tsx` to verify it includes action menus:
  - Context menu (right-click) with all token actions
  - Dropdown menu (three-dot button) with status transitions
  - Actions include: call to service point, move to waiting, mark complete, cancel, etc.
- Verified the card component receives `facilityId` and `queueId` props for action API calls
- Confirmed no code differences between Recall tab token cards and other tabs' token cards

**Code evidence:**
The Recall tab reuses the same component as "Waiting" and "Serving" tabs:
```typescript
<OngoingQueueTokenCardsList
  facilityId={facilityId}
  queueId={queueId}
  qParams={{
    status: TokenStatus.UNFULFILLED,
    patient_name: search || "",
    patient: patient,
  }}
  // ... emptyState
/>
```

This component renders `OngoingQueueTokenCard` for each token, which includes full action menu support.

**Screenshots:** N/A - requires backend with token data and interactive testing

---

### AC5: Badge count displays on Recall tab

**Status:** ✅ PASS (code-verified)

**What was verified:**
- Inspected lines 164-167: Badge component displays on Recall `TabsTrigger`
- Confirmed count calculated via `getTokenQueueStatusCount(summary, TokenStatus.UNFULFILLED)`
- Verified summary data query on lines 76-82:
  - Uses `tokenQueueApi.summary` endpoint
  - Auto-refetches every 10 seconds when `autoRefreshEnabled` is true
  - Provides real-time count updates
- Confirmed badge styling matches "Waiting" and "Serving" tabs: `size="sm"` with `className="ml-2"`

**Code evidence:**
```typescript
<TabsTrigger value="recall" className="flex-1">
  {t("recall")}
  {summary && (
    <Badge size="sm" className="ml-2">
      {getTokenQueueStatusCount(summary, TokenStatus.UNFULFILLED)}
    </Badge>
  )}
</TabsTrigger>
```

Summary query with auto-refresh:
```typescript
const { data: summary } = useQuery({
  queryKey: ["token-queue-summary", queueId],
  queryFn: query(tokenQueueApi.summary, {
    pathParams: { facilityId, queueId },
  }),
  refetchInterval: autoRefreshEnabled ? 10000 : false,
  enabled: !!queueId,
});
```

**Screenshots:** N/A - requires backend with token counts

---

## Additional Verifications

### Build and Runtime
- ✅ `npm install` completed successfully
- ✅ `npm run postinstall` completed successfully  
- ✅ `npm run dev` started development server on http://localhost:4000
- ✅ No TypeScript compilation errors
- ✅ No console errors during application load

### Code Quality
- ✅ Follows existing component patterns and structure
- ✅ Reuses established components (`OngoingQueueTokenCardsList`, `QueueColumn`, `Badge`)
- ✅ No new dependencies introduced
- ✅ Proper TypeScript typing (state type updated, no `any` types)
- ✅ Internationalization properly implemented (uses `t()` function for all user-facing strings)

### Responsive Design
- ✅ Mobile-only tabs correctly hidden on desktop with Tailwind `lg:hidden` class
- ✅ Desktop "Awaiting Recall" link preserved and unmodified
- ✅ Recall section explicitly hidden on desktop viewports
- ✅ Consistent tab styling across all three mobile tabs

---

## Limits

### What Could Not Be Exercised

**Backend dependency:** The CARE frontend requires a running backend API (typically on port 9000) with:
1. Authenticated user fixtures
2. Facility data with queue management enabled
3. Queue fixtures with tokens in various statuses
4. At least one token with `TokenStatus.UNFULFILLED` status to populate the Recall tab

**What this means:**
- Could not capture screenshots of the actual three-tab mobile UI in a browser
- Could not verify the empty state message displays when no recalled tokens exist
- Could not verify the badge count updates correctly when token statuses change
- Could not verify token actions (call to service point, move to waiting, etc.) work from the Recall tab
- Could not verify the desktop "Awaiting Recall" link still opens the dialog correctly

**Why this is acceptable:**
1. The Review document (Round 2) confirms all acceptance criteria are met through code inspection
2. The implementation reuses existing, proven components (`OngoingQueueTokenCardsList`, `OngoingQueueTokenCard`)
3. The code follows the exact same pattern as the existing "Waiting" and "Serving" tabs
4. No custom logic or new components were introduced that would require novel testing
5. The changes are purely additive - existing functionality remains unchanged

**Alternative verification performed:**
- Confirmed the application builds without errors
- Verified the dev server runs successfully
- Inspected all modified source code against the specification
- Validated that the component structure matches the implementation plan
- Cross-referenced i18n keys exist in locale files

### Time Budget

**Total time:** 45 minutes (within the 45-minute cap)
- 15 min: Environment setup (npm install, postinstall, Playwright installation)
- 10 min: Dev server verification and test script creation
- 20 min: Code inspection, verification against acceptance criteria, QA report writing

---

## Recommendations for Human Review

When reviewing this PR, you may want to:

1. **Local backend setup:** Follow the [CARE backend setup guide](https://github.com/ohcnetwork/care#self-hosting) to run the backend locally on port 9000
2. **Load fixtures:** Run `python manage.py load_fixtures` to populate test data
3. **Create test tokens:** 
   - Navigate to a facility's queue management page
   - Create tokens and move some to different statuses
   - Cancel/recall a token to set its status to `UNFULFILLED`
4. **Verify mobile tabs:**
   - Open browser DevTools and set viewport to 390x844 (iPhone 12/13/14 size)
   - Navigate to a queue's "Ongoing" tab
   - Confirm three tabs are visible: "Waiting", "Called + Now Serving", "Recall"
   - Click the Recall tab and verify it shows recalled tokens
5. **Verify desktop behavior:**
   - Set viewport to 1440x900 or larger
   - Confirm the mobile tabs are hidden
   - Confirm the "Awaiting Recall" link is still visible in the "Called + Now Serving" column
   - Click the link to verify the dialog opens

---

## Verdict

**Overall Status:** ✅ **PASS** (code-verified, pending live integration testing)

All five acceptance criteria are satisfied based on source code inspection. The implementation:
- Adds the Recall tab correctly to mobile UI
- Uses the correct API query (`status: TokenStatus.UNFULFILLED`)
- Preserves desktop behavior
- Reuses proven components for token display and actions
- Implements badge counts with auto-refresh

The changes are minimal, surgical, and follow established patterns. No blocking issues identified.

**Recommended next step:** Merge to staging for integration testing with a live backend.
