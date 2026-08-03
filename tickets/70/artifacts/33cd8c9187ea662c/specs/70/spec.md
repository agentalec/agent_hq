# Ticket 70: Save a Purchase Delivery item with Shift + Enter, not Enter

## Problem Statement

When adding items in Purchase Delivery, pressing Enter while focused in the Quantity or Price field immediately submits the entire form. Users expect Enter to move focus to the next field, but instead it triggers form submission prematurely, creating incomplete rows that must be located and corrected. This is a significant usability issue reported from the Pallium deployment.

## Acceptance Criteria

1. Given the user is entering data in the Quantity field of a Purchase Delivery item row, when they press Enter (without Shift), then focus moves to the next focusable field and the form does not submit.
2. Given the user is entering data in the Price field of a Purchase Delivery item row, when they press Enter (without Shift), then focus moves to the next focusable field and the form does not submit.
3. Given the user has filled in item fields in a Purchase Delivery row, when they press Shift + Enter in any input field, then the form submits and saves the delivery item.
4. Given the user presses Shift + Enter in the Quantity or Price field, when the form has validation errors, then standard validation error handling occurs (errors displayed, no submission).
5. Given the user completes filling a Purchase Delivery item row, when they click the Save/Submit button, then the form submits as it does today (button behavior unchanged).

## Capability Notes

- `src/pages/Facility/services/inventory/externalSupply/deliveryOrder/SmartExternalDeliveryRow.tsx` -- row component rendering Price (line 455-470) and Quantity (line 433-440) input fields; needs keyboard event handlers
- `src/pages/Facility/services/inventory/externalSupply/deliveryOrder/AddSupplyDeliveryForm.tsx` -- parent form with `onSubmit` handler (line 538-590) and `form.handleSubmit` hook (line 600); keyboard events must integrate with existing submission logic
- `src/components/ui/input.tsx` -- base Input component used for Quantity and Price fields; may need extension for keyboard shortcut handling
- `src/Utils/keyboardShortcutComponents.tsx` -- existing keyboard shortcut utilities; provides `ShortcutBadge` component for displaying shortcuts like Shift+Enter

## Open Questions

None.
