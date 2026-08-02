# Implementation Plan: Highlight medicine dosages which aren't 1

## Overview

This is a UI-only change to improve patient safety by making non-standard dosages (values other than 1) immediately visible to nurses administering medications. The implementation adds visual highlighting using bold text and warning color to dosages that aren't 1, while maintaining accessibility through non-color-dependent styling (WCAG 2.1 AA compliant).

## Classification

**CRUD** - This is a pure frontend display enhancement with no backend, data model, authorization, or FHIR/EMR changes.

## Architecture Approach

### Core Strategy

Create reusable utilities and components to:
1. Detect when a dosage value is non-standard (not equal to 1)
2. Conditionally wrap dosage text with highlighting styles that combine bold text weight and amber warning color

### Key Design Decisions

- **Detection logic**: Create `isNonStandardDosage()` utility that checks `DosageQuantity.value` or `DoseRange` low/high values against "1"
- **Highlighting component**: Create `<HighlightedDosage>` wrapper component that applies `font-bold` and `text-amber-600` classes when needed
- **Accessibility**: Use both color (amber) and text weight (bold) to ensure WCAG 2.1 AA compliance for color vision deficiency
- **Print support**: Bold text remains visible in print mode without relying on color

## Repositories Touched

### agentalec/care_fe (frontend)

**New files:**
- `src/components/Medicine/HighlightedDosage.tsx` — Reusable component for conditionally highlighted dosage display

**Modified files:**
- `src/components/Medicine/utils.ts` — Add `isNonStandardDosage()` helper function
- `src/components/Medicine/MedicationAdministration/GroupedMedicationRow.tsx` — Wrap dosage output at lines 113 and 353 with `<HighlightedDosage>`
- `src/components/Medicine/MedicationsTable.tsx` — Wrap dosage output at line 106 with `<HighlightedDosage>`
- `src/components/Prescription/PrescriptionPreview.tsx` — Apply bold styling to non-standard dosages at line 72

## Implementation Details

### Step 1: Create detection utility

Add to `src/components/Medicine/utils.ts`:

```typescript
export function isNonStandardDosage(
  instruction?: MedicationRequestDosageInstruction
): boolean {
  if (!instruction?.dose_and_rate) return false;
  
  const { dose_range, dose_quantity } = instruction.dose_and_rate;
  
  if (dose_range) {
    // If either low or high is not 1, consider non-standard
    return dose_range.low.value !== "1" || dose_range.high.value !== "1";
  }
  
  if (dose_quantity) {
    return dose_quantity.value !== "1";
  }
  
  return false;
}
```

### Step 2: Create highlighting component

New file `src/components/Medicine/HighlightedDosage.tsx`:

```typescript
interface HighlightedDosageProps {
  instruction?: MedicationRequestDosageInstruction;
  children: React.ReactNode;
  className?: string;
}

export function HighlightedDosage({
  instruction,
  children,
  className,
}: HighlightedDosageProps) {
  const shouldHighlight = isNonStandardDosage(instruction);
  
  return (
    <span
      className={cn(
        shouldHighlight && "font-bold text-amber-600",
        className
      )}
    >
      {children}
    </span>
  );
}
```

### Step 3: Update medication administration view

In `GroupedMedicationRow.tsx`, wrap dosage text:
- Line 113: Wrap `formatDosage(di)` in medication card
- Line 353: Wrap `formatDosage(di)` in latest prescription display

### Step 4: Update medications table

In `MedicationsTable.tsx` at line 106, wrap the dosage cell content with `<HighlightedDosage>`.

### Step 5: Update prescription preview

In `PrescriptionPreview.tsx` at line 72, conditionally apply bold styling to dosage values when rendering for print. Since print doesn't support color reliably, use bold text weight only.

## Testing Strategy

### Unit Tests
- Test `isNonStandardDosage()` with:
  - Standard dosage (value = "1")
  - Non-standard dosages (value = "2", "0.5", "1.5")
  - Dose ranges with standard and non-standard values
  - Missing or undefined instructions

### Visual Regression Tests
- Capture screenshots of:
  - Medication administration grid with mixed standard/non-standard dosages
  - Medications table with highlighted values
  - Prescription preview in print mode

### Accessibility Tests
- Verify bold text is distinguishable in:
  - High contrast mode
  - Color vision deficiency simulation (protanopia, deuteranopia, tritanopia)
  - Print preview
- Test with screen reader to ensure highlighting doesn't affect content reading

### Manual Testing Checklist
1. Open medication administration sheet with medications having dosages of 1, 2, 0.5
2. Verify only non-standard dosages (2, 0.5) appear in bold amber text
3. Open medications table and verify highlighting appears consistently
4. Print preview prescription and verify bold text is visible without color
5. Test with browser zoom at 200% to verify text remains readable
6. Simulate color blindness modes to verify bold text provides sufficient distinction

## Acceptance Criteria Coverage

| Criterion | Implementation |
|-----------|----------------|
| AC1: Dosage of 1 appears normal | `isNonStandardDosage()` returns false for value="1" |
| AC2: Non-standard dosages highlighted in admin sheet | `<HighlightedDosage>` in `GroupedMedicationRow.tsx` |
| AC3: Non-standard dosages highlighted in table | `<HighlightedDosage>` in `MedicationsTable.tsx` |
| AC4: Bold text in print preview | Conditional styling in `PrescriptionPreview.tsx` |
| AC5: Dose range highlighting | `isNonStandardDosage()` checks both low/high values |
| AC6: WCAG 2.1 AA compliance | Combined bold + color approach |
| AC7: Grouped medication view highlighting | Same `<HighlightedDosage>` component reused |

## Dependencies

No new dependencies required. Implementation uses:
- Existing Tailwind CSS utilities (`font-bold`, `text-amber-600`)
- Existing component patterns (`cn()` utility from CAREUI)
- Existing type definitions (`MedicationRequestDosageInstruction`, `DosageQuantity`, `DoseRange`)

## Risk Assessment

**Low risk:**
- UI-only change with no backend or data model impact
- Uses existing styling utilities and patterns
- Additive change that doesn't modify existing behavior
- Easy to roll back if issues arise

## Rollout Plan

1. Implement and test in development environment
2. Deploy to staging for clinical workflow validation
3. Gather feedback from pilot nurses on visibility and usability
4. Deploy to production after sign-off

## Success Metrics

- Zero medication administration errors due to overlooked non-standard dosages (baseline comparison)
- Positive feedback from nurses on improved dosage visibility
- No accessibility violations in WCAG audits
- No performance degradation in medication views
