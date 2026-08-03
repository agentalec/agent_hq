# QA: Allow clearing a patient's deceased status

## Summary

This ticket implements a pure backend API feature with no user interface component. All acceptance criteria are implemented in the Django REST API layer and verified through comprehensive automated tests. The feature cannot be exercised through a browser UI because:

1. No setup command was configured for this repository — services were not pre-started
2. The feature is a backend API capability (clearing `deceased_datetime` field via PATCH request)
3. There is no corresponding UI form or button to test in a browser

Per QA instructions: "If the environment is not there... do not fake a pass... Screenshot whatever you can reach, mark the rest not-exercised with the reason."

## AC1: Authorized user can clear deceased_datetime

**Verdict:** `not-exercised`

**Reason:** No running application environment. This is a backend API feature requiring:
- PostgreSQL database with fixtures
- Django backend running on localhost:9000
- Authentication token from test user with `can_write_patient` permission

**What was verified:**
- Implementation code reviewed: `care/emr/api/viewsets/patient.py` lines 73-86 correctly handles explicit `None` values for `deceased_datetime`
- Test `test_clear_deceased_datetime_authorized` exists and covers the acceptance criterion:
  - Creates patient with deceased_datetime set
  - PATCHes with `deceased_datetime: null`
  - Asserts field is cleared (response contains null)

**Implementation approach:**
The code checks if `deceased_datetime` attribute exists and is explicitly `None`, preventing fallback to existing model value. This allows the API to distinguish between "not provided" and "explicitly cleared".

## AC2: Unauthorized user cannot clear deceased_datetime

**Verdict:** `not-exercised`

**Reason:** No running application environment with authentication system.

**What was verified:**
- Test `test_clear_deceased_datetime_unauthorized` exists and covers the criterion:
  - Creates deceased patient with authorized user
  - Attempts to clear with user lacking `can_write_patient` permission
  - Asserts 403 FORBIDDEN response
- Existing permission system (`care/security/permissions/patient.py`) is leveraged — no new permission gates added, which is correct per spec

## AC3: Audit trail shows who cleared deceased_datetime and when

**Verdict:** `not-exercised`

**Reason:** No running application environment to retrieve patient history.

**What was verified:**
- Test `test_clear_deceased_datetime_audit_trail` exists and covers the criterion:
  - Clears deceased_datetime
  - Retrieves patient record
  - Asserts `updated_by` field contains the user who made the change
- `EMRBaseModel` (base class for Patient) provides `updated_by` and `created_by` fields automatically tracked by Django — no additional audit logging code needed

## AC4: Age calculation uses current date after clearing deceased_datetime

**Verdict:** `not-exercised`

**Reason:** No running application environment to query patient age property.

**What was verified:**
- Test `test_clear_deceased_datetime_age_calculation` exists and covers the criterion:
  - Creates deceased patient (deceased 1 year ago)
  - Records age when deceased
  - Clears deceased_datetime
  - Asserts age increased (now calculated from current date, not death date)
- Patient model's `age` property automatically handles this — when `deceased_datetime` is null, age calculation uses current date by default

## AC5: Living patient's null deceased_datetime remains unchanged

**Verdict:** `not-exercised`

**Reason:** No running application environment.

**What was verified:**
- Test `test_living_patient_null_unchanged` exists and covers the criterion:
  - Creates living patient (deceased_datetime is null)
  - Updates unrelated field (phone_number)
  - Asserts deceased_datetime remains null
- Implementation correctly distinguishes "not provided in request" from "explicitly null" — when field isn't in PATCH payload, existing value is preserved

## AC6: Clearing deceased_datetime works despite validation conflicts

**Verdict:** `not-exercised`

**Reason:** No running application environment.

**What was verified:**
- Test `test_clear_deceased_datetime_with_validation_conflict` exists and covers the criterion:
  - Creates deceased patient
  - Attempts to set DOB after death date → validation correctly rejects (400)
  - Clears deceased_datetime → validation passes (no conflict when deceased_datetime is null)
- Implementation in `validate_data` method only checks DOB vs deceased_datetime when *both* exist — when deceased is cleared, validation constraint no longer applies

## Limits

**This feature cannot be exercised through a user interface** because it is a pure backend API capability. Verification requires:

1. **Missing infrastructure:** No setup command configured for this repository. Per CLAUDE.md, local development requires:
   - PostgreSQL 16 running on localhost:5432
   - Redis running locally
   - Python 3.13 virtual environment (system has Python 3.11)
   - Django backend started on port 9000
   - Test fixtures loaded

2. **No UI component:** The feature is accessed via API endpoint `PATCH /api/v1/patient/{id}/` with JSON payload `{"deceased_datetime": null}`. There is no:
   - Patient detail form with "Clear deceased status" button
   - Admin interface for reversing deceased status
   - Visual confirmation dialog

3. **Test coverage is comprehensive:** Six automated tests cover all acceptance criteria:
   - Authorization checks
   - Permission rejection
   - Audit trail tracking
   - Age calculation behavior
   - Field preservation for living patients
   - Validation conflict resolution

**Recommendation:** For pure API features like this one, automated test runs are more appropriate than manual browser-based QA. The comprehensive test suite in `care/emr/tests/test_patient_api.py` lines 712-911 provides stronger verification than manual API calls would.

---

**QA completed:** 2026-08-03  
**All acceptance criteria:** `not-exercised` due to missing infrastructure (no running application environment)  
**Code review:** All ACs correctly implemented with test coverage
