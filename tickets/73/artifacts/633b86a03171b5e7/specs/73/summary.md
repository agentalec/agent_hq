# Summary: Match user search on prefix, first name and last name

Extended user search to include `prefix` and `suffix` fields alongside the existing username, first name, and last name search. Staff can now find colleagues using professional titles like "Dr Meera Nair" or suffixes like "Jr".

## Changes Made

- Added `"prefix"` and `"suffix"` to `search_fields` in `UserViewSet` (`care/emr/api/viewsets/user.py`)
- Added 7 comprehensive test methods covering all acceptance criteria

## Acceptance Criteria

All 7 acceptance criteria are met:

1. ✅ Search by prefix alone (e.g., "Dr")
2. ✅ Search by prefix + first name (e.g., "Dr Meera")
3. ✅ Search by prefix + last name (e.g., "Dr Nair")
4. ✅ Search by prefix + first + last name (e.g., "Dr Meera Nair")
5. ✅ No false positives for users without prefixes
6. ✅ Existing search functionality unchanged (username, first name, last name)
7. ✅ Search by suffix (e.g., "Jr")

## Review Outcome

**Clean** — no findings. Code review passed with no issues.

## QA Status

All acceptance criteria verified via API-level tests. Frontend QA was not exercised (backend-only repository, no setup provided). Test coverage directly validates the API behavior that the frontend consumes.
