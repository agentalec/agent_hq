# Implementation Plan: Organization missing in Edit Patient State

## Problem Analysis

The patient edit flow correctly sets the `geo_organization` field value (line 222 of PatientRegistration.tsx) but fails to properly populate the `_selected_levels` array that drives the GovtOrganizationPicker UI component. On line 235, the code sets `_selected_levels: [data.geo_organization]`, which creates an array with either a valid Organization object or `undefined` when no organization exists. The GovtOrganizationPicker expects this array to contain only valid Organization objects or be empty.

## Root Cause

The issue occurs at `src/components/Patient/PatientRegistration.tsx:235`:
```typescript
_selected_levels: [data.geo_organization],
```

This line doesn't filter out `undefined` values, resulting in `[undefined]` when a patient has no geo_organization, which causes the picker to render incorrectly or not display the field at all.

## Solution Approach

Fix the form reset logic to properly handle both cases:
1. When `data.geo_organization` exists: populate `_selected_levels` with a valid organization object
2. When `data.geo_organization` is undefined/null: set `_selected_levels` to an empty array `[]`

The fix is a one-line change:
```typescript
_selected_levels: data.geo_organization ? [data.geo_organization] : [],
```

This ensures:
- Existing organization hierarchy displays correctly when editing
- The picker shows properly when no organization is set (allowing users to add one)
- The validation logic for required organization fields works as expected
- The form's dirty state tracking correctly identifies changes to organization

## Implementation Details

### File to Modify
- `src/components/Patient/PatientRegistration.tsx` (line 235)

### Change Required
Replace:
```typescript
_selected_levels: [data.geo_organization],
```

With:
```typescript
_selected_levels: data.geo_organization ? [data.geo_organization] : [],
```

### Testing Strategy
1. **Test Case 1**: Edit patient with existing geo_organization
   - Navigate to patient with organization set
   - Click edit from Demographics tab
   - Verify GovtOrganizationPicker displays with current hierarchy pre-populated
   - Change organization selection
   - Save and verify organization updated

2. **Test Case 2**: Edit patient without geo_organization
   - Navigate to patient without organization
   - Click edit from Demographics tab
   - Verify GovtOrganizationPicker is visible and empty
   - Select an organization
   - Save and verify organization saved

3. **Test Case 3**: Required organization validation
   - Edit patient where organization is required by config
   - Clear organization field
   - Attempt to save
   - Verify validation error prevents submission

4. **Test Case 4**: Navigation prompt for unsaved changes
   - Edit patient and modify geo_organization
   - Click back without saving
   - Verify unsaved changes warning appears

## Repositories Touched
- `agentalec/care_fe` (frontend only)

## Dependencies
None. This is a bug fix to existing functionality with no new dependencies.

## Risk Assessment
- **Low risk**: Single-line conditional fix to form initialization logic
- **No API changes**: Backend already supports geo_organization field in PatientUpdate
- **No schema changes**: Organization field already exists in patient model
- **Backward compatible**: Handles both existing and missing organization data gracefully

## Acceptance Criteria Coverage
- ✅ AC1: GovtOrganizationPicker visible and pre-populated when editing patient with organization
- ✅ AC2: Organization changes save successfully via patient update API
- ✅ AC3: GovtOrganizationPicker visible when editing patient without organization
- ✅ AC4: Validation error prevents submission when organization required but missing
- ✅ AC5: geo_organization field visible in Additional Details accordion section (already present)
- ✅ AC6: Navigation prompt warns about unsaved changes (form dirty tracking works correctly with fix)
