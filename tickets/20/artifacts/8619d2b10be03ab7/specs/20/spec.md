# Specification: Add search for Healthcare Service index page

## Problem Statement

Government healthcare setups configure departments as healthcare services, often resulting in long lists that require manual scrolling to locate specific departments. Users need a quick way to filter and find the relevant healthcare service from potentially hundreds of entries. This specification addresses adding search functionality that already exists in the UI but needs to be verified and potentially enhanced for optimal usability.

## Acceptance Criteria

### AC1: Search input is visible and functional

**Given** a user navigates to the Healthcare Services index page at `/facility/{facilityId}/settings/healthcare_services`  
**When** the page loads  
**Then** a search input field with placeholder "Search healthcare services..." is visible above the list of healthcare services  
**And** the search input has a search icon on the left side

### AC2: Search filters by service name

**Given** the Healthcare Services index page displays 5+ healthcare services  
**When** the user types "Cardio" into the search input  
**Then** only healthcare services with names containing "Cardio" (case-insensitive) are displayed in the list  
**And** the search query is debounced to avoid excessive API calls  
**And** pagination updates to reflect the filtered result count

### AC3: Search updates URL query parameters

**Given** a user is on the Healthcare Services index page  
**When** the user types a search term into the search input  
**Then** the URL updates to include `?search={searchTerm}` as a query parameter  
**And** when the page is refreshed or the URL is shared, the search term persists and the filtered results are displayed

### AC4: Clearing search shows all services

**Given** a user has entered a search term that filters the list  
**When** the user clears the search input (backspace or clear button)  
**Then** all healthcare services are displayed again  
**And** the `search` query parameter is removed from the URL

### AC5: Empty state shows when no results match

**Given** a user has entered a search term  
**When** no healthcare services match the search criteria  
**Then** an empty state is displayed with an appropriate message  
**And** no service cards are visible

## Capability Notes

### Already Implemented

The search functionality is **already fully implemented** in the codebase:

1. **Search UI Component** (`src/pages/Facility/settings/healthcareService/HealthcareServiceList.tsx`):
   - Lines 74-82: Search input with icon, connected to `qParams.search`
   - Uses `useFilters` hook for URL query parameter management
   - Debounced search via `query.debounced()` wrapper

2. **API Integration** (`src/types/healthcareService/healthcareServiceApi.ts`):
   - Line 11: `listHealthcareService` endpoint supports `name` query parameter for filtering
   - Returns paginated results via standard `PaginatedResponse` type

3. **Translation Key** (`public/locale/en.json`):
   - Line 5261: `"search_healthcare_services": "Search healthcare services..."`

4. **Test Coverage** (`tests/facility/settings/services/healthcareServiceDelete.spec.ts`):
   - Lines 30-33: Test verifies search input is accessible via `getByRole("textbox", { name: "Search healthcare services..." })`
   - Lines 49-55: Test verifies search filters results correctly

### Implementation Details

- **Filter Hook**: `useFilters` from `src/hooks/useFilters` manages pagination and query params
- **Debouncing**: `query.debounced()` from `src/Utils/request/query.ts` handles API call debouncing
- **API Query**: Passes `name: qParams.search` to backend endpoint (line 39)
- **Empty State**: Uses `<EmptyState>` component when `healthcareServices.length === 0` (lines 89-94)

## Open Questions

None. The feature is already fully implemented and tested. No additional work is required.

## Recommendation

**Outcome**: `complete`

The search functionality described in the ticket is already implemented in `src/pages/Facility/settings/healthcareService/HealthcareServiceList.tsx`. The implementation includes:
- A visible search input with debounced filtering
- URL query parameter integration (`?search=...`)
- Proper empty state handling
- Existing Playwright test coverage

No code changes are necessary. The ticket can be closed as already implemented.
