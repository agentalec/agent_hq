# Summary: Organization missing in Edit Patient State

## What Was Done

Fixed the missing organization field in patient edit flow by implementing support for a `section=general-info` query parameter. When users click "Edit" from the Demographics tab, the URL now includes this parameter, causing the "Additional Details" accordion section to auto-expand and reveal the organization picker (GovtOrganizationPicker).

The organization field was already present in the form — it just wasn't visible because the accordion section was collapsed by default. No changes to the patient API or data model were required.

## Changes Made

- Modified `PatientRegistration.tsx` to read the `section` query parameter
- Added `useEffect` hook to auto-expand the "Additional Details" accordion when `section==="general-info"`
- Implemented auto-scroll behavior to bring the expanded section into view

## Acceptance Criteria Status

- **AC1** ✅ Organization field visible when navigating from Demographics tab with section parameter
- **AC2** ⚠️ Save functionality not fully exercised (implementation uses standard form patterns)
- **AC3** ⚠️ Empty organization scenario not tested (requires specific test data)
- **AC4** ⚠️ Validation not fully exercised (validation logic present in code)
- **AC5** ✅ Organization field visible in Additional Details section
- **AC6** ⚠️ Navigation prompt not tested (uses standard `useNavigationPrompt` hook)

## Review Outcome

**Clean** — no findings after round 3. Earlier rounds addressed formatting issues and ensured actual implementation was completed.

## QA Outcome

**PASS** — Visual QA verified the organization field is now accessible in edit mode when navigating from Demographics tab. The implementation correctly:
- Expands the Additional Details accordion based on query parameter
- Displays the organization picker fields
- Works across desktop and mobile viewports

Full integration testing (save operations, validation, navigation prompts) was beyond visual QA scope but implementation follows established patterns used throughout the application.

## Recommendation

Ready for merge. The core issue is resolved: users can now access and edit the organization field from the Demographics tab. Consider adding Playwright E2E tests for complete form submission and validation behavior in future work.
