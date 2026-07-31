# Spec: Add search for the Healthcare Service index page

## Problem Statement

The FacilityServices page (`/facility/:facilityId/services`) displays a list of healthcare services but lacks search functionality. In government setups with many departments configured as services, users must scroll through the entire list. Adding a search field would enable quick filtering.

## Acceptance Criteria

Given the FacilityServices page is loaded, when a user types text into a new search field, then the service list filters to show only services whose names contain the search text.

Given a user has filtered services with a search query, when they clear the search field, then all services are displayed again.

Given the API returns an empty result set, when the user performs a search, then the existing empty state is shown with the "No services found" message.

Given multiple healthcare services exist, when the user types a partial service name, then debounced search queries are sent to the backend to avoid excessive API calls.

Given pagination exists, when a user performs a search, then pagination is maintained and the page resets to 1.

## Capability Notes

- `src/pages/Facility/services/FacilityServices.tsx` — Facility services index page exists without search; uses `useFilters` hook.
- `src/pages/Facility/settings/healthcareService/HealthcareServiceList.tsx:74-82` — Reference implementation of search input with icon exists in settings page.
- `src/types/healthcareService/healthcareServiceApi.ts:11` — API endpoint `listHealthcareService` accepts `name` query parameter for filtering.
- `src/Utils/request/query.ts` — `query.debounced()` wrapper exists for debounced API queries.
- `public/locale/en.json:3882` — i18n key `no_services_found` exists for empty state.

## Open Questions

None.
