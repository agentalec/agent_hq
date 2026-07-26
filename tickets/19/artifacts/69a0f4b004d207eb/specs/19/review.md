# Review: Highlight medicine dosages which aren't 1 to skip overlooking them

## Round 1

### Acceptance Criteria Coverage

#### ✅ AC1: Highlight dosages in medication administration table
**Status**: Implemented correctly

**Evidence**: 
- `GroupedMedicationRow.tsx` lines 107-111 and 130-133 wrap dosage text with `<HighlightedDosage>` component
- Uses `shouldHighlightDosage()` utility to check if highlighting is needed
- Applies consistent styling per spec requirements

**Verification**:
```typescript
<HighlightedDosage instruction={di}>
  {dosage}
</HighlightedDosage>
```

#### ❌ AC2: Highlight dosages in medication administration sheet
**Status**: NOT IMPLEMENTED - **BLOCKER**

**Issue**: `MedicineAdminSheet.tsx` was NOT modified in the diff. Line 76 displays medication name but does not apply any highlighting to dosage information.

**Expected**: The component should wrap dosage display with `<HighlightedDosage>` component or apply highlighting logic.

**Current state**: File `src/components/Medicine/MedicationAdministration/MedicineAdminSheet.tsx` exists but has no changes in the diff patch. The medication name is displayed at line 76 but dosage highlighting is missing.

#### ✅ AC3: Highlight dosages in medication administration form
**Status**: Implemented correctly

**Evidence**: 
- `MedicineAdminForm.tsx` lines 165-168 and 178-182 wrap dosage text with `<HighlightedDosage>`
- Applied in both card view and list view of dosage options

#### ✅ AC4: Highlight dosages in medications table
**Status**: Implemented correctly

**Evidence**: 
- `MedicationsTable.tsx` lines 236-245 wrap dosage text with `<HighlightedDosage>` in renderItem callback
- Properly handles null/empty dosage with fallback to "-"

#### ✅ AC5: Highlight dosages in prescription preview and print
**Status**: Implemented with print-safe approach

**Evidence**: 
- `PrescriptionPreview.tsx` lines 321-322 add warning emoji `⚠` prefix for non-standard dosages
- Uses `shouldHighlightDosage()` to detect which dosages need marking
- Print-safe: Uses text prefix rather than color-dependent styling

**Note**: Uses different approach (emoji prefix) rather than `<HighlightedDosage>` component, but achieves the same goal in a print-safe manner.

#### ✅ AC6: Highlight dosages in print medication administration
**Status**: Implemented with print-safe approach

**Evidence**: 
- `PrintMedicationAdministration.tsx` lines 208-210 add warning emoji `⚠` prefix
- Print-safe: Uses text marker without color dependency

#### ✅ AC7: Handle dose ranges
**Status**: Implemented correctly

**Evidence**: 
- `utils.ts` lines 273-276 check both `dose_range.low.value` and `dose_range.high.value`
- Returns `true` if either value is not equal to 1
- Logic: `return lowValue !== 1 || highValue !== 1`

#### ✅ AC8: Preserve existing functionality
**Status**: Implemented correctly

**Evidence**: 
- `formatDosage()`, `formatFrequency()`, and `formatSig()` functions remain unchanged
- Highlighting is additive via wrapper component
- Standard dosages (value === 1) return false from `shouldHighlightDosage()` and render without highlighting

### Implementation Quality

#### ✅ Component Design
**Quality**: Good

**Strengths**:
- Clean separation of concerns with `<HighlightedDosage>` wrapper component
- Reusable utility function `shouldHighlightDosage()`
- Props-based configuration (`printSafe`, `showIcon`)
- WCAG 2.1 AA compliant with multiple visual cues

**Component structure**:
```typescript
<HighlightedDosage 
  instruction={di}
  printSafe={false}  // Optional
  showIcon={false}   // Optional
>
  {formatDosage(di)}
</HighlightedDosage>
```

#### ✅ Accessibility Implementation
**Quality**: Excellent

**Compliance**: 
- Multiple visual cues (bold text, border, background color, optional icon)
- `aria-label="Non-standard dosage - requires attention"` on highlighted spans
- `aria-hidden="true"` on decorative icons
- Print styles don't rely on color: `print:border-black print:font-bold print:bg-transparent`

