# Implementation Tasks: Current Location Selector Hidden in Sidebar

This document breaks down the implementation plan into ordered, actionable tasks for the `agentalec/care_fe` repository.

## Task 1: Refactor Location Switcher Component to Remove Responsive Tooltip Wrapper

**Repository:** `agentalec/care_fe`

**What it touches:**
- `src/components/ui/sidebar/facility/location/location-switcher.tsx` (lines 88-104)

**Dependencies:**
- None (standalone task)

**Acceptance Criteria Coverage:**
- ✅ AC1: Current location name visible without requiring tooltip (all screen sizes)
- ✅ AC2: Location name displays inline on screens < 1024px when sidebar expanded
- ✅ AC3: Long location names truncate with ellipsis
- ✅ AC4: Optional tooltip on large screens for full name (implementation choice)
- ✅ AC5: Collapsed sidebar shows only home icon (existing behavior)

**Implementation Details:**

1. **Remove the problematic TooltipComponent wrapper** (lines 91-103) that has `className="hidden lg:block"`
2. **Display the location name directly** within the button structure:
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
3. **Optionally add a tooltip** that appears only on large screens for showing full name on hover:
   ```tsx
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
   ```
4. **Maintain existing behavior** when sidebar is collapsed (only home icon shows)
5. **Ensure proper truncation** using `truncate` class to prevent layout overflow

**Verification Steps:**
- Test on mobile (< 640px): Location name visible when sidebar expanded
- Test on tablet (640px - 1023px): Location name visible when sidebar expanded
- Test on desktop (≥ 1024px): Location name visible, optional tooltip shows full name on hover
- Test with long location names: Truncation with ellipsis works correctly
- Test with collapsed sidebar: Only home icon displays (existing behavior maintained)
- Screen reader accessibility: Location name is accessible without hovering

**Estimated Changed Lines:** ~20-30 lines (refactoring existing component)

---

## Coverage Verification

All acceptance criteria from `spec.md` are covered by Task 1:

- **AC1** (Current location name visible without requiring tooltip): ✅ Covered by Task 1 - location name displayed directly
- **AC2** (Location name displays inline on screens < 1024px): ✅ Covered by Task 1 - removes `hidden lg:block` from primary display
- **AC3** (Long location names truncate with ellipsis): ✅ Covered by Task 1 - uses `truncate` class
- **AC4** (Optional tooltip on large screens): ✅ Covered by Task 1 - optional tooltip implementation
- **AC5** (Collapsed sidebar shows only home icon): ✅ Covered by Task 1 - maintains existing behavior

**Total Tasks:** 1  
**Total Repositories:** 1 (agentalec/care_fe)
