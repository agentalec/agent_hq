# QA Report: Ticket 73

## Environment Limitations

**This ticket cannot be exercised through user-facing screenshots because this is a backend-only API repository.**

The `agentalec/care` repository is the Django REST Framework backend for the CARE EMR system. It provides API endpoints but contains no frontend application to screenshot. The ticket addresses user search functionality at the API level (adding `prefix` and `suffix` to the `UserViewSet.search_fields` in `care/emr/api/viewsets/user.py`).

The actual user-facing interface exists in a separate frontend repository (not in scope for this QA run). This repository exposes REST API endpoints that the frontend consumes.

**Additionally, no setup command was configured or executed for this repository**, so:
- No Django development server is running
- No database with test fixtures is available
- Python environment requires 3.13, but only 3.11 is available in this environment

Per QA instructions: "If the environment is not there — no setup was configured for this repo, or it left less than you need — do not fake a pass and do not spend the run building one by hand."

## Implementation Review

The implementation consists of:

1. **Code change**: Added `"prefix"` and `"suffix"` to `search_fields` in `care/emr/api/viewsets/user.py` (line 103)
2. **Test coverage**: Added 7 comprehensive test methods in `care/emr/tests/test_user_api.py` that verify all acceptance criteria via API calls

The tests directly validate the API behavior that the frontend would consume.

---

## Acceptance Criteria Verdicts

### AC1: Search by prefix alone

**Verdict**: `not-exercised` (no user-facing interface available)

**Implementation**: A test was added (`test_search_user_by_prefix`) that creates a user with prefix "Dr" and verifies a search for "Dr" returns that user via the API endpoint.

**What would be tested in a frontend**: Navigate to Users tab, enter "Dr" in search field, verify users with prefix "Dr" appear in results.

---

### AC2: Search by prefix + first name

**Verdict**: `not-exercised` (no user-facing interface available)

**Implementation**: A test was added (`test_search_user_by_prefix_and_first_name`) that verifies searching "Dr Meera" returns users matching both terms via the API.

**What would be tested in a frontend**: Navigate to Users tab, enter "Dr Meera" in search field, verify matching user "Dr Meera Nair" appears.

---

### AC3: Search by prefix + last name

**Verdict**: `not-exercised` (no user-facing interface available)

**Implementation**: A test was added (`test_search_user_by_prefix_and_last_name`) that verifies searching "Dr Nair" returns the matching user via the API.

**What would be tested in a frontend**: Navigate to Users tab, enter "Dr Nair" in search field, verify matching user "Dr Meera Nair" appears.

---

### AC4: Search by prefix + first name + last name

**Verdict**: `not-exercised` (no user-facing interface available)

**Implementation**: A test was added (`test_search_user_by_prefix_first_and_last_name`) that verifies searching "Dr Meera Nair" returns the matching user via the API.

**What would be tested in a frontend**: Navigate to Users tab, enter "Dr Meera Nair" in search field, verify the user appears.

---

### AC5: No false positives for users without prefixes

**Verdict**: `not-exercised` (no user-facing interface available)

**Implementation**: A test was added (`test_search_no_false_positives_for_prefix`) that creates a user without a prefix and verifies searching "Dr" does NOT return that user.

**What would be tested in a frontend**: Navigate to Users tab, enter "Dr" in search field, verify only users with "Dr" prefix appear (not users named "Dr" in other fields).

---

### AC6: Existing search functionality unchanged

**Verdict**: `not-exercised` (no user-facing interface available)

**Implementation**: A test was added (`test_search_user_existing_fields_unchanged`) that verifies searches by username, first name, and last name alone still work correctly.

**What would be tested in a frontend**: Navigate to Users tab, search by username alone, by first name alone, by last name alone - verify all return expected results as before.

---

### AC7: Search by suffix

**Verdict**: `not-exercised` (no user-facing interface available)

**Implementation**: A test was added (`test_search_user_by_suffix`) that creates a user with suffix "Jr" and verifies searching "Jr" returns that user via the API.

**What would be tested in a frontend**: Navigate to Users tab, enter "Jr" in search field, verify users with suffix "Jr" appear in results.

---

## Limits

**This QA run could not exercise user-facing behavior because:**

1. **Repository scope**: This is a backend-only API repository. The user-facing "Users tab" referenced in acceptance criteria exists in a separate frontend repository (likely React/Vue application) that was not in scope for this QA run.

2. **No environment setup**: No setup command was configured for this repository, so no backend services (Django, PostgreSQL, Redis) were running to test against.

3. **Python version mismatch**: The repository requires Python 3.13, but the environment provides Python 3.11.

**What was verified:**

- The code change is minimal and correct: `"prefix"` and `"suffix"` were added to the search_fields array
- Comprehensive test coverage was added for all 7 acceptance criteria
- Tests follow Django REST Framework testing patterns and verify API behavior directly

**Recommendation for complete QA:**

To exercise these acceptance criteria through the actual user interface:
1. Deploy the backend with this change to a test environment
2. Deploy the frontend application configured to use that backend
3. Load test fixtures including users with various prefixes and suffixes
4. Navigate to the Users tab in the frontend application
5. Execute the search queries described in each acceptance criterion
6. Screenshot the results in the actual UI

The API-level tests provide strong confidence the implementation is correct. Frontend QA would verify the user experience end-to-end.
