# Spec: Option to lock or restrict access to certain encounters

## Problem Statement

Psychiatric departments require the ability to restrict access to sensitive encounters beyond standard permission controls. Current permissions allow all authorized users to view encounters, which is insufficient for sensitive mental health records.

## Acceptance Criteria

1. Given an encounter with write permission, when a user locks the encounter, then the encounter is marked as locked and access is restricted.
2. Given a locked encounter, when a user without explicit access attempts to view it, then they see an access denied message instead of encounter details.
3. Given a locked encounter, when the user who locked it views it, then they see a lock indicator and can unlock it.
4. Given a locked encounter, when a user with unlock permission unlocks it, then it becomes accessible per standard permissions.
5. Given locked encounters in the encounter list, when users without access view the list, then they see restricted indicators with no clinical details.
6. Given a facility administrator viewing locked encounters, when they check audit logs, then they see who locked/unlocked the encounter and when.
7. Given a locked encounter, when a user attempts to modify it without access, then the system denies the operation and logs the attempt.

## Capability Notes

- `src/types/emr/encounter/encounter.ts` — EncounterRead interface exists, needs `locked` boolean field
- `src/types/emr/encounter/encounterApi.ts` — API routes exist, needs lock/unlock endpoints (pattern: `src/types/billing/invoice/invoiceApi.ts:42-51`)
- `src/common/Permissions.tsx` — Permission system exists with encounter permissions, may need `can_lock_encounter` permission
- `src/pages/Encounters/utils/EncounterProvider.tsx` — Encounter context provider exists, needs access control logic updates
- `src/pages/Encounters/tabs/overview/summary-panel-details-tab/auditlogs.tsx` — Audit log UI exists for encounters

## Open Questions

[open] **Access model**: Should locking restrict both read and write, or only read? Should it override all permissions or layer on top of existing permissions? **Product team decision required** — blocks AC2 and AC7.

[open] **Lock permission model**: Who can lock/unlock encounters — only the encounter creator, any user with write permission, or only facility administrators? **Product team decision required** — blocks AC1 and AC4.

[open] **Granular access**: Should locked encounters support a whitelist of specific users/roles who can still access, or is it binary (locked/unlocked)? **Product team decision required** — blocks AC2 and AC3.

[open] **Department scope**: Should this feature be department-specific (e.g., only psych department can lock) or facility-wide? **Implementation team confirmation required** — affects all acceptance criteria.
