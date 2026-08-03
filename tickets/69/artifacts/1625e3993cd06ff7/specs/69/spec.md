# Specification: Show user's role on user list cards

## Problem Statement

User list cards previously displayed each user's role alongside their name, but this information is no longer consistently visible. Operators managing large facilities cannot distinguish between Administrators, Nurses, and other roles without opening each user's detail page, slowing onboarding and access reviews.

## Acceptance Criteria

1. Given a user list in card view, when viewing any user card, then the user's role is displayed adjacent to their name and username.
2. Given a user list in table view, when viewing any user row, then the user's role is displayed in a dedicated role column.
3. Given a facility users page in card view, when viewing user cards, then each card shows the user_type value (doctor, nurse, staff, volunteer, administrator) rendered as readable text.
4. Given an organization users page in card view, when viewing user cards with organization roles, then each card shows the organization role name.
5. Given a facility organization users page in card view, when viewing user cards, then each card shows the facility organization role name.
6. Given any user card rendering, when the role is displayed, then it uses consistent styling (text-sm text-gray-500) and positioning relative to user identity.
7. Given a user list with no role data available, when viewing cards, then the role field is omitted without breaking the card layout.

## Capability Notes

- `src/components/Users/UserListAndCard.tsx:UserCard` — accepts `roleName` prop, renders role on line 118 when provided
- `src/components/Users/UserListAndCard.tsx:UserGrid` — passes `user.user_type` as `roleName` on line 162
- `src/components/Users/UserListAndCard.tsx:UserList` — displays `user.user_type` in table role column on line 220
- `src/pages/Organization/OrganizationUsers.tsx` — passes `userRole.role.name` as `roleName` on line 216
- `src/pages/Facility/settings/organizations/FacilityOrganizationUsers.tsx` — passes `userRole.role.name` as `roleName` on line 163

## Open Questions

None.
