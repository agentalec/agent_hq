# Implementation Plan: Show user's role on user list cards

## Problem Analysis

The infrastructure to display roles on user cards already exists in the codebase. The `UserCard` component accepts a `roleName` prop and renders it when provided (line 118 of `UserListAndCard.tsx`). However, the role display is not consistently implemented across all user list views:

1. **Facility Users Grid View** - Currently passes `user.user_type` as `roleName` (line 162)
2. **Facility Users Table View** - Displays `user.user_type` in role column (line 220)
3. **Organization Users** - Already passes `userRole.role.name` as `roleName` (line 216)
4. **Facility Organization Users** - Already passes `userRole.role.name` as `roleName` (line 163)

The spec indicates that role display "was lost at some point", suggesting this is a regression where the role data exists but may not be rendered properly in some contexts.

## Implementation Approach

### Phase 1: Verify Current State
1. Confirm that `user.user_type` values are correctly populated in API responses
2. Verify that the `UserCard` component's `roleName` rendering logic (line 118) is functioning
3. Identify which specific user list views are missing role display

### Phase 2: Restore Role Display
Since the infrastructure already exists, the implementation focuses on ensuring:
1. The `roleName` prop is passed consistently across all user list contexts
2. The role values are properly transformed from machine-readable format (e.g., "nurse") to human-readable text (e.g., "Nurse")
3. Styling remains consistent with the spec's requirement (`text-sm text-gray-500`)

### Phase 3: Handle Edge Cases
1. Ensure graceful handling when role data is missing (AC #7)
2. Verify role display works in both card and table views (AC #1-2)
3. Test with all user types: doctor, nurse, staff, volunteer, administrator

## Files to Modify

### Frontend Repository (`agentalec/care_fe`)

1. **`src/components/Users/UserListAndCard.tsx`**
   - Primary file containing `UserCard`, `UserGrid`, and `UserList` components
   - Verify/fix `roleName` prop passing in `UserGrid` (line 162)
   - Ensure role transformation to readable format
   - Confirm styling matches spec requirements

2. **`src/pages/Organization/OrganizationUsers.tsx`** (verification only)
   - Already correctly passes `userRole.role.name` as `roleName` (line 216)
   - No changes needed unless testing reveals issues

3. **`src/pages/Facility/settings/organizations/FacilityOrganizationUsers.tsx`** (verification only)
   - Already correctly passes `userRole.role.name` as `roleName` (line 163)
   - No changes needed unless testing reveals issues

## Repositories Touched

- **`agentalec/care_fe`** (primary) - React frontend where user cards are rendered

No backend changes required as the user type data already exists in the API responses.

## New Dependencies

None. The implementation uses existing React components, TypeScript types, and styling utilities already present in the codebase.

## Testing Strategy

1. **Manual Testing**
   - Verify role display on facility users page (card view)
   - Verify role display on facility users page (table view)
   - Verify role display on organization users page
   - Verify role display on facility organization users page
   - Test with users of different roles (doctor, nurse, staff, volunteer, administrator)
   - Test with users missing role data

2. **Automated Testing**
   - Add Playwright tests to verify role visibility in user list cards
   - Test role display across different user types and contexts
   - Verify graceful handling of missing role data

## Implementation Complexity

**Low Complexity** - This is a display restoration ticket where the rendering infrastructure already exists. The work primarily involves:
- Verifying existing code paths
- Ensuring consistent prop passing
- Adding human-readable formatting if needed
- Testing across different contexts

No new components, APIs, or data models are required.