**WCAG 2.1 AA**: Fully compliant with color-independent visual indicators.

#### ✅ Utility Function Logic
**Quality**: Correct

**Implementation**:
```typescript
export function shouldHighlightDosage(
  instruction?: MedicationRequestDosageInstruction,
): boolean {
  if (!instruction?.dose_and_rate) return false;
  const { dose_range, dose_quantity } = instruction.dose_and_rate;
  
  // Check dose_range
  if (dose_range) {
    const lowValue = parseFloat(dose_range.low.value);
    const highValue = parseFloat(dose_range.high.value);
    return lowValue !== 1 || highValue !== 1;
  }
  
  // Check dose_quantity
  if (dose_quantity) {
    const value = parseFloat(dose_quantity.value);
    return value !== 1;
  }
  
  return false;
}
```

**Correctness**: 
- ✅ Handles undefined/null instructions
- ✅ Checks both dose_range and dose_quantity
- ✅ Uses `parseFloat()` to handle string "1.0" === numeric 1 (addresses Open Question #2)
- ✅ OR logic for dose_range (highlights if either low or high != 1)

#### ✅ Testing Coverage
**Quality**: Comprehensive

**Test file**: `tests/facility/patient/encounter/medicine/dosageHighlighting.spec.ts`

**Coverage**:
1. ✅ Non-standard dosages are visually highlighted (dosage = 2)
2. ✅ Standard dosages (dosage = 1) are NOT highlighted
3. ✅ Dose range highlighting (0.5 - 1.5 range)

**Test approach**:
- Creates prescriptions with different dosage values
- Verifies highlighting classes (`.border-2.font-semibold`, `.border-yellow-600`)
- Validates standard dosages don't have highlighting parent elements
- Uses proper Playwright patterns (test.step, proper locators)

### Over-Engineering Check

#### 🟡 Unused Props (Minor)
**Finding**: `showIcon` prop on `<HighlightedDosage>` is defined but never used in the codebase.

**Impact**: Low - no functional issue, just unused code

**Recommendation**: Should-fix - Either use the icon in at least one location or remove the prop to keep the API surface minimal.

#### ✅ No Speculative Abstractions
**Finding**: Implementation is appropriately scoped. No unnecessary abstractions or premature optimization.

#### ✅ Print-Safe Approach
**Finding**: Two different approaches for print safety:
1. `<HighlightedDosage>` component with `printSafe` prop
2. Emoji prefix (`⚠`) for print views

**Assessment**: Appropriate - The emoji approach in `PrintMedicationAdministration.tsx` and `PrescriptionPreview.tsx` is pragmatic for actual print scenarios where React components may not render.

### Security Check

#### ✅ No Security Issues
- No hardcoded secrets
- No injection points (using React children prop, not dangerouslySetInnerHTML)
- No new dependencies added
- No authorization bypass concerns (display-only feature)
- Uses existing type-safe API structures

### Code Quality Issues

#### 🟡 Formatting Error in PLAYWRIGHT_GUIDE.md (Nit)
**Finding**: Lines 352-369 have incorrect formatting - missing newlines between template literals

**Current**:
```typescript
`/facility/${facilityId}/overview``/facility/${facilityId}/settings/locations`
```

**Expected**:
```typescript
`/facility/${facilityId}/overview`
`/facility/${facilityId}/settings/locations`
```

**Impact**: Low - documentation-only, doesn't affect functionality

### Summary

#### Blockers (1)
1. **AC2 Not Implemented**: `MedicineAdminSheet.tsx` is missing dosage highlighting

#### Should-Fix (1)
1. **Unused showIcon prop**: Either use it or remove it to keep the API minimal

#### Nits (1)
1. **PLAYWRIGHT_GUIDE.md formatting**: Template literal lines need newlines

#### Strengths
- ✅ Excellent component design with clean separation of concerns
- ✅ WCAG 2.1 AA compliant accessibility implementation
- ✅ Comprehensive test coverage with realistic scenarios
- ✅ Handles edge cases (dose ranges, null values, string vs. numeric comparison)
- ✅ Print-safe implementations for physical document output
- ✅ Consistent application across 5 of 6 required locations

#### Decision
**Hand off to**: `implement`  
**Reason**: Blocker identified - AC2 (MedicineAdminSheet.tsx) not implemented. Must add dosage highlighting to the medicine administration sheet component.
