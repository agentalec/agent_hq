# Implementation Tasks: Highlight medicine dosages which aren't 1

## Overview

This ticket adds visual highlighting (bold text + amber color) to medicine dosages that aren't 1, improving patient safety by making non-standard dosages immediately visible to nurses. All work is in the `agentalec/care_fe` repository.

Total estimated changes: ~150 lines across 5 files.

## Task List

### Task 1: Create dosage detection utility and highlighting component

**Repository:** `agentalec/care_fe`

**What it touches:**
- `src/components/Medicine/utils.ts` — Add `isNonStandardDosage()` helper function
- `src/components/Medicine/HighlightedDosage.tsx` — New reusable component for conditionally highlighted dosage display

**Changes:**
1. Add `isNonStandardDosage()` function to `utils.ts` that:
   - Accepts a `MedicationRequestDosageInstruction` parameter
   - Returns `true` if `dose_quantity.value !== "1"` OR if `dose_range` has `low.value !== "1"` OR `high.value !== "1"`
   - Returns `false` for standard dosages or missing data

2. Create new `HighlightedDosage.tsx` component that:
   - Accepts `instruction`, `children`, and optional `className` props
   - Uses `isNonStandardDosage()` to determine if highlighting is needed
   - Applies `font-bold text-amber-600` Tailwind classes when dosage is non-standard
   - Uses `cn()` utility to merge classNames properly

**Dependencies:** None

**Acceptance criteria covered:**
- AC1: Dosage of 1 appears normal (detection logic returns false for value="1")
- AC5: Dose range highlighting (checks both low/high values in range)
- AC6: WCAG 2.1 AA compliance (combines bold text weight with color)

**Estimated changes:** ~50 lines (30 in utils.ts, 20 in new component)

---

### Task 2: Apply highlighting to medication administration views

**Repository:** `agentalec/care_fe`

**What it touches:**
- `src/components/Medicine/MedicationAdministration/GroupedMedicationRow.tsx` — Wrap dosage outputs with `<HighlightedDosage>`

**Changes:**
1. Import `HighlightedDosage` component
2. Locate dosage output at line ~113 (medication card) and wrap with:
   ```tsx
   <HighlightedDosage instruction={di}>
     {formatDosage(di)}
   </HighlightedDosage>
   ```
3. Locate dosage output at line ~353 (latest prescription display) and apply same wrapping

**Dependencies:** Task 1 (requires `HighlightedDosage` component)

**Acceptance criteria covered:**
- AC2: Non-standard dosages highlighted in medicine administration sheet
- AC7: Grouped medication administration view highlighting

**Estimated changes:** ~20 lines (imports + 2 wrapping instances)

---

### Task 3: Apply highlighting to medications table

**Repository:** `agentalec/care_fe`

**What it touches:**
- `src/components/Medicine/MedicationsTable.tsx` — Wrap dosage column content with `<HighlightedDosage>`

**Changes:**
1. Import `HighlightedDosage` component
2. Locate dosage cell rendering at line ~104-107
3. Wrap dosage output with `<HighlightedDosage>` component, passing the instruction from the current medication row

**Dependencies:** Task 1 (requires `HighlightedDosage` component)

**Acceptance criteria covered:**
- AC3: Non-standard dosages highlighted in medications table

**Estimated changes:** ~15 lines (imports + wrapping logic)

---

### Task 4: Apply highlighting to prescription print preview

**Repository:** `agentalec/care_fe`

**What it touches:**
- `src/components/Prescription/PrescriptionPreview.tsx` — Apply conditional bold styling to dosages at line ~72

**Changes:**
1. Import `isNonStandardDosage` utility
2. Locate dosage rendering at line ~72 in print template
3. Apply conditional `font-bold` class to dosage output when `isNonStandardDosage()` returns true
4. Note: Use bold text only (not color) for print accessibility

**Dependencies:** Task 1 (requires `isNonStandardDosage` utility)

**Acceptance criteria covered:**
- AC4: Bold text in prescription print preview (color-independent for print accessibility)

**Estimated changes:** ~15 lines (imports + conditional styling)

---

## Acceptance Criteria Coverage Summary

| AC | Description | Covered by Task(s) |
|----|-------------|-------------------|
| AC1 | Dosage of 1 appears normal without highlighting | Task 1 (detection logic) |
| AC2 | Non-standard dosages highlighted in medicine administration sheet | Task 2 |
| AC3 | Non-standard dosages highlighted in medications table | Task 3 |
| AC4 | Bold text in prescription print preview (print-safe) | Task 4 |
| AC5 | Dose range highlighting when either value is not 1 | Task 1 (detection logic) |
| AC6 | WCAG 2.1 AA compliance (bold + color, not color alone) | Task 1 (component design) |
| AC7 | Grouped medication view highlighting | Task 2 |

All acceptance criteria are covered.

## Testing Notes

After implementation, manual testing should verify:
1. Medications with dosage = 1 display normally (no bold, no color)
2. Medications with dosage ≠ 1 display in bold amber text
3. Dose ranges highlight when any value is not 1
4. Print preview shows bold text without relying on color
5. Highlighting is distinguishable in high contrast and color blindness modes
6. Screen readers read dosage values without announcing highlighting

## Risk Assessment

- **Low risk**: UI-only changes with no backend, API, or data model modifications
- **Easy rollback**: Pure display logic that can be reverted without data migration
- **No breaking changes**: Additive styling that doesn't alter existing behavior
