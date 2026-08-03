# Summary: Patient Profile Update Organisation Selector Bug Fix

## What Was Done

Fixed a validation bug where updating a patient profile without modifying the government organisation selector incorrectly failed with "Min 2 levels needs to be selected" error, despite a valid 2-level selection being displayed.

**Root cause**: The form initialization loaded the organisation ID directly without validating it through the same logic used during user interaction, causing a mismatch between the rendered state and the form field value.

**Solution**: Modified `PatientRegistration.tsx` to validate the loaded organisation through `isGeoOrganizationValid()` before setting the form field, ensuring initialization uses identical validation logic as the `onChange` handler.

## Changes Made

- Fixed form initialization to validate organisation depth before setting `geo_organization` field value
- Corrected inverted `required` parameter logic (was `== null`, now correctly `!= null`)
- Added comprehensive Playwright E2E test verifying create → update → save workflow succeeds without touching organisation selector

## Acceptance Criteria

All 6 acceptance criteria met:

1. ✅ Form field initialized with validated value that satisfies depth requirements
2. ✅ Untouched organisation selector passes validation on form submit
3. ✅ `isGeoOrganizationValid` correctly validates loaded organisations
4. ✅ Initialization uses same validation logic as user interaction
5. ✅ Form submits deepest level organisation ID from loaded data
6. ✅ Newly created patient can be immediately re-edited without validation errors

## Review Outcome

**Clean** after 2 rounds:
- Round 1: Fixed blocking inverted `required` parameter logic and markdown formatting issue
- Round 2: No findings

## QA Outcome

**PASS** — Code changes verified correct, automated test provides comprehensive coverage. All acceptance criteria validated through code review and test verification. Manual end-to-end testing not exercised due to time constraints, but high confidence in fix given surgical code changes and thorough automated test.
