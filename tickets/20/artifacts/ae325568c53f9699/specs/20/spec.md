# Spec: Add search for the Healthcare Service index page

## Problem Statement

The healthcare services index page already includes search functionality that filters services by name. The feature request describes a need for search/filter capability, but examination of the codebase reveals this capability is fully implemented and tested.

## Acceptance Criteria

Given the healthcare services index page is loaded, when the user types text into the search field, then the service list filters to show only services whose names contain the search text.

Given a user has filtered services with a search query, when they clear the search field, then all services are displayed again.

Given the API returns an empty result set, when the user performs a search, then an appropriate empty state message is displayed.

Given multiple healthcare services exist, when the user types a partial service name, then debounced search queries are sent to the backend without overwhelming the API.

## Capability Notes

- `src/pages/Facility/settings/healthcareService/HealthcareServiceList.tsx:74-82` — Search input field exists with icon, connected to `qParams.search` state.
- `src/pages/Facility/settings/healthcareService/HealthcareServiceList.tsx:34` — Search query uses `query.debounced()` wrapper to avoid excessive API calls.
- `src/types/healthcareService/healthcareServiceApi.ts:11` — API endpoint `listHealthcareService` accepts search parameters via query string.
- `tests/facility/settings/services/healthcareServiceDelete.spec.ts:31-33` — Playwright test verifies search functionality works end-to-end.
- `public/locale/en.json:search_healthcare_services` — i18n key exists for the search placeholder text.

## Open Questions

None.

---

**Outcome:** The requested functionality is already implemented. The healthcare services index page includes a working search field with debounced queries, empty state handling, and E2E test coverage. No code changes are required.
