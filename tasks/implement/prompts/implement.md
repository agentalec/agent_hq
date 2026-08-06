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

Where to look in CARE (compress into the research map):

- Routes: `src/Routers/routes/`
- Sidebar: `src/components/ui/sidebar/`
- Pages/components: `src/pages/`, `src/components/`
- Labels: `public/locale/en.json`
- Permissions: `src/common/Permissions.ts`, `PermissionContext`
- Existing E2E hints: `tests/` (for implement tests — not live QA steps)
- APIs: `src/types/**/*Api.ts`

When the work is committed, queue a single `review` entry in your
`.agent-hq/control.json` (see Control output below), forwarding
`specs/{ticket}/spec.md` and `specs/{ticket}/qa-plan.md` in `artifacts` --
and also `specs/{ticket}/review.md` if it was given to you, so the reviewer
keeps its round history.

Leave the rest of the ticket's queue alone: entries you do not mention stay
queued, and you have no reason to cancel work someone else planned.
