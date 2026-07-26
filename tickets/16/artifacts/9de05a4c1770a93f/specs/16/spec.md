# Spec: Enhance service points list in queue board

## Problem Statement

The queue board currently displays all assigned service points simultaneously in the "Called + Now Serving" section, which creates a cluttered interface, especially on mobile devices. On desktop, the service point selection dropdown is separate from the serving section, making it less intuitive. This ticket aims to reorganize the UI by moving the service point dropdown into the serving section on desktop and implementing a focused single-service-point view on mobile with improved token card UI/UX.

## Acceptance Criteria

### AC1: Desktop service point dropdown placement
**Given** a user is viewing the queue board on a desktop viewport (≥1024px)  
**When** they navigate to the "Called + Now Serving" section  
**Then** the service point dropdown should appear at the top of the serving section (instead of being separate)  
**And** the background of the serving section should have a visually distinct background color (currently `bg-gray-200`)  
**And** the dropdown should function identically to the existing `ServicePointsDropDown` component for selecting which service points to display

### AC2: Mobile single service point view
**Given** a user is viewing the queue board on a mobile viewport (<1024px)  
**When** they are in the "Called + Now Serving" tab  
**Then** only one service point should be visible at a time  
**And** a dropdown selector should be present above the service point display  
**And** the user can select a different service point from the dropdown  
**And** the view should update to show only the selected service point's tokens

### AC3: Mobile service point navigation
**Given** a user has selected a service point on mobile  
**When** they open the service point dropdown  
**Then** all available service points should be listed  
**And** the currently selected service point should be visually indicated  
**And** selecting a new service point should immediately update the display without page refresh

### AC4: Token card UI consistency
**Given** tokens are displayed in either desktop or mobile view  
**When** the service point display is updated  
**Then** token cards should maintain consistent styling and functionality  
**And** all token actions (mark as serving, move to waiting, complete, etc.) should continue to work  
**And** the "Call Next Patient" button should remain visible when no patient is being served

### AC5: Desktop multi-service-point display
**Given** a user is on desktop and has multiple service points selected via the dropdown  
**When** viewing the "Called + Now Serving" section  
**Then** all selected service points should be displayed vertically with separators  
**And** each service point should show its name, category, "Now Serving" tokens, and "Called" tokens  
**And** the layout should match the existing pattern from `ManageQueueOngoingTab.tsx` lines 208-278

## Capability Notes

### Existing Functionality

- **Service point dropdown**: `src/pages/Facility/queues/ServicePointsDropDown.tsx` provides a working dropdown with multi-select checkboxes for service points. Uses responsive breakpoints to show 1-6 service point badges depending on screen size (lines 21-26).

- **Service point state management**: `src/pages/Facility/queues/useQueueServicePoints.ts` manages selected service points via Jotai atom with localStorage persistence. Provides `assignedServicePointIds`, `assignedServicePoints`, and `toggleServicePoint` function (lines 37-60).

- **Current serving section layout**: `src/pages/Facility/queues/ManageQueueOngoingTab.tsx` lines 185-282 render the "Called + Now Serving" column with service points mapped vertically. Each service point has `bg-gray-200` background and includes category info, "Now Serving" section, and "Called" tokens.

- **Mobile/desktop responsive sections**: `ManageQueueOngoingTab.tsx` lines 138-153 implement mobile tabs ("waiting" vs "serving") using state and CSS classes. Desktop shows both columns side-by-side (line 155).

- **Token cards**: `src/pages/Facility/queues/OngoingQueueTokenCard.tsx` renders token cards with context menu actions. Uses `OngoingQueueTokenCardsList` component to fetch and display tokens with infinite scroll.

### What Needs Building

- **Desktop**: Move `ServicePointsDropDown` component into the "Called + Now Serving" section header (currently it's not present in `ManageQueueOngoingTab.tsx`). Adjust layout to position it as part of the serving column's header.

- **Mobile**: Implement single-service-point mode. Add a new mobile-specific dropdown (can reuse parts of `ServicePointsDropDown` but simplified to single-select) and filter the service points array to show only the selected one.

- **Mobile state**: Add mobile-specific state (e.g., `selectedServicePointId` for mobile view) to track which single service point is active on mobile. This should be independent of the multi-select desktop state.

- **Background styling**: Verify that the serving section has the appropriate `bg-gray-200` or similar background as per design requirements. Current implementation has this for individual service point containers (line 213).

## Open Questions

1. **[open]** Should the mobile dropdown allow users to view "All" service points (like desktop), or must they always select exactly one? Resolution: Product owner or designer should clarify desired mobile UX.

2. **[open]** When a user switches from desktop to mobile (or vice versa), should the mobile selection default to the first assigned service point from desktop's multi-select, or should there be separate state persistence? Resolution: Product owner decision on state synchronization strategy.

3. **[open]** Should the desktop service point dropdown retain its existing multi-select checkbox UI when moved into the serving section header, or should it have a different visual treatment? Resolution: Designer should provide UI mockup or clarification.

4. **[open]** On mobile, if no service point is explicitly selected, should the system default to the first available service point or show a prompt to select one? Resolution: Product owner to define default behavior.
