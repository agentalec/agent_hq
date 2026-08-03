# Review: Ticket 70

## Round 1

- **blocker** `src/pages/Facility/services/inventory/externalSupply/deliveryOrder/SmartExternalDeliveryRow.tsx:56` — Plain Enter calls `e.preventDefault()` but doesn't ensure focus moves to next field. AC1 and AC2 require "focus moves to the next focusable field" but the implementation only prevents submission. Either remove `e.preventDefault()` to allow browser's default focus behavior, or explicitly call `focus()` on the next focusable element after preventing default.
- **should-fix** `tests/PLAYWRIGHT_GUIDE.md:96-97,102,106` and `tests/README.md:120` — Unrelated formatting changes (removed newlines, malformed template literals). Revert these files to their original state as they're unrelated to the ticket.

## Round 2

- **should-fix** `tests/PLAYWRIGHT_GUIDE.md` and `tests/README.md` — Unrelated formatting changes remain; revert these test documentation files to their original state as they're not part of the ticket scope.
