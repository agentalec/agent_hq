# Implementation Tasks: Show user's role on user list cards

## Task 1: Add user type formatting and restore role display in user cards

**Repository:** `agentalec/care_fe`

**Estimated Changes:** ~50 lines

**Dependencies:** None

**Description:**

Transform the raw `user_type` values (doctor, nurse, staff, volunteer, administrator) into human-readable, internationalized text for display in user list cards.

**What it touches:**
- `src/components/Users/UserListAndCard.tsx`
  - Update `UserGrid` component to format `user.user_type` before passing to `roleName` prop
  - Update `UserList` component (table view) to format `user.user_type` for display in the role column
  - Ensure consistent styling (`text-sm text-gray-500`) matches spec requirements

**Implementation details:**
1. Import `useTranslation` hook in `UserListAndCard.tsx`
2. In `UserGrid` component (line ~162):
   - Use `t(user.user_type)` to translate the raw user type value
   - Pass the translated string as `roleName` prop to `UserCard`
3. In `UserList` component (line ~220):
   - Use `t(user.user_type)` to translate the raw user type value in the role column
   - Replace direct `user.user_type` display with translated value
4. Verify that `UserCard` component's existing role rendering (line 118) correctly displays the formatted role with proper styling
5. Add null-safety check to handle missing `user_type` gracefully (AC #7)

**Acceptance Criteria Covered:**
- AC #1: User card in card view displays role adjacent to name/username ✓
- AC #2: User row in table view displays role in dedicated column ✓
- AC #3: Facility users page shows user_type as readable text ✓
- AC #6: Role uses consistent styling (text-sm text-gray-500) ✓
- AC #7: Missing role data handled gracefully ✓

**Testing:**
- Verify role display in facility users page (card view) for all user types
- Verify role display in facility users page (table view) for all user types
- Verify translated role text appears correctly (Doctor, Nurse, Staff, Volunteer, Administrator)
- Verify missing role data doesn't break card layout
- Test with fixture users: `care-doctor`, `care-nurse`, `care-staff`, `care-volunteer`, `care-fac-admin`

---

## Task 2: Verify organization role display

**Repository:** `agentalec/care_fe`

**Estimated Changes:** ~0-10 lines (verification + potential bug fixes only)

**Dependencies:** Task 1

**Description:**

Verify that organization user pages correctly display organization role names in user cards. According to the spec and plan, these pages already pass `userRole.role.name` as `roleName`, but this task ensures the implementation works end-to-end.

**What it touches:**
- `src/pages/Organization/OrganizationUsers.tsx` (verification)
- `src/pages/Facility/settings/organizations/FacilityOrganizationUsers.tsx` (verification)

**Implementation details:**
1. Review `OrganizationUsers.tsx` line 216 to confirm `roleName={userRole.role.name}` is correctly passed
2. Review `FacilityOrganizationUsers.tsx` line 163 to confirm `roleName={userRole.role.name}` is correctly passed
3. Verify that organization role names are displayed correctly in the rendered cards
4. If any display issues are found, apply fixes consistent with Task 1's approach
5. Ensure styling consistency with facility user cards

**Acceptance Criteria Covered:**
- AC #4: Organization users page shows organization role name ✓
- AC #5: Facility organization users page shows facility organization role name ✓
- AC #6: Consistent styling across all role displays ✓

**Testing:**
- Verify role display on organization users page (e.g., Admin, Manager, Member)
- Verify role display on facility organization users page
- Test with fixture users: `care-role-admin`, `care-role-manager`, `care-role-member`
- Confirm visual consistency between facility user roles and organization roles

---

## Task 3: Add automated tests for role display

**Repository:** `agentalec/care_fe`

**Estimated Changes:** ~150-200 lines

**Dependencies:** Task 1, Task 2

**Description:**

Create Playwright E2E tests to verify role display across all user list contexts, ensuring the feature works correctly and preventing future regressions.

**What it touches:**
- `tests/facility/user-role-display.spec.ts` (new file)

**Implementation details:**
1. Create new test file following Playwright conventions in `tests/PLAYWRIGHT_GUIDE.md`
2. Test facility users page card view:
   - Navigate to `/facility/{facilityId}/users`
   - Verify role text is visible on user cards
   - Verify different user types display correct role text
3. Test facility users page table view:
   - Switch to table view
   - Verify role column displays formatted user types
4. Test organization users page:
   - Navigate to organization users page
   - Verify organization role names display correctly
5. Test facility organization users page:
   - Navigate to facility organization users page
   - Verify facility organization role names display correctly
6. Test missing role data edge case:
   - Mock user data without role
   - Verify card renders without error

**Acceptance Criteria Covered:**
- All ACs (#1-7) verified through automated testing

**Testing:**
- Run tests against local backend with fixtures loaded
- Verify tests pass consistently
- Ensure tests follow repository patterns from existing facility tests

---

## Coverage Summary

All acceptance criteria from `specs/69/spec.md` are covered:

| AC # | Description | Covered by Task(s) |
|------|-------------|-------------------|
| AC #1 | Role displayed in card view adjacent to name/username | Task 1 |
| AC #2 | Role displayed in table view in dedicated column | Task 1 |
| AC #3 | Facility users show user_type as readable text | Task 1 |
| AC #4 | Organization users show organization role name | Task 2 |
| AC #5 | Facility organization users show facility org role name | Task 2 |
| AC #6 | Consistent styling (text-sm text-gray-500) and positioning | Task 1, Task 2 |
| AC #7 | Missing role data handled gracefully | Task 1 |

All tasks validated by automated tests in Task 3.
