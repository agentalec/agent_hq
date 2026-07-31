# Summary: Add search for the Healthcare Service index page

## What was done

Added a search field to the FacilityServices index page (`/facility/:facilityId/services`) to enable quick filtering of healthcare services by name. This addresses the need for government setups with many departments configured as services where users previously had to scroll through the entire list.

## Implementation

- Added search input component with icon to `src/pages/Facility/services/FacilityServices.tsx`
- Integrated debounced API queries using `query.debounced()` wrapper to reduce server load
- Connected search state to existing `useFilters` hook for automatic pagination handling
- Added i18n key `search_healthcare_services` to English locale file

## Acceptance criteria

✅ **All acceptance criteria met:**
- Service list filters based on search input text
- Clearing search field restores full service list
- Empty state displays when no results match search query
- Debounced search queries prevent excessive API calls
- Pagination resets to page 1 on search (verified via code review; `useFilters` handles automatically)

## Review outcome

**Clean after 2 rounds.** Initial issues with unrelated test documentation formatting were resolved. Core implementation was correct from the start.

## QA verification

All exercisable criteria passed with visual confirmation via screenshots:
- Search filtering works correctly with debounced queries
- Empty state displays appropriately for no results
- Mobile responsiveness verified
- Network monitoring confirmed single API request per search input

Note: Pagination reset could not be visually verified due to test data containing fewer than 12 services, but the implementation is architecturally sound.
