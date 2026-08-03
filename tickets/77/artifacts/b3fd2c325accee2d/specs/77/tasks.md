# Implementation Tasks: Organization missing in Edit Patient State

## Task 1: Fix geo_organization initialization in patient edit form (care_fe)

**Repository:** agentalec/care_fe

**Scope:** Single-line bug fix in patient registration component

**Changes Required:**
- Modify `src/components/Patient/PatientRegistration.tsx` line 235
- Change `_selected_levels: [data.geo_organization],` to `_selected_levels: data.geo_organization ? [data.geo_organization] : [],`

**What it touches:**
- Patient edit form initialization logic
- GovtOrganizationPicker component integration
- Form state management for geo_organization field

**Dependencies:**
- None. This is a standalone fix.

**Acceptance Criteria Coverage:**
- ✅ AC1: GovtOrganizationPicker visible and pre-populated with current organization when editing patient with existing geo_organization
- ✅ AC2: Organization changes save successfully via patient update API (fix enables proper form state)
- ✅ AC3: GovtOrganizationPicker visible when editing patient without geo_organization (empty array instead of [undefined])
- ✅ AC4: Validation error prevents submission when organization required but missing (picker properly initialized enables validation)
- ✅ AC5: geo_organization field visible in Additional Details accordion (already present, fix ensures it displays correctly)
- ✅ AC6: Navigation prompt warns about unsaved changes (form dirty tracking works with proper initialization)

**Size:** ~1 line changed

**Verification:**
1. Edit patient with existing organization → verify hierarchy pre-populated
2. Edit patient without organization → verify picker displays empty
3. Modify organization and save → verify update succeeds
4. Test required organization validation → verify error when missing
5. Modify organization and navigate away → verify unsaved changes warning

---

## Coverage Summary

All acceptance criteria from spec.md are covered by Task 1:
- ✅ AC1: Pre-populated organization picker for patients with geo_organization
- ✅ AC2: Organization updates save successfully
- ✅ AC3: Picker visible for patients without geo_organization
- ✅ AC4: Validation prevents submission when required
- ✅ AC5: Field visible in Additional Details section
- ✅ AC6: Unsaved changes warning on navigation

**Total Tasks:** 1  
**Total Repositories:** 1 (agentalec/care_fe)
