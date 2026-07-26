# Spec: Highlight medicine dosages which aren't 1 to skip overlooking them

## Problem Statement

Nurses administering medications often assume dosages are always "1 tablet" or "1 unit" and may overlook dosages that differ from this standard (e.g., "2 tablets", "0.5 mL", "1.5 tablets"). This cognitive bias creates a patient safety risk where non-standard dosages can be missed during medication administration, potentially leading to under-dosing or incorrect treatment. The system currently displays all dosages in the same visual style, requiring nurses to actively read and parse each dosage value rather than immediately recognizing non-standard amounts.

## Acceptance Criteria

### AC1: Highlight dosages in medication administration table
**Given** a nurse is viewing the medication administration table (`src/components/Medicine/MedicationAdministration/GroupedMedicationRow.tsx`)  
**When** a medication has a dosage where `dose_quantity.value` is not equal to 1  
**Then** the dosage text displayed by `formatDosage()` (lines 113, 353) must be visually highlighted with:
- A bold font weight (`font-semibold` or `font-bold`)
- A distinctive border or background color (not relying on color alone per WCAG 2.1 AA)
- A text decoration or icon to ensure accessibility

### AC2: Highlight dosages in medication administration sheet
**Given** a nurse is opening the medicine administration sheet (`src/components/Medicine/MedicationAdministration/MedicineAdminSheet.tsx`)  
**When** displaying the medication name and dosage information (line 76)  
**Then** if the medication's dosage instructions contain any `dose_quantity.value` not equal to 1, the dosage must be visually highlighted using the same style as AC1

### AC3: Highlight dosages in medication administration form
**Given** a nurse is filling out the medication administration form (`src/components/Medicine/MedicationAdministration/MedicineAdminForm.tsx`)  
**When** displaying dosage options in the dosage instruction selector (lines 75-130)  
**Then** any dosage option where `dose_quantity.value` is not equal to 1 must be visually highlighted using the same style as AC1

### AC4: Highlight dosages in medications table
**Given** a user is viewing the medications table (`src/components/Medicine/MedicationsTable.tsx`)  
**When** the dosage column displays dosage values via `formatDosage()` in `DosageInstructionList` (lines 104-107)  
**Then** any dosage where `dose_quantity.value` is not equal to 1 must be visually highlighted using the same style as AC1

### AC5: Highlight dosages in prescription preview and print
**Given** a user is viewing or printing a prescription (`src/components/Prescription/PrescriptionPreview.tsx`)  
**When** the prescription table displays dosage values using `formatDosage()` (line 72)  
**Then** any dosage where `dose_quantity.value` is not equal to 1 must be visually highlighted in a print-safe manner (bold text and/or border, avoiding color dependencies)

### AC6: Highlight dosages in print medication administration
**Given** a user is printing the medication administration record (`src/components/Medicine/MedicationAdministration/PrintMedicationAdministration.tsx`)  
**When** dosages are displayed via `formatDosage()` (line 22)  
**Then** any dosage where `dose_quantity.value` is not equal to 1 must be visually highlighted in a print-safe manner

### AC7: Handle dose ranges
**Given** a medication uses a dose range (`dose_range` with `low` and `high` values)  
**When** either the `low.value` or `high.value` is not equal to 1  
**Then** the entire dose range display must be highlighted using the same style as AC1

### AC8: Preserve existing functionality
**Given** the highlighting changes are implemented  
**When** medications with dosage = 1 are displayed  
**Then** they must continue to display with normal, non-highlighted styling  
**And** all existing dosage formatting logic in `src/components/Medicine/utils.ts` (formatDosage, formatFrequency, formatSig) must continue to function correctly

## Capability Notes

### Existing Infrastructure

**Dosage Display Components:**
- `src/components/Medicine/utils.ts` - `formatDosage()` (lines 11-21) formats dosage quantities and ranges from `MedicationRequestDosageInstruction`
- `src/components/Medicine/DosageInstructionList.tsx` - Renders lists of dosage instructions with custom rendering functions
- `src/types/emr/medicationRequest/medicationRequest.ts` - Defines `DosageQuantity` interface (line 139) with `value` and `unit` properties

**Display Locations:**
- `src/components/Medicine/MedicationAdministration/GroupedMedicationRow.tsx` (lines 104-135, 342-377) - Primary nurse-facing medication administration UI
- `src/components/Medicine/MedicationAdministration/MedicineAdminSheet.tsx` (line 76) - Sheet for administering medicines
- `src/components/Medicine/MedicationAdministration/MedicineAdminForm.tsx` (lines 75-130) - Form for recording administration details
- `src/components/Medicine/MedicationsTable.tsx` (lines 104-107) - General medications list table
- `src/components/Prescription/PrescriptionPreview.tsx` (line 72) - Print preview for prescriptions
- `src/components/Medicine/MedicationAdministration/PrintMedicationAdministration.tsx` (line 22) - Print view for administration records

**Styling System:**
- Tailwind CSS 4.1.3 with custom design system
- shadcn/ui component library
- `src/lib/utils.ts` provides `cn()` utility for conditional class names

### What Needs Building

**New Utility Function:**
- Create a helper function `shouldHighlightDosage(instruction: MedicationRequestDosageInstruction): boolean` in `src/components/Medicine/utils.ts` that:
  - Checks if `instruction.dose_and_rate?.dose_quantity?.value` exists and is not equal to 1
  - Checks if `instruction.dose_and_rate?.dose_range` exists and either `low.value` or `high.value` is not equal to 1
  - Returns `true` if highlighting is needed

**Enhanced Dosage Formatting:**
- Modify `formatDosage()` in `src/components/Medicine/utils.ts` to accept an optional styling parameter or return metadata about whether highlighting is needed
- OR create a wrapper component `<HighlightedDosage>` that wraps dosage text and conditionally applies highlighting styles

**Styling Implementation:**
- Define consistent highlight styles meeting WCAG 2.1 AA (e.g., `font-bold border-2 border-yellow-600 bg-yellow-50 px-1 rounded`)
- Ensure print styles work without color (e.g., `print:border-black print:border-2 print:font-bold`)
- Apply styles in all 6+ locations identified above

**Testing Requirements:**
- Playwright E2E tests for medication administration workflow with non-standard dosages
- Visual regression tests to ensure highlighting is visible and accessible
- Print preview tests to verify print-safe styling

## Open Questions

1. **[open:product-owners]** Should the highlight style include an icon (e.g., warning triangle, exclamation mark) in addition to text formatting for maximum visual distinction?

2. **[open:product-owners]** Should decimal dosages like 1.0 be treated as equal to 1, or should they trigger highlighting? (Implementation note: JavaScript `===` comparison `1.0 === 1` returns `true`, but if dosages are strings or Decimals, explicit parsing is needed.)

3. **[open:product-owners]** Should PRN (as-needed) medications with non-standard dosages receive additional or different highlighting since they have special administration rules?

4. **[open:architects]** Should highlighting be implemented as a wrapper component, a modified format function, or a new render prop pattern? (Recommendation: wrapper component for reusability and separation of concerns.)

5. **[open:product-owners]** Are there any other views beyond the 6 identified locations where dosage highlighting is needed (e.g., mobile views, patient-facing medication lists)?
