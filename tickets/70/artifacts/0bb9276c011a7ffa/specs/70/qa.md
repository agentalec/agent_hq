# QA Report: Ticket 70

## Status Summary

**All acceptance criteria: `not-exercised`**

The implementation code changes are present and correctly implemented in `SmartExternalDeliveryRow.tsx`. However, the Purchase Delivery item entry form could not be accessed through the running application's UI to verify the keyboard behavior changes.

---

## Acceptance Criterion 1

**Given the user is entering data in the Quantity field of a Purchase Delivery item row, when they press Enter (without Shift), then focus moves to the next focusable field and the form does not submit.**

**Verdict:** `not-exercised`

**Reason:** Could not access the Purchase Delivery item entry form through the application UI. Navigated through the facility services → locations → external deliveries path, but the delivery list page (`/facility/{facilityId}/location/{locationId}/inventory/external/deliveries/outgoing`) did not provide a "New" or "Create" button to open the item entry form.

**Code verification:** The implementation in `SmartExternalDeliveryRow.tsx` (lines 130-156) correctly handles plain Enter by preventing default submission and explicitly moving focus to the next focusable form element using `form.elements` iteration.

---

## Acceptance Criterion 2

**Given the user is entering data in the Price field of a Purchase Delivery item row, when they press Enter (without Shift), then focus moves to the next focusable field and the form does not submit.**

**Verdict:** `not-exercised`

**Reason:** Same as AC1 - could not access the Purchase Delivery item entry form.

**Code verification:** The keyboard handler applies to all inputs in the row, including the Price field, using the `handleKeyDown` function attached via `onKeyDown` prop (lines 433-440 for Quantity, 455-470 for Price fields).

---

## Acceptance Criterion 3

**Given the user has filled in item fields in a Purchase Delivery row, when they press Shift + Enter in any input field, then the form submits and saves the delivery item.**

**Verdict:** `not-exercised`

**Reason:** Same as AC1/AC2 - could not access the form.

**Code verification:** The implementation correctly detects `e.shiftKey && e.key === "Enter"` (line 128) and calls `onSubmit?.()` to trigger form submission, which was passed from the parent form component.

---

## Acceptance Criterion 4

**Given the user presses Shift + Enter in the Quantity or Price field, when the form has validation errors, then standard validation error handling occurs (errors displayed, no submission).**

**Verdict:** `not-exercised`

**Reason:** Could not access the form to test validation behavior.

**Code verification:** The keyboard handler calls `onSubmit` which is wired to `form.handleSubmit` in the parent `AddSupplyDeliveryForm` component. React Hook Form's standard validation would prevent submission if errors exist, as the handler doesn't bypass validation.

---

## Acceptance Criterion 5

**Given the user completes filling a Purchase Delivery item row, when they click the Save/Submit button, then the form submits as it does today (button behavior unchanged).**

**Verdict:** `not-exercised`

**Reason:** Could not access the form to verify button behavior.

**Code verification:** The implementation adds keyboard shortcuts without modifying button click behavior. The existing submit button in `AddSupplyDeliveryForm` continues to use the same `form.handleSubmit` mechanism.

---

## Navigation Path Attempted

1. Started at application homepage (authenticated with `tests/.auth/user.json`)
2. Navigated to **Facility Services** page (`/facility/{facilityId}/services`)
3. Clicked on **Main Pharmacy → View Details** link
4. Reached **Service Locations** page showing pharmacy locations
5. Extracted location ID from pharmacy link: `64586697-d2bc-4312-af37-5a0aa72afc6d`
6. Navigated directly to **External Deliveries** list: `/facility/{facilityId}/location/{locationId}/inventory/external/deliveries/outgoing`
7. **Stopped:** No "New", "Add", or "Create" button present to open delivery form

![Services page](specs/70/screenshots/01-services-page.png)
![Service locations](specs/70/screenshots/02-service-locations.png)
![Deliveries list with no action button](specs/70/screenshots/03-deliveries-list.png)

---

## Limits

**What prevented full QA:**

1. **No access to delivery entry form:** The external deliveries list page did not provide UI controls to create a new delivery or add items to an existing delivery. The `SmartExternalDeliveryRow` component that contains the changed keyboard behavior appears to be rendered within a parent form (DeliveryOrderForm or AddSupplyDeliveryForm), but this form was not accessible through the navigation path available in the seeded test environment.

2. **Possible reasons:**
   - The form may require specific permissions or roles not present in the `admin` test user
   - The form may require pre-existing purchase orders or delivery orders to add items to
   - The route might require additional URL parameters (delivery order ID) to show the form
   - The feature may need specific facility configuration or inventory setup not present in fixtures

3. **Code implementation verified:** Despite inability to exercise the UI, the code changes in `SmartExternalDeliveryRow.tsx` are correctly implemented:
   - Plain Enter: prevents default, explicitly moves focus to next form element
   - Shift+Enter: prevents default, calls `onSubmit` handler
   - Applied to both Quantity and Price input fields
   - No changes to button-based submission

**Time spent:** Approximately 40 minutes on navigation exploration and test automation attempts.

---

## Recommendation

To properly QA this change:

1. **Provide specific navigation steps** or a direct URL to reach the Purchase Delivery item entry form in the test environment
2. **Verify permissions** - ensure the test user has rights to create/edit purchase deliveries
3. **Seed test data** - create a purchase order or delivery order that allows item entry
4. **Alternative:** Consider a focused E2E test in the Playwright suite that directly mounts or navigates to the delivery form component

The code implementation is sound and follows the specification exactly. The barrier is purely environmental access to the form in the running application.
