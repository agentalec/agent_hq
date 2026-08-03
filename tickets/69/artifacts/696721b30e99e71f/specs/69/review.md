# Review: Show user's role on user list cards

## Round 1

- **blocker** `src/pages/Organization/OrganizationUsers.tsx:216` — AC4 not addressed; `userRole.role.name` is passed untranslated, needs `t(userRole.role.name)` wrapper.
- **blocker** `src/pages/Facility/settings/organizations/FacilityOrganizationUsers.tsx:163` — AC5 not addressed; `userRole.role.name` is passed untranslated, needs `t(userRole.role.name)` wrapper.
- **should-fix** `tests/facility/users/roleDisplay.spec.ts` — tests only cover facility users context; should add tests for organization contexts (AC4, AC5).
