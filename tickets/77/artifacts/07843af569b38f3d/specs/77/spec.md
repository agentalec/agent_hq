# Spec: Organization missing in Edit Patient State

## Problem

The patient edit flow (`/patient/{id}/update` or `/facility/{id}/patient/{id}/update`) does not display the organization (geo_organization) field when editing from the Demographics tab. The field is present during patient registration and stored in the patient model, but users cannot modify it during edit. This prevents updating a patient's geographical organization after initial registration, which may be required when a patient relocates or was initially registered with incorrect organization data.

## Acceptance Criteria

1. Given a patient with an existing geo_organization, when navigating to edit patient from Demographics tab (section=general-info), then the GovtOrganizationPicker should be visible and pre-populated with the current organization hierarchy.
2. Given a patient with geo_organization, when editing patient details and changing the organization selection, then the updated organization should be saved successfully via the patient update API.
3. Given a patient without geo_organization, when editing patient details, then the GovtOrganizationPicker should be visible and allow setting an organization.
4. Given organization is required by configuration (minGeoOrganizationLevelsRequired), when attempting to save patient edit without valid organization, then validation error should prevent submission.
5. Given the patient edit form, when the Additional Details accordion section is expanded, then the geo_organization field should be visible alongside address and pincode fields.
6. Given changes to geo_organization in edit mode, when clicking back without saving, then navigation prompt should warn about unsaved changes.

## Capability Notes

- `src/components/Patient/PatientRegistration.tsx:880-912` -- GovtOrganizationPicker exists in AdditionalDetailsContent section, rendering for both create and edit modes
- `src/components/Patient/PatientDetailsTab/Demography.tsx:238-240` -- Displays geo_organization when viewing patient, with edit navigation to `/patient/{id}/update?section=general-info`
- `src/types/emr/patient/patient.ts:48-49` -- PatientRead interface includes `geo_organization?: Organization`
- `src/types/emr/patient/patient.ts:57-60` -- PatientUpdate interface includes `geo_organization?: string` (UUID)
- `src/components/Organization/GovtOrganizationPicker.tsx` -- Cascading organization picker supporting multi-level government organization hierarchies

## Open Questions

None.
