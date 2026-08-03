# Implementation Plan: Option to lock or restrict access to certain encounters

## Approach

This feature adds encounter-level access restrictions to protect sensitive psychiatric and mental health records beyond standard permission controls. The implementation requires:

1. **Backend data model changes** — Add `locked` boolean field to Encounter model, track locking user and timestamp
2. **Authorization layer updates** — Extend permission checks to enforce locked encounter restrictions
3. **API endpoints** — Create lock/unlock endpoints for encounter access control
4. **Frontend UI updates** — Add lock/unlock controls, access denied states, and visual indicators
5. **Audit logging** — Track lock/unlock operations for compliance

## Decision Points Requiring Resolution

The spec identifies 4 open questions that must be answered by product/implementation teams before implementation:

1. **Access model** — Does locking restrict read, write, or both? Does it override or layer on existing permissions?
2. **Lock permission model** — Who can lock/unlock (creator, write users, or admins only)?
3. **Granular access** — Binary lock or support whitelisted users/roles?
4. **Department scope** — Psych-only or facility-wide feature?

**Recommended defaults for unblocking** (if team doesn't provide decisions):
- Lock restricts both read and write, overriding standard permissions except for facility admins
- Any user with encounter write permission can lock; facility admins and encounter creator can unlock
- Binary lock (no whitelist) for MVP simplicity
- Facility-wide feature (not department-restricted)

## Repositories

### care (backend)
- Add `locked`, `locked_by`, `locked_at` fields to Encounter model
- Create migration for new fields
- Implement lock/unlock endpoints (`/api/v1/encounter/{id}/lock/`, `/api/v1/encounter/{id}/unlock/`)
- Update encounter detail/list serializers to include lock status
- Add permission checks in encounter views to enforce locked access restrictions
- Extend audit log to record lock/unlock operations
- Add `can_lock_encounter` permission (if granular permission needed)

### care_fe (frontend)
- Update `EncounterRead` interface in `src/types/emr/encounter/encounter.ts` to include `locked`, `locked_by`, `locked_at`
- Add lock/unlock routes to `src/types/emr/encounter/encounterApi.ts`
- Create `<EncounterLockControl>` component for lock/unlock UI
- Update `EncounterProvider` in `src/pages/Encounters/utils/EncounterProvider.tsx` to handle locked state
- Add access denied state to encounter detail pages when user lacks access
- Add lock indicator to encounter list items in restricted view
- Update audit log display in `src/pages/Encounters/tabs/overview/summary-panel-details-tab/auditlogs.tsx` to show lock/unlock events
- Add permission check utilities for locked encounter access

## New Dependencies

None required — all functionality can be built with existing frameworks and libraries.

## Implementation Order

1. **Backend first** — Model changes, migrations, API endpoints, permission logic (care repo)
2. **Frontend integration** — Type updates, API client, UI components (care_fe repo)
3. **Testing** — Playwright E2E tests for lock/unlock workflows, permission enforcement
4. **Documentation** — Update user docs for locked encounters feature

## Risk Assessment

- **Medium complexity** — Requires authorization changes across read/write paths
- **Clinical safety relevance** — Access control for sensitive mental health records
- **Breaking change potential** — Low (additive feature, backward compatible)
- **Testing requirements** — Must verify permission enforcement in all access paths (list, detail, edit)

## Success Metrics

- Locked encounters cannot be accessed by unauthorized users
- Audit trail captures all lock/unlock operations with user and timestamp
- UI clearly indicates locked status to users with appropriate permissions
- No performance degradation in encounter list/detail queries
