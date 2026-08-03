# Spec: Allow clearing a patient's deceased status

## Problem Statement

Once a patient's `deceased_datetime` is set, the system provides no supported way to clear it, forcing administrators to manually edit the database when staff mistakenly mark a living person as deceased. This ticket adds a supported mechanism to clear the deceased status, with appropriate permission controls and audit logging to track who reversed it and when.

## Acceptance Criteria

1. Given a patient with `deceased_datetime` set, when an authorized user updates the patient with `deceased_datetime: null`, then the field is cleared and the patient's status is restored to living.
2. Given an unauthorized user attempts to clear `deceased_datetime` on a deceased patient, when they submit the update, then the request is rejected with a permission error.
3. Given a patient whose `deceased_datetime` is cleared, when retrieving the patient's history, then the audit trail shows who cleared it and when.
4. Given a patient's `deceased_datetime` is cleared, when calculating the patient's age, then the calculation uses the current date instead of the deceased datetime.
5. Given a patient with `deceased_datetime: null` (living), when updating other patient fields, then the existing null value remains unchanged.
6. Given a patient with validation errors (e.g., date_of_birth after deceased_datetime), when clearing `deceased_datetime`, then the validation no longer blocks the update.

## Capability Notes

- `care/emr/models/patient.py:34` — `deceased_datetime` field exists as nullable DateTimeField
- `care/emr/resources/patient/spec.py:69` — PatientBaseSpec includes `deceased_datetime` as optional field
- `care/emr/api/viewsets/patient.py:73-92` — `validate_data` method checks deceased_datetime constraints
- `care/emr/models/base.py:8-26` — EMRBaseModel provides `history`, `created_by`, `updated_by` for audit trail
- `care/security/permissions/patient.py:30-42` — `can_write_patient` permission exists for patient updates

## Open Questions

None.
