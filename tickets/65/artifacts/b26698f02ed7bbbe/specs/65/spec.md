# Spec: Add search for the Healthcare Service index page

## Problem Statement

The ticket requests adding search functionality to the Healthcare Services index page to help users quickly locate departments in long lists. However, search functionality is already implemented in the healthcare services list page at `/facility/{facilityId}/settings/healthcare_services`.

## Investigation Findings

The healthcare services index page (`src/pages/Facility/settings/healthcareService/HealthcareServiceList.tsx`) already implements a fully functional search feature with:
- Search input field with icon (lines 70-82)
- Debounced API query to reduce server load (line 34)
- Real-time filtering by service name via `name` query parameter (line 39)
- Query parameter persistence via `useFilters` hook (lines 27-30)
- Pagination support for search results (lines 107-111)

Additionally, search is implemented in two other healthcare service contexts:
- `src/pages/Facility/services/HealthcareServiceSelector.tsx` (combobox selector, lines 116-122)
- `src/components/ui/sidebar/facility/service/service-switcher.tsx` (service switcher dialog, lines 192-200)

## Acceptance Criteria

None. The requested functionality already exists.

## Capability Notes

- `src/pages/Facility/settings/healthcareService/HealthcareServiceList.tsx` -- existing search implementation
- `src/types/healthcareService/healthcareServiceApi.ts:listHealthcareService` -- API endpoint supports `name` query param for filtering
- `src/hooks/useFilters.ts` -- provides query parameter management with debouncing
- `public/locale/en.json` -- contains `search_healthcare_services` translation key

## Open Questions

None.

## Recommendation

No implementation work is required. The healthcare services index page at `/facility/{facilityId}/settings/healthcare_services` has a visible search input field that filters services by name with debounced API queries. Users can type in the search box to quickly locate departments without manual scrolling.

If the reporter is experiencing different behavior, this may be a deployment issue or they may be looking at a different page. Consider closing this ticket or requesting clarification about which specific page lacks search functionality.
