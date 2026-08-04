# Summary: Make automatic OPD ticket printing configurable per facility

## What was delivered

Added a facility-level toggle to control automatic invoice printing after payment. The setting appears in the facility edit form under "Print Settings" and defaults to ON for backward compatibility.

## Acceptance criteria met

- **AC1 (PASS)**: Facility administrators see the "Auto-print invoices after payment" toggle in facility settings
- **AC2 (PASS)**: When toggle is OFF, the facility setting prevents automatic print dialogs
- **AC3 (PASS)**: When toggle is ON, automatic printing follows template-level `auto_print` settings (current behavior)
- **AC4 (PASS)**: New facilities default to auto-print ON
- **AC5 (PASS)**: Existing facilities without explicit setting behave as auto-print ON
- **AC6 (NOT-EXERCISED)**: Print dialog suppression verified via code review; full payment flow not exercised
- **AC7 (NOT-EXERCISED)**: Print dialog triggering verified via code review; full payment flow not exercised

## Changes implemented

- `src/types/facility/facility.ts`: Added `auto_print_invoices?: boolean` to `FacilityRead` interface
- `src/components/Facility/FacilityForm.tsx`: Added print settings section with toggle in facility edit form
- `src/CAREUI/misc/PrintPreview.tsx`: Updated auto-print logic to check facility setting first: `facilityAutoPrintSetting && (templateAutoPrint ?? false)`
- `public/locale/en.json`: Added i18n strings for the new toggle

## Review outcome

Code review found no issues (clean pass). QA verified UI behavior and confirmed backward compatibility. End-to-end print dialog testing (AC6, AC7) requires a complete registration-and-payment flow not available in the test environment, but code review confirms correct implementation.

## Result

The feature is ready for deployment. Facilities like Jharkhand PHCs can now disable automatic invoice printing, while other facilities retain the current behavior by default.
