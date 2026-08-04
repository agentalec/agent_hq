# Spec: Current Location Selector Hidden in Sidebar

## Problem Statement

The Current Location selector in the facility location sidebar displays the location name within a TooltipComponent that has responsive visibility classes (`hidden lg:block`). This causes the location name to be hidden on screens below the large breakpoint (< 1024px), making it difficult for users on tablets and smaller laptops to see which location they are currently viewing. The selector button itself is visible, but the location name inside it is not shown until the screen width exceeds the large breakpoint.

## Acceptance Criteria

1. Given a user is on a facility location page on any screen size, when viewing the sidebar, then the current location name should be visible without requiring a tooltip.
2. Given a user is on a screen below 1024px width, when the sidebar is expanded, then the current location name should display inline within the location selector button.
3. Given the location name is very long, when displayed in the selector, then it should truncate with ellipsis to prevent layout overflow while remaining readable.
4. Given a user hovers over the location selector on large screens (≥ 1024px), when a tooltip would provide additional context, then the full location name may optionally appear in a tooltip.
5. Given a user has the sidebar collapsed, when viewing the location switcher, then only the home icon should display (existing behavior maintained).

## Capability Notes

- `src/components/ui/sidebar/facility/location/location-switcher.tsx:LocationSwitcher` -- exists, renders the Current Location selector with TooltipComponent
- `src/components/ui/sidebar/facility/location/location-switcher.tsx:91-103` -- TooltipComponent with `className="hidden lg:block"` causes visibility issue on smaller screens
- `src/components/ui/tooltip.tsx` -- exists, provides tooltip functionality with responsive classes
- `src/components/ui/sidebar/app-sidebar.tsx:141` -- conditionally renders LocationSwitcher when locationId is present
- `public/locale/en.json:1661` -- "current_location" i18n key exists

## Open Questions

None.
