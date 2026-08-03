# Specification: Patient Profile Update Rejects Unmodified Organisation Selector

## Problem Statement

When updating an existing patient profile, saving the form without modifying the government organisation selector fails with validation error "Min 2 levels needs to be selected", even though the selector visually displays the required two levels (e.g., state and district). The instance has minimum organisation level requirement configured as two, creating a mismatch where the rendered selection appears valid but the submitted value fails validation on untouched selectors.

## Acceptance Criteria

1. Given a patient with a valid 2-level government organisation (e.g., state + district), when the profile update form loads, then the `geo_organization` form field is initialized with a value that satisfies depth validation.

2. Given a patient profile update form with the government organisation selector untouched, when the form is submitted, then the organisation validation succeeds if the existing selection meets the configured minimum depth requirement.

3. Given a patient with an organisation at level 1 (level_cache: 1) and minGeoOrganizationLevelsRequired configured as 2, when the form loads, then `isGeoOrganizationValid` returns true for the loaded organisation.

4. Given the form field's `onChange` handler validates organisation depth before setting the field value, when the form initializes with an existing patient, then the field value is set through the same validation logic used during user interaction.

5. Given the organisation selector displays the full cascade from state to district, when the user saves without touching it, then the form submits the deepest level organisation ID that was originally loaded.

6. Given a newly created patient with valid 2-level organisation, when immediately editing that patient's profile without changing the organisation, then the save succeeds without validation errors.

## Capability Notes

- `src/components/Patient/PatientRegistration.tsx:222` -- initializes `geo_organization` field with `data.geo_organization?.id` directly during form reset
- `src/components/Patient/PatientRegistration.tsx:235` -- initializes `_selected_levels` with `[data.geo_organization]` 
- `src/components/Patient/PatientRegistration.tsx:893-906` -- `onChange` handler validates organisation depth via `isGeoOrganizationValid` before setting field value
- `src/components/Patient/PatientRegistration.tsx:1049-1060` -- `isGeoOrganizationValid` function checks if organisation meets depth requirement
- `src/components/Organization/GovtOrganizationPicker.tsx:129-142` -- rebuilds full cascade from organisation's ancestor chain on value change

## Open Questions

None.
