# Ticket 64: Highlight medicine dosages which aren't 1 to skip overlooking them

## Problem Statement

Nurses administering medications commonly assume dosages are 1 unit and may overlook when a dosage is different (e.g., 2 tablets, 0.5 mL). This creates a patient safety risk where incorrect amounts are administered. The dosage value currently appears in plain text without visual distinction, requiring nurses to actively read and verify each value rather than having non-standard dosages immediately draw their attention.

## Acceptance Criteria

1. Given a medication with dosage value of 1, when displayed in any medication view, then the dosage appears in normal text styling without highlighting.
2. Given a medication with dosage value other than 1 (e.g., 2, 0.5, 1.5), when displayed in the medicine administration sheet, then the dosage value is visually highlighted using bold text and a warning color (amber/yellow).
3. Given a medication with dosage value other than 1, when displayed in the medications table, then the dosage value is visually highlighted using bold text and a warning color.
4. Given a medication with dosage value other than 1, when displayed in prescription print preview, then the dosage value is visually highlighted using bold text (color-independent for print accessibility).
5. Given a medication with a dose range (e.g., 1-2 tablets), when either value is not 1, then the entire range is highlighted.
6. Given a non-standard dosage is highlighted, when a user has color vision deficiency, then the highlighting remains distinguishable through bold text weight and not color alone (WCAG 2.1 AA compliance).
7. Given medications listed in the grouped medication administration view, when any request in the group has a non-standard dosage, then the dosage displayed for that medication is highlighted.

## Capability Notes

- `src/components/Medicine/utils.ts:formatDosage` — exists, formats dosage from instruction to display string (e.g., "2 tablets", "0.5 mL")
- `src/components/Medicine/DosageInstructionList.tsx` — exists, renders divided list of dosage instructions with custom render callback
- `src/components/Medicine/MedicationAdministration/GroupedMedicationRow.tsx` — exists, displays medications in administration grid with dosage at lines 113, 353
- `src/components/Medicine/MedicationsTable.tsx` — exists, displays medications table with dosage column at line 104-107
- `src/components/Prescription/PrescriptionPreview.tsx` — exists, print template showing dosage at line 72
- `src/types/emr/medicationRequest/medicationRequest.ts:DosageQuantity` — exists, type definition with value (string) and unit fields
- Component for conditional highlighting based on dosage value — needs building

## Open Questions

None.
