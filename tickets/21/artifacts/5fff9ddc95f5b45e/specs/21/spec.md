# Specification: Add infinite pagination in Dispense History selector

## Problem Statement

The Dispense History selector in `src/components/Medicine/DispenseOrderListSelector.tsx` currently fetches all dispense orders without pagination, displaying only whatever the API returns by default. For patients with more than 14 dispense orders, older records are not shown because the component lacks infinite scroll pagination to fetch additional pages as the user scrolls.

## Acceptance Criteria

### AC1: Initial load displays first page of dispense orders

**Given** a patient has 20 dispense orders  
**When** the user navigates to Encounter → Medicine → Dispense History  
**Then** the dispense order selector displays the first 14 dispense orders (ordered by creation date, most recent first)  
**And** the selector does not display all 20 orders at once

### AC2: Scrolling to bottom loads next page

**Given** the dispense order selector is displaying the first page of 14 dispense orders  
**And** there are more than 14 total dispense orders available  
**When** the user scrolls to the bottom of the dispense order list  
**Then** the next page of dispense orders is automatically fetched and appended to the list  
**And** a loading indicator is displayed while fetching  
**And** the previously loaded dispense orders remain visible

### AC3: Pagination stops when all records are loaded

**Given** the dispense order selector has loaded 20 out of 20 total dispense orders  
**When** the user scrolls to the bottom of the list  
**Then** no additional fetch request is made  
**And** no loading indicator is displayed

### AC4: Desktop and mobile views both support infinite scroll

**Given** the user is viewing the dispense history on a desktop (lg breakpoint)  
**When** they scroll through the sidebar dispense order list  
**Then** infinite pagination loads additional pages as described in AC2

**Given** the user is viewing the dispense history on mobile (below lg breakpoint)  
**When** they open the drawer and scroll through the dispense order list  
**Then** infinite pagination loads additional pages within the drawer as described in AC2

### AC5: Selected dispense order persists across pagination

**Given** the user has scrolled and loaded multiple pages of dispense orders  
**And** a dispense order from page 2 is currently selected  
**When** additional pages are loaded  
**Then** the selected dispense order remains selected  
**And** the selection UI state (highlight, indicator) is preserved

## Capability Notes

### Existing Infrastructure

- **Infinite query support**: The codebase uses `@tanstack/react-query` with `useInfiniteQuery` for paginated data. See:
  - `src/pages/Encounters/EncounterHistorySelector.tsx` (lines 278-334): Complete reference implementation with `useInfiniteQuery`, `react-intersection-observer`'s `useInView`, and scroll-triggered pagination
  - `src/components/Patient/allergy/list.tsx` (lines 74-98): Another working example
  
- **Intersection observer for scroll detection**: `react-intersection-observer` v9.15.1 is installed and actively used. Pattern:
  ```tsx
  const { ref, inView } = useInView();
  // ... place ref at bottom of list
  useEffect(() => {
    if (inView && hasNextPage) {
      fetchNextPage();
    }
  }, [inView, hasNextPage, fetchNextPage]);
  ```

- **API pagination support**: `dispenseOrderApi.list` in `src/types/emr/dispenseOrder/dispenseOrderApi.ts` (lines 8-13) returns `PaginatedResponse<DispenseOrderRead>` and supports `limit` and `offset` query parameters

- **Loading skeleton**: `CardListSkeleton` from `src/components/Common/SkeletonLoading` is already imported and can be reused for pagination loading state (currently used for initial load)

### What Needs Building

- **`DispenseOrderListSelector` migration**: Replace `useQuery` (line 37-46) with `useInfiniteQuery` following the pattern from `EncounterHistorySelector.tsx`
  
- **Scroll detection in list**: Add `useInView` ref at the bottom of the `DispenseOrderList` component (line 143-198) to detect when user scrolls near the end

- **Pagination trigger**: Implement `useEffect` to call `fetchNextPage` when the intersection observer ref enters view and `hasNextPage` is true

- **Loading indicator**: Display `CardListSkeleton` below the list when `isFetchingNextPage` is true

- **Drawer scroll support**: Ensure the infinite scroll works within the mobile drawer's `ScrollArea` (line 129 of `DispenseOrderListSelector.tsx`)

## Open Questions

[open] Should we maintain a page size of 14 to match the EncounterHistorySelector pattern, or use a different page size for dispense orders? - Product owner to confirm (defaulting to 14 based on existing patterns)

[open] Should there be a maximum number of pages loaded before requiring user action (e.g., a "Load More" button), or is pure infinite scroll acceptable for all use cases? - Product owner to confirm (defaulting to pure infinite scroll based on existing implementations)
