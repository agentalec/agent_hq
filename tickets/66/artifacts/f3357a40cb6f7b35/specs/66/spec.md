# Spec: Add infinite pagination in Dispense History selector

## Problem

The dispense history selector in Encounter → Medicine → Dispense History loads all dispense orders without pagination, causing performance issues for patients with many dispense records. The component should implement infinite scroll to load dispense orders progressively as the user scrolls.

## Acceptance Criteria

1. Given a patient has more than 14 dispense orders, when the dispense history tab loads, then only the first 14 dispense orders appear in the selector.
2. Given the user scrolls to the bottom of the dispense order list, when there are more dispense orders available, then the next page of 14 orders loads automatically.
3. Given dispense orders are being loaded, when the user scrolls to the trigger point, then a loading indicator appears at the bottom of the list.
4. Given all dispense orders have been loaded, when the user scrolls to the bottom, then no loading indicator appears and no additional fetch occurs.
5. Given the component is loading the initial page, when the query is executing, then the existing skeleton loader displays.
6. Given infinite pagination is active, when the selected dispense order ID is set, then the component auto-selects the first order if not already selected.

## Capability Notes

- `src/components/Medicine/DispenseOrderListSelector.tsx` -- existing component using `useQuery` without pagination; needs conversion to `useInfiniteQuery`
- `src/pages/Encounters/EncounterHistorySelector.tsx:211-346` -- reference implementation using `useInfiniteQuery`, `useInView`, and `fetchNextPage` pattern
- `src/types/emr/dispenseOrder/dispenseOrderApi.ts:9-13` -- API endpoint returns `PaginatedResponse<DispenseOrderRead>` supporting limit/offset params
- `react-intersection-observer` library (`useInView` hook) -- already installed, used for scroll detection
- `@tanstack/react-query` (`useInfiniteQuery`) -- already installed, supports infinite pagination

## Open Questions

None.
