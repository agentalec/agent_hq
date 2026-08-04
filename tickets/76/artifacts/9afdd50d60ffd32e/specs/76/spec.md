# Spec: Make automatic OPD ticket printing configurable per facility

## Problem

When payment is recorded in the new registration flow, the invoice print page automatically triggers `window.print()` via the `auto_print` setting in print templates. Facilities like Jharkhand PHCs don't print OPD tickets at all, so staff dismiss an unwanted print dialog on every registration. The `auto_print` flag exists per print template but cannot be globally disabled for a facility.

## Acceptance Criteria

1. Given a facility administrator is editing facility settings, when they view the print configuration section, then they see a global "Auto-print invoices after payment" toggle.
2. Given the global toggle is OFF, when any invoice print page loads for that facility, then the print dialog does not open automatically regardless of template-level `auto_print` settings.
3. Given the global toggle is ON, when an invoice print page loads, then the print dialog opens automatically only if the template's `auto_print` is true (current behavior).
4. Given a new facility is created, when the facility record is saved, then the global auto-print setting defaults to ON (preserves current behavior).
5. Given an existing facility has no explicit auto-print setting, when the facility is loaded, then auto-print behaves as ON (preserves current behavior).
6. Given a facility has the global toggle set to OFF, when staff record payment for a registration, then the invoice page renders without triggering `window.print()`.
7. Given a facility has the global toggle set to ON, when staff record payment for a registration, then the invoice page triggers `window.print()` if the invoice template has `auto_print: true`.

## Capability Notes

- `src/types/facility/facility.ts:FacilityRead` -- exists, stores facility metadata; add global `auto_print_invoices` boolean here.
- `src/types/facility/printTemplate.ts:PrintSetupConfig` -- exists, has per-template `auto_print` flag.
- `src/CAREUI/misc/PrintPreview.tsx:PrintPreview` -- exists, reads `auto_print` from template and calls `useAutoPrint`; update to check facility-level setting first.
- `src/components/Facility/PrintTemplateSheet.tsx` -- exists, shows per-template auto-print UI; no changes needed, it configures templates.
- `src/pages/Facility/settings/general/general.tsx` -- likely place for facility-level auto-print toggle (needs verification).

## Open Questions

None.
