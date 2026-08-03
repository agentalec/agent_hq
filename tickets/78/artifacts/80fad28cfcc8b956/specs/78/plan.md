# Implementation Plan: Current Location Selector Hidden in Sidebar

## Problem Summary

The Current Location selector in the facility location sidebar wraps the location name display inside a `TooltipComponent` with responsive visibility classes (`hidden lg:block`). This causes the location name to be hidden on screens below 1024px width, making it inaccessible to users on tablets and smaller laptops. Only the selector button chrome remains visible, not the critical location name content.

## Root Cause

In `src/components/ui/sidebar/facility/location/location-switcher.tsx` lines 91-103, the `TooltipComponent` wrapper has `className="hidden lg:block"` which applies Tailwind's responsive display utilities. This hides the entire tooltip (and its children) below the large breakpoint, even though the tooltip's children contain the primary location name display, not supplementary information.

## Implementation Approach

### 1. Remove Tooltip Wrapper from Primary Display

The location name display should not be wrapped in a tooltip component for primary visibility. Instead:

1. **Remove the TooltipComponent wrapper** (lines 91-103) and display the location name directly in the button
2. **Maintain the existing structure** of the location name display (label + name with truncation)
3. **Optionally add a tooltip on large screens** only if there's a UX benefit (e.g., showing full name on hover when truncated)

### 2. Responsive Display Strategy

The display should be visible at all screen sizes when the sidebar is expanded:

```tsx
<div className="flex min-w-0 flex-col items-start">
  <span className="text-xs text-gray-500">
    {t("current_location")}
  </span>
  <span className="w-full truncate text-left text-sm font-medium text-gray-900">
    {location?.name}
  </span>
</div>
```

### 3. Optional Enhancement for Large Screens

If a tooltip provides value on large screens (showing full name when truncated), wrap only the name span with a tooltip that appears on hover:

```tsx
<div className="flex min-w-0 flex-col items-start">
  <span className="text-xs text-gray-500">
    {t("current_location")}
  </span>
  <Tooltip>
    <TooltipTrigger asChild>
      <span className="w-full truncate text-left text-sm font-medium text-gray-900">
        {location?.name}
      </span>
    </TooltipTrigger>
    <TooltipContent side="right" className="hidden lg:block">
      {location?.name}
    </TooltipContent>
  </Tooltip>
</div>
```

This approach ensures:
- The location name is always visible when sidebar is expanded (all screen sizes)
- Truncation prevents overflow
- Optional tooltip on large screens provides full name on hover
- The `hidden lg:block` class, if used, is applied to the tooltip content popup, not the primary display

## Files to Modify

### Repository: `agentalec/care_fe`

1. **`src/components/ui/sidebar/facility/location/location-switcher.tsx`**
   - Lines 88-104: Refactor the location name display within the button
   - Remove `TooltipComponent` wrapper with `hidden lg:block` class
   - Display location name directly with proper truncation
   - Optionally add hover tooltip on large screens only

## Testing Strategy

1. **Visual verification** on multiple screen sizes:
   - Mobile (< 640px): Sidebar expanded state should show location name
   - Tablet (640px - 1023px): Location name visible
   - Desktop (≥ 1024px): Location name visible, optional tooltip on hover
2. **Layout verification**: Long location names truncate with ellipsis
3. **Accessibility**: Screen reader can access location name without hovering
4. **Collapsed sidebar**: Only home icon shows (existing behavior maintained)

## Dependencies

No new dependencies required. This is a pure refactoring of existing components using established UI patterns.

## Acceptance Criteria Coverage

- ✅ AC1: Current location name visible without requiring tooltip (all screen sizes)
- ✅ AC2: Location name displays inline on screens < 1024px when sidebar expanded
- ✅ AC3: Long location names truncate with ellipsis
- ✅ AC4: Optional tooltip on large screens for full name (implementation choice)
- ✅ AC5: Collapsed sidebar shows only home icon (existing behavior)

## Risk Assessment

**Low risk**: This is a localized UI change affecting only the location switcher component. No API changes, no data model changes, no authorization changes.

## Rollback Plan

If issues arise, the change is easily reversed by restoring the original `TooltipComponent` wrapper pattern. However, the fix is straightforward and low-risk.
