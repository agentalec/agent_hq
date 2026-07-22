# Spec: Display patient age on encounter page using clinical age-format rules

## Problem Statement

The patient age display on the encounter page patient card currently uses a simplified format (years only for 1+ years, months+days for <1 year) that does not meet clinical requirements. Healthcare providers need age displayed with appropriate granularity based on clinical age ranges to support accurate pediatric and geriatric assessment. The new format must follow established clinical age-format conventions with different representations for neonates, infants, toddlers, children, and adults.

## Acceptance Criteria

### AC1: Display age using clinical age-format rules
**Given** a patient with a date of birth  
**When** their age is displayed on the encounter page patient card  
**Then** the age format should follow these rules:
- 0–28 days old: display "X days" (e.g., "15 days")
- 29 days to 1 year old: display "X weeks Y days" (e.g., "8 weeks 3 days")
- 1 year to 2 years old: display "X months Y days" (e.g., "18 months 15 days")
- 2 years to 18 years old: display "X years Y months" (e.g., "5 years 3 months")
- Above 18 years old: display "X years" only (e.g., "42 years")

### AC2: Handle abbreviated format
**Given** the age formatter is called with abbreviated mode enabled  
**When** rendering the age text  
**Then** use abbreviated suffixes (e.g., "y" for years, "m" for months, "w" for weeks, "d" for days) instead of full words

### AC3: Show full age breakdown on hover
**Given** a patient age is displayed on the encounter page patient card  
**When** the user hovers over the age text  
**Then** display a tooltip showing the complete age breakdown in format "X years, Y months, Z days" regardless of the primary display format

### AC4: Calculate age relative to death date for deceased patients
**Given** a deceased patient with a recorded deceased_datetime  
**When** displaying their age  
**Then** calculate the age from date_of_birth to deceased_datetime instead of the current date

### AC5: Handle year-of-birth-only patients
**Given** a patient with only year_of_birth and no date_of_birth  
**When** displaying their age  
**Then** display "Born YYYY" or "Born on YYYY" (depending on abbreviated mode) as the current implementation does

### AC6: Maintain consistency across all age displays
**Given** the `formatPatientAge()` function is used in multiple locations (appointments, billing, prescriptions, service requests)  
**When** the age format changes  
**Then** all instances throughout the application should use the new clinical age format

## Capability Notes

### Existing Implementation
- **Age formatting function**: `formatPatientAge()` in `src/Utils/utils.ts` (lines 148-183) implements the current logic
- **Current age calculation**: Uses dayjs to calculate years, months, and days from date_of_birth or year_of_birth
- **Deceased patient handling**: Already calculates age relative to deceased_datetime when present
- **Abbreviated mode**: Already supports abbreviated vs full suffixes via `getRelativeDateSuffix()` function
- **Patient card location**: `PatientHoverCard` component in `src/pages/Facility/services/serviceRequests/PatientHoverCard.tsx` (line 107) displays age
- **Hover card**: `PatientInfoHoverCard` component in `src/components/Patient/PatientInfoHoverCard.tsx` (line 48) displays age in the popover
- **Encounter page integration**: `EncounterShow.tsx` uses `PatientHeader` which includes `PatientHoverCard`

### Needs Building
- **New age range logic**: Implement conditional formatting based on clinical age ranges (0-28 days, 29 days-1 year, 1-2 years, 2-18 years, 18+ years)
- **Week calculation**: Add logic to calculate weeks from days for the 29 days to 1 year range
- **Tooltip component**: Add hover tooltip to display full "X years, Y months, Z days" breakdown for all ages
- **Tooltip integration**: Wrap age display text with tooltip in `PatientInfoHoverCard.tsx` and `PatientHoverCard.tsx` trigger components
- **Tests**: Add unit tests for `formatPatientAge()` covering all age ranges and edge cases
- **E2E tests**: Update Playwright tests in `tests/facility/patient/encounter/` and `tests/organization/patient/encounter/patientInfoHoverCard.spec.ts` to verify new age formats

## Open Questions

[open] **Q1: Should the tooltip always show the full breakdown, or should it adapt based on the primary format?**  
**Resolution**: Product owners should confirm if tooltip should always show "X years, Y months, Z days" format or follow the same age-range rules as the primary display.

[open] **Q2: How should weeks be rounded when calculating "X weeks Y days"?**  
**Resolution**: Clinical team should clarify if we use 7-day weeks (standard) or any special rounding rules for partial weeks.

[open] **Q3: Should the 18-year threshold use >= or > for the "years only" display?**  
**Resolution**: Product owners should confirm if exactly 18 years old should show "18 years" or "18 years 0 months".

[open] **Q4: What should be the behavior for edge cases like "0 days" old (born today)?**  
**Resolution**: Clinical team should specify if newborns born today should show "0 days" or "< 1 day" or similar.

[open] **Q5: Should the abbreviated format be different for the new age ranges?**  
**Resolution**: Product owners should confirm abbreviated suffixes for weeks (e.g., "w" vs "wks" vs "weeks").
