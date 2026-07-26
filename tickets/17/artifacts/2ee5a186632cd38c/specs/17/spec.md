# Ticket 17: Add Recall tab in mobile UI of queue board

## Problem Statement

The queue board currently displays "Ongoing" and "Finished" tabs on desktop, with the mobile UI showing separate "Waiting" and "Called + Now Serving" sections. However, recalled tokens (with `UNFULFILLED` status) are only accessible via a dialog triggered by the "Awaiting Recall" link in the desktop "Called + Now Serving" column. On mobile devices, users cannot easily view or manage recalled tokens, as the "Awaiting Recall" link is hidden on smaller screens. This creates an accessibility gap where mobile users cannot efficiently work with tokens that need to be recalled.

## Acceptance Criteria

### AC1: Add Recall tab on mobile UI
**Given** I am viewing the queue board on a mobile device (screen width < 1024px)  
**When** I navigate to the Ongoing tab of a queue  
**Then** I should see three tabs: "Waiting", "Called + Now Serving", and "Recall"

### AC2: Display recalled tokens in Recall tab
**Given** I am viewing the Recall tab on mobile  
**When** the tab loads  
**Then** I should see a list of tokens with `TokenStatus.UNFULFILLED` status for the current queue  
**And** each token should be displayed using the `OngoingQueueTokenCard` component  
**And** if there are no recalled tokens, I should see an empty state message

### AC3: Maintain desktop behavior
**Given** I am viewing the queue board on a desktop device (screen width >= 1024px)  
**When** I navigate to the Ongoing tab  
**Then** the "Awaiting Recall" link should remain visible in the "Called + Now Serving" column header  
**And** clicking it should open the `AwaitingRecallDialog` as it currently does  
**And** no Recall tab should be visible on desktop

### AC4: Token actions work correctly in Recall tab
**Given** I am viewing a recalled token in the mobile Recall tab  
**When** I open the token's action menu  
**Then** I should be able to perform all applicable actions (move to waiting, call to service point, mark as complete, cancel, etc.)  
**And** the actions should update the token status and refresh the appropriate tab views

### AC5: Badge count displays on Recall tab
**Given** I am viewing the mobile tabs and there are tokens with `UNFULFILLED` status  
**When** the tabs render  
**Then** the Recall tab should display a badge showing the count of `UNFULFILLED` tokens  
**And** the count should update automatically when tokens are moved in or out of recall status

## Capability Notes

### What the Repository Already Has

**Tab infrastructure:**
- `NavTabs` component (`src/components/ui/nav-tabs.tsx`) - Desktop tab system with dropdown for overflow tabs
- `Tabs`, `TabsList`, `TabsTrigger` components (`src/components/ui/tabs.tsx`) - Mobile tab system already used in `ManageQueueOngoingTab`

**Queue board structure:**
- `ManageQueue.tsx` - Main queue board page with `NavTabs` for "ongoing" and "completed" tabs
- `ManageQueueOngoingTab.tsx` (lines 138-153) - Mobile section toggle using `Tabs` component with "waiting" and "serving" values
- `ManageQueueFinishedTab.tsx` - Finished tokens tab

**Token display:**
- `OngoingQueueTokenCard.tsx` - Component for displaying individual tokens in ongoing view
- `OngoingQueueTokenCardsList` component (lines 455-508 in `OngoingQueueTokenCard.tsx`) - List wrapper with infinite scroll

**Recall functionality:**
- `AwaitingRecallDialog` function (lines 567-606 in `ManageQueueOngoingTab.tsx`) - Desktop dialog showing `UNFULFILLED` tokens
- `AwaitingRecallTrigger` component (lines 480-518 in `ManageQueueOngoingTab.tsx`) - Desktop button/link with count badge
- Token status enum (`src/types/tokens/token/token.ts`, lines 14-21) includes `UNFULFILLED` status
- `getTokenQueueStatusCount` utility (`src/pages/Facility/queues/utils.ts`) - Counts tokens by status

**Data fetching:**
- `useTokenListInfiniteQuery` hook (`src/pages/Facility/queues/utils.ts`) - Fetches paginated token lists with query params
- `tokenQueueApi.summary` endpoint - Provides status counts for badge display

### What Needs to Be Built

**Mobile tab addition:**
- Add "recall" value to the `mobileSection` state in `ManageQueueOngoingTab.tsx`
- Add a third `TabsTrigger` for "Recall" in the mobile `Tabs` component (after line 151)
- Add corresponding conditional display logic for the recall section (after line 189)

**Recall section UI:**
- Create a new `QueueColumn` wrapper for the Recall tab content
- Use `OngoingQueueTokenCardsList` with `qParams: { status: TokenStatus.UNFULFILLED }`
- Add appropriate empty state (similar to lines 174-180 for waiting tokens)

**Badge count integration:**
- Extract `UNFULFILLED` count from the existing `summary` query data
- Display count badge on Recall `TabsTrigger` (similar to existing "Waiting" count display)

**Responsive hiding:**
- Ensure the desktop `AwaitingRecallTrigger` remains visible on large screens (already implemented via `className="lg:hidden"` on mobile tabs)
- The existing `AwaitingRecallDialog` on desktop should continue to work unchanged

## Open Questions

1. [open] Should the Recall tab be positioned as the middle tab (Waiting, Recall, Called + Now Serving) or as the third tab (Waiting, Called + Now Serving, Recall)? _Resolved by: Product team / UX designer_

2. [open] Should the badge count on the Recall tab use the same style as the "Waiting" and "Called + Now Serving" tabs, or should it have a distinct visual treatment to emphasize urgency? _Resolved by: Product team / UX designer_

3. [open] On desktop, should the "Awaiting Recall" link remain as-is, or should we consider also adding a full "Recall" column to the desktop view for consistency? _Resolved by: Product team / UX designer - assuming desktop stays as-is for this ticket_
