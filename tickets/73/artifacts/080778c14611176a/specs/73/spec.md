# Ticket 73: Match user search on prefix, first name and last name

## Problem

User search currently only matches on username, first name, and last name individually. Staff who know colleagues by their professional titles (e.g., "Dr Meera Nair") cannot find users when searching with the prefix included. The prefix field exists in the User model but is not included in the search, limiting discoverability of colleagues by their commonly-used names.

## Acceptance Criteria

1. Given a user with prefix "Dr", when searching by "Dr" alone, then that user appears in results.
2. Given a user with first name "Meera" and prefix "Dr", when searching by "Dr Meera", then that user appears in results.
3. Given a user with last name "Nair" and prefix "Dr", when searching by "Dr Nair", then that user appears in results.
4. Given a user with first name "Meera", last name "Nair", and prefix "Dr", when searching by "Dr Meera Nair", then that user appears in results.
5. Given users without prefixes, when searching by common honorifics, then no false positives are returned.
6. Given existing user search by username, first name, or last name alone, when searching without prefix, then results remain unchanged.
7. Given a user with suffix, when searching by the suffix, then that user appears in results.

## Capability Notes

- `care/emr/api/viewsets/user.py:103` — `UserViewSet.search_fields = ["first_name", "last_name", "username"]` — existing search field configuration, needs `prefix` and `suffix` added.
- `care/users/models.py:165-166` — `User.prefix` and `User.suffix` fields — exist and are stored as char fields, ready for search inclusion.
- `care/emr/tests/test_user_api.py:381-397` — existing search test cases — cover username, first_name, and last_name; need expansion for prefix/suffix and multi-field queries.
- `care/emr/api/viewsets/user.py:102` — `filter_backends = [filters.DjangoFilterBackend, drf_filters.SearchFilter]` — DRF SearchFilter supports multi-field queries via space separation.

## Open Questions

None.
