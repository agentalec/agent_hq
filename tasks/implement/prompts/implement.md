# Implement prompt

Read `constitution.md` and `specs/{ticket}/spec.md` (handed to you -- see
Available inputs below).

If `specs/{ticket}/review.md` was also handed to you, this is a re-implement
round: read its **latest** `## Round N` section and resolve every `blocker`
it raises (address `should-fix` items where reasonable). Otherwise implement
the spec from scratch.

Implement the spec's acceptance criteria that apply to your assigned
repository (see Work repo below); skip criteria scoped to a different
repo -- another `implement` run handles those. For each criterion that
applies:

- write the code and its tests
- commit it
- keep the diff scoped to that criterion; don't fold in unrelated changes

Never touch files outside your assigned repository. Commit as you go rather
than batching everything at the end -- it keeps your own working state
recoverable. Your commits are squashed into one before they reach the work
repo, so the message that ends up on the branch is the `summary` you write in
`.agent-hq/control.json` (see Control output below) -- describe what you
actually changed there, not what the ticket asked for. The engine formats
changed files after you finish, per the work repo's `format` config -- you do
not need to run the repo formatter yourself.

## Write `specs/{ticket}/qa-plan.md` (required)

QA will execute this plan in a browser; it must not invent clicks from scratch.
For every **user-facing** acceptance criterion that applies to your repo,
add a section with Action / Expect / Record steps. If nothing is user-facing,
write a short file saying so.

**Live plan only.** Agent QA drives the running app; it does not run the
repo's Playwright suite or CI. Put "add Playwright coverage" / "CI must
pass" under a **Test plan / notes** section (or in the implement summary) —
**not** as a live Action/Expect/Record criterion in `qa-plan.md`. Suite
items that land in the live list waste QA retries when scored dishonestly.

```markdown
## <criterion-id> — <title from spec>

### Research map
- routes: src/Routers/routes/... → /facility/:facilityId/...
- components: ...
- i18n labels: "Save", "Select device", ...
- auth/role: tests/.auth/user.json | nurse.json | ...
- permissions / facility-scoped: yes|no
- fixtures needed: seeded facility, patient, encounter, ...

### Prerequisites
- facility context active (if applicable)
- data that must already exist (prefer fixtures; QA may UI-create on localhost)

### Data setup
- Prefer fixtures: <exact what load-fixtures already provides; IDs if known>
- If missing — UI recipe (ordered clicks):
  1. Go to `/facility/{facilityId}/settings/...`
  2. Create <entity> with fields: ...
  3. ...
- If UI graph is deep (3+ entity types / multi-settings), API seed allowed:
  - Paths: copy exact templates from `src/types/.../*Api.ts`
    (e.g. POST `/api/v1/facility/{facilityId}/activity_definition/`)
  - Auth: `getApiUrl` + `getApiHeaders` from `tests/helper/utils.ts` +
    `tests/.auth/user.json`
  - Body sketch: minimal JSON fields required
  - Never unscoped `/api/v1/<resource>/`
- After seed: open the target URL and confirm dropdown/section visible
  before scoring the criterion

### Steps
1. **Action:** ...
   **Expect:** ...
   **Record through:** yes
   **Still after:** optional (only if screenshots enabled for the repo)
2. ...

### Success looks like
- toast / URL / visible state that proves the criterion

## Test plan / notes
- Playwright E2E / CI expectations for implement (not live QA criteria)
```

**Data setup is required** for every live criterion that needs non-default
data. Listing “fixtures needed: SR with multi-code AD” is not enough — QA
executes a recipe; it must not invent browse-and-hope. Vague “QA may
UI-create” without ordered clicks (and facility-scoped API paths when the
graph is deep) is a should-fix in review.

### Worked example — Activity Definition seed

```markdown
### Data setup
- Prefer fixtures: load-fixtures leaves a facility; no Activity Definition
  with the codes this criterion needs.
- UI recipe:
  1. Go to `/facility/{facilityId}/settings/activity_definitions`
  2. Create → title `qa-ad-{ticket}-{slug}`, status active, add required codes
  3. Save; confirm the new row appears in the list
- API seed (if UI graph is deep / UI create failed):
  - POST `/api/v1/facility/{facilityId}/activity_definition/`
    (verbatim from `src/types/emr/activityDefinition/activityDefinitionApi.ts`)
  - Auth: `getApiUrl()` + `getApiHeaders()` + `tests/.auth/user.json`
  - Body: minimal create fields from the nearby type / create form
  - Never POST `/api/v1/activity_definition/` (unscoped — will 404)
- Verify: open the target Service Request URL; confirm the AD appears in
  the dropdown/section before scoring
```

### Route discovery recipe (paste paths into Data setup)

When writing Data setup, paste the exact `path` + method from the FE route
object so QA does not rediscover under time pressure. If you need to find
a path:

1. Name the entity to create (e.g. Activity Definition, Specimen Definition,
   Service Request).
2. In the FE worktree, find the matching file under `src/types/**/` — usually
   `*Api.ts` next to the domain type (e.g.
   `src/types/emr/activityDefinition/activityDefinitionApi.ts`). Grep:
   `rg -n "activity_definition|/facility/\{facilityId\}" src/types --glob '*Api.ts'`.
3. Open that file; use the route entry for create (often `create` / `list`
   with `method: HttpMethod.POST` or GET). Copy the `path` string
   **verbatim** (e.g. `/api/v1/facility/{facilityId}/activity_definition/`).
4. Resolve path params from setup-notes / fixtures (`facilityId`,
   `patientId`, …) — never drop the facility segment.
5. Infer minimal body from nearby types / create form / existing Playwright
   helpers under `tests/` if present; do not guess unscoped top-level routes.
6. Ban: inventing `/api/v1/<resource>/` without `{facilityId}` just because
   the resource name “sounds right”.

Where to look in CARE (compress into the research map):

- Routes: `src/Routers/routes/`
- Sidebar: `src/components/ui/sidebar/`
- Pages/components: `src/pages/`, `src/components/`
- Labels: `public/locale/en.json`
- Permissions: `src/common/Permissions.ts`, `PermissionContext`
- Existing E2E hints: `tests/` (for implement tests — not live QA steps)
- APIs: `src/types/**/*Api.ts` (copy create paths into Data setup)

When the work is committed, queue a single `review` entry in your
`.agent-hq/control.json` (see Control output below), forwarding
`specs/{ticket}/spec.md` and `specs/{ticket}/qa-plan.md` in `artifacts` --
and also `specs/{ticket}/review.md` if it was given to you, so the reviewer
keeps its round history.

Leave the rest of the ticket's queue alone: entries you do not mention stay
queued, and you have no reason to cancel work someone else planned.
