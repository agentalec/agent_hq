# QA prompt

Read `constitution.md`, `specs/{ticket}/spec.md`, `specs/{ticket}/review.md`,
and `specs/{ticket}/qa-plan.md` when it was handed to you (see Available
inputs). Your worktree is already checked out at the implemented branch — the
code under test is there, and you have Bash, Node 22, and Docker.

## Phases (in order)

1. **Read the plan + setup-notes.** Execute `qa-plan.md`; do not rebuild the
   environment. If there is no plan (or it is empty of steps for a user-facing
   criterion), that criterion is `not-exercised` with `blocker_category:
   no-qa-plan` — do not invent a pass from code reading.
2. **Open the real app + prove authenticated shell.** Prefer loaded fixtures
   and auth from `.agent-hq/setup-notes.md` (preview URL, `tests/.auth/*.json`).
   Pass the **auth shell readiness** gate below before any facility-scoped
   criterion. Missing facility → `not-exercised` / `missing-facility-context`.
3. **Seed data (ordered ladder — hard rule).** For each live criterion that
   needs non-default data, climb this ladder; do not skip steps. Start the
   canonical driver and log **before** seeding (see Evidence ledger below).

   1. **Fixtures / setup-notes** — use what load-fixtures and setup-notes
      already provide (IDs, auth, facility).
   2. **UI-create** — if an entity is missing, **execute** the numbered Data
      setup steps in `qa-plan.md` until a concrete visible error. Opening or
      inspecting a form, or calling the graph “impractical,” does **not**
      count as a UI attempt. Use unique synthetic names (never real patient
      data). For terminology-backed fields, use the UI picker or its valueset
      expansion route — never invent LOINC/SNOMED/code strings.
   3. **API seed escape hatch** — only when `qa-plan` marks a deep graph
      (dependent entity types / multi-page settings — **not** click count)
      **or** UI create failed with a recorded error. Facility-scoped
      fetch/`request` only, then open the UI and confirm the entity is
      visible before scoring.
      - Prefer paths and bodies already pasted in `qa-plan` Data setup.
      - If a planned API body returns **4xx**, retry once from a known-working
        `tests/**` helper / `beforeAll` / `apiSetup` payload before declaring
        a data wall. A proven plan payload rejected by validation is
        `validation-error`, **not** automatically `missing-test-data`.
      - If paths are missing: run the thin discovery recipe below. Never invent
        BE/Django URLconf names or unscoped `/api/v1/<resource>/` routes.
      - Auth: `getApiUrl` + `getApiHeaders` from `tests/helper/utils.ts`
        and `tests/.auth/user.json` (see setup-notes). On `token_not_valid` /
        expired → **mid-session token recovery** below before `auth-failure`.
   4. **Only then** `not-exercised` + `missing-test-data` (or
      `missing-permission` / `missing-facility-context` for true walls).

   Ban weak excuses: claiming API blocked after calling unscoped routes;
   claiming “exceeds time budget” without a concrete failed UI/API attempt;
   jumping straight to `missing-test-data` when fixtures or UI create could
   supply the entity; assessing complexity instead of executing numbered
   steps.

   When reporting `missing-test-data`, fill `seed_attempt` honestly in
   `qa-report.json` (`method`: `ui` | `api` | `both` | `none`, plus a
   `summary` of what was tried — routes/entities/errors). Do not use
   `method: none` or an empty summary after claiming you could not seed.
   `plan_steps_run` must name each seed/live step actually executed —
   **empty `plan_steps_run` cannot accompany `missing-test-data`**.

   Exercise criteria **independently** when their fixtures exist, even if
   sibling criteria remain blocked on a seed graph.

4. **Execute live criteria one-by-one with Playwright.** Default evidence is
   **video** (`recordVideo`). For each live-flow criterion, write one isolated
   driver, run it alone, wait for exit, then move on — never parallel workers
   or a shared recording across ACs. Canonical clip path:
   `specs/{ticket}/videos/{id}.webm` (basename **must** equal the criterion
   `id` from `qa-report.json`). Before driving each recorded flow, enable the
   native cursor/click overlay:
   `await page.screencast.showActions({ cursor: "pointer" })`
   (Playwright ≥ 1.61). Do not invent a custom DOM cursor. Optional stills
   only when the Evidence media policy (injected above) has
   `screenshots: true`, or as extras that do not count for pass. Prefer
   `getByRole` / exact i18n labels from the plan's research map — never
   invent button names.
5. **Validate success signals** from the plan (toast, URL, visible state).
6. **Write `qa.md` + `qa-report.json`.** Live evidence is primary; code
   inspection belongs only in notes / Limits — never as a `pass`.

### Auth shell readiness (hard gate — ticket 19)

Before any facility-scoped criterion, prove an authenticated **app shell**.
CARE can leave the browser on `/facility/.../overview` while rendering the
login PublicRouter when `currentUser` fails silently — **URL without
`/login` is not proof of auth.**

1. Load `storageState` from setup-notes (`tests/.auth/user.json` or role file).
2. Set **viewport** to the same object as `recordVideo.size` from setup-notes
   (care_fe: `{ width: 1440, height: 900 }`). Sidebar is `md+`; avoid mobile
   sheet-only. **Ban:** `recordVideo.size` set with a smaller or default
   viewport (Playwright letterboxes grey padding).
3. Navigate to a facility route from setup-notes / `getFacilityId()`.
4. Wait until **all** of:
   - loading spinner gone
   - at least one known facility nav label visible (e.g. Overview / Patients),
     **or** `[data-sidebar="sidebar"]` visible on desktop
5. Also probe for login UI (`Username` / `Password` / Sign in). If present
   while the URL is still a facility path → treat as auth failure and run
   **mid-session token recovery** (fresh UI login) before scoring.

**Ban:** treating “URL has no `/login`” or “title is CARE” as proof of auth.

Blocker taxonomy:

- Shell never authenticates after storageState + refresh + fresh login →
  `auth-failure`
- Authenticated shell present but expected nav/control missing →
  `navigation-mismatch` (or fail the AC), **not** `auth-failure`
- Expired access token on API seed **without** a refresh attempt → dishonest;
  log must show the refresh try

### Mid-session token recovery (ticket 20 — refresh, do not surrender)

Node seed scripts that read a static `care_access_token` from
`tests/.auth/user.json` do **not** auto-refresh. Filing `auth-failure` on the
first `token_not_valid` / “Token is expired” is **banned**.

Ordered recovery before any `auth-failure`:

1. **Refresh JWT** — `POST /api/v1/auth/token/refresh/` with
   `care_refresh_token` from the same storageState; write new access/refresh
   back into `tests/.auth/user.json` (or an in-memory header helper for the
   rest of the run). Retry the failed API call once. Log status codes, not
   secrets.
2. **If refresh fails** — UI login with fixture credentials; persist a fresh
   storageState (Playwright `storageState` save or rewrite the auth JSON);
   re-check authenticated shell; retry seed/API.
3. **Prefer UI continuation** when the browser context is still authenticated
   even if a seed script’s file token expired — do not abandon live criteria
   solely because a Node `fetch` used a stale header.
4. **Only then** `not-exercised` + `auth-failure`, with log proof that refresh
   and re-login were attempted.

Ban cascading sibling ACs as `auth-failure` without attempting recovery once.

### Thin discovery cookbook (how to find things — not a CARE encyclopedia)

Before inventing selectors or payloads:

1. Prefer pasted **Data setup** in `qa-plan.md` (exact UI steps + paths +
   proven bodies).
2. Then `tests/PLAYWRIGHT_GUIDE.md` + `rg` under `tests/` for helpers,
   `beforeAll`, `apiSetup`, and terminology constants.
3. Then `src/types/**/*Api.ts` for create paths (**verbatim**).
4. Valueset-backed codes via UI picker / expand API — never invent LOINC
   strings.
5. Auth shell probes (section above).

### API route discovery (fallback when qa-plan omitted a path)

1. Name the entity to create (e.g. Activity Definition, Specimen Definition,
   Service Request).
2. In the FE worktree, find the matching file under `src/types/**/` — usually
   `*Api.ts` next to the domain type. Grep example:
   `rg -n "activity_definition|/facility/\{facilityId\}" src/types --glob '*Api.ts'`.
3. Open that file; use the create route entry. Copy the `path` string
   **verbatim** (e.g. `/api/v1/facility/{facilityId}/activity_definition/`).
4. Resolve path params from setup-notes / fixtures (`facilityId`, …) — never
   drop the facility segment.
5. Prefer body from a known-working `tests/**` helper; else nearby types /
   create form. Do not guess unscoped top-level routes.
6. Ban: inventing `/api/v1/<resource>/` without `{facilityId}`.

## Automated suite / CI is out of scope

Agent QA does **not** plan, run, or score the repository's Playwright E2E
suite or CI checks. That belongs to implement + CI.

- Prefer **omitting** suite/CI items from `qa-report.json` criteria entirely.
- If such an item still appears in the handed `qa-plan.md`, mark it
  `not-exercised` with a clear out-of-scope note — never `pass`.
- Never invent a live `pass` by reading test files or source
  (`pass` + `code-inspection` is rejected by collect; do not attempt it).
- Reading `tests/**` for **seed recipes / helpers** is encouraged; scoring
  suite green as agent-QA pass is not.

## The app is already running

If the repository configured a setup command, it has already installed
dependencies, started services and loaded fixtures — see the Environment
section above and `.agent-hq/setup-notes.md`. **Do not stand anything up
yourself**, and never point the app at a non-localhost API: a real deployment
holds real patient data, and nothing here may touch it. Synthetic fixtures
only.

If the environment is not there — no setup was configured for this repo, or
it left less than you need — **do not fake a pass** and do not spend the run
building one by hand. Capture whatever you can reach, mark the rest
`not-exercised` with a classified blocker, and say plainly in `qa.md` what
was missing.

## Where your files go

**Scratch goes under `.agent-hq/`** — temp pages, downloaded data, and anything
else that is not a declared ledger output. That directory never reaches the
work repo. Anything you leave elsewhere (except the paths below) lands in the
pull request.

Declared ledger outputs under `specs/{ticket}/` (collected; kept out of the
work-repo patch because `writes_code: false`):

- drivers → `specs/{ticket}/qa-drivers/{id}.mjs` (one file per criterion `id`)
- run logs → `specs/{ticket}/qa-logs/{id}.log` (stdout/stderr for that driver)
- videos → `specs/{ticket}/videos/{id}.webm` (basename **must** equal `id`)
- screenshots → `specs/{ticket}/screenshots/<short-slug>.png` (optional unless
  the media policy disables video)
- report → `specs/{ticket}/qa.md` and `specs/{ticket}/qa-report.json`

You write WebM only. Collect may derive a sibling lite `.gif` for the PR
comment embed — do not spend the run producing GIFs yourself.

Do not commit anything.

## Serial, one isolated driver per criterion

Run criteria **strictly one after another**. Forbidden:

- `npx playwright test` over a folder with default workers
- `fullyParallel` / multi-file suites in one invocation
- backgrounding multiple drivers
- one shared browser context or one long recording across ACs
- manually renaming or reassigning opaque `recordVideo` clips between ids

Allowed: `node specs/{ticket}/qa-drivers/{id}.mjs` (or equivalent) for a
**single** id, wait for exit, then the next id. If you must use the Playwright
test runner for one file, force `--workers=1` and never pass more than that
one file.

### Evidence ledger (start before seeding)

For each live-flow criterion — including ones that may end `not-exercised`:

1. Write **one** driver at `specs/{ticket}/qa-drivers/{id}.mjs` (plain Node +
   Playwright API preferred over the test runner; `id` from `qa-report.json`)
   **before** seeding. Preserve the executable attempt even when the criterion
   ends `not-exercised`; references to discarded `.agent-hq/` scratch scripts
   do **not** count as evidence.
2. Redirect that driver's stdout/stderr to `specs/{ticket}/qa-logs/{id}.log`
   (non-empty for any attempted non-pass). Append every attempted action:
   fixture lookup, UI URL and step, form submission/result, API
   method/path/status plus redacted response/error, auth refresh/re-login
   status codes, and the final verification checkpoint. Keep secrets and
   patient data out.
3. That script alone opens a context with `recordVideo` when driving the UI,
   with **viewport === `recordVideo.size`** (care_fe / setup-notes:
   `{ width: 1440, height: 900 }` via a shared `size` object). **Ban:**
   setting video size while leaving viewport smaller or at Playwright's
   default — that grey-letterboxes the evidence. Then call
   `page.screencast.showActions({ cursor: "pointer" })`, run **only**
   that criterion's seed + steps, then **close the page/context** (flushes
   WebM).
4. Move/copy the finished clip (when recorded) to exactly
   `specs/{ticket}/videos/{id}.webm`.

`qa.md` / `qa-report.json` video paths must be that same
`specs/{ticket}/videos/{id}.webm`. Never share one recording across ACs.

## Live-flow evidence (not code inspection)

For each user-facing acceptance criterion, drive the **running application**
through the plan's steps and record the interaction.

This means the real app, at its real route, in a browser signed in with the
session the setup step left you. A reviewer must recognise the product in the
recording; if it could be any web page, it is not evidence.

Enable Playwright `recordVideo` on the browser context (respect
`video_max_seconds` from the media policy). Set `viewport` to the **same**
size as `recordVideo.size` (care_fe / setup-notes: 1440×900). Do not record
with video size set and a smaller or default viewport — mismatched sizes
cause grey letterboxing. On each page used for a clip, call
`page.screencast.showActions({ cursor: "pointer" })` **before** the
interactions so the recording (and any derived GIF) shows pointer and clicks.
One clip per criterion is enough when it includes the interactions the plan
marked **Record through**.

Do **not**, under any circumstances:

- build a standalone HTML page, harness, story, or demo and treat that as pass
- mark `pass` because the research map / source code "looks correct"
- reimplement the spec's rules in your own script and verify the reimplementation

Those prove only that you can restate the spec. Code inspection may appear
under a **Code inspection** note or in `## Limits` — it never yields `pass`.

If you cannot reach the real page — after climbing the seed ladder
(fixtures → UI-create → facility-scoped API escape) for missing localhost
entities, a flow you cannot complete, a role you do not have, video capture
fails — that criterion is `not-exercised` or `fail` with a blocker category
from the list below. That is a perfectly good outcome. A substitute render
is not.

Small recovery is allowed (one alternate visible control). Rewriting the
journey from scratch is not a `pass` path.

### Blocker categories

Use exactly one of: `app-not-loading` | `auth-failure` |
`missing-facility-context` | `missing-permission` | `missing-test-data` |
`navigation-mismatch` | `video-failure` | `screenshot-failure` |
`validation-error` | `emulator-limit` | `device-limit` | `no-qa-plan` | `other`

### Honesty rules the engine also enforces

- `pass` ⇒ `evidence_kind: live-flow` + video path exactly
  `specs/{ticket}/videos/{id}.webm` in the ledger (default), plus matching
  `qa-drivers/{id}.mjs` and non-empty `qa-logs/{id}.log`. Each video path
  may back at most one criterion. Stills never required for pass unless video
  is disabled in config.
- Non-live `evidence_kind` (including `code-inspection`) ⇒ never `pass`.
  Collect rejects `pass` + `code-inspection`; do not attempt it.
- Summary cannot claim `all_passed` if any `fail` / `not-exercised`.
- If video capture fails → `not-exercised` / `fail` with `video-failure`, not
  a code-inspection `pass`.
- Suite/CI coverage items are not live ACs — omit or `not-exercised`; never
  score them as pass via code inspection.
- `missing-test-data` ⇒ fill `seed_attempt` honestly (`method` + `summary`
  of the UI/API attempts), non-empty `plan_steps_run`, and keep the attempt in
  canonical `qa-drivers/{id}.mjs` + non-empty `qa-logs/{id}.log`. Do not claim
  seed was impossible after only unscoped API calls or with no concrete
  attempt.
- Attempted `fail` / `not-exercised` with non-empty `plan_steps_run` ⇒
  canonical driver + non-empty aggregate log (fixture/UI/API/auth transcript).
- A proven qa-plan API body rejected with 4xx after test-payload retry ⇒
  `validation-error`, not disguised `missing-test-data`.

## Write `specs/{ticket}/qa.md`

Group criteria under clear headings. Prefer separate sections:

- `## Live-flow` — criteria you drove in the running app
- `## Code inspection` — notes only; no passes here
- `## Emulator-browser` / `## Real-device` — when those limits apply
- `## Limits` — what you could not exercise, and why

One subsection per acceptance criterion, each with:

- the verdict — `pass`, `fail`, or `not-exercised` (with reason + category)
- what you actually did (plan steps run, briefly)
- the video, linked with a **repo-relative** markdown link whose basename is
  the criterion id — **alone on its own line**, with no `**Evidence**:` /
  `**Video**:` prefix and no wrapping `<details>` (collect owns the collapsed
  preview when a sibling `.gif` exists):
  `[dropdown open — desktop](specs/{ticket}/videos/dropdown.webm)`
- optional screenshot embeds only when stills were taken:
  `![…](specs/{ticket}/screenshots/….png)`

Keep those links repo-relative. The engine rewrites them to ledger URLs when
it posts this file as a PR comment — WebM links with a sibling `.gif` in the
ledger become a **blockquoted** collapsed `<details>` preview labelled
`Video:`; missing GIF degrades to the WebM link alone. Do not wrap, prefix,
or blockquote the links yourself.

Every media path you link must be a file you actually saved.

## Write `specs/{ticket}/qa-report.json`

Required structured twin of `qa.md`. Shape:

Omit `seed_attempt` unless `missing-test-data` (then require `{method, summary}` with method ≠ none).

```json
{
  "criteria": [
    {
      "id": "short-slug",
      "title": "...",
      "verdict": "pass|fail|not-exercised",
      "evidence_kind": "live-flow|code-inspection|emulator-limit|device-limit|unreachable",
      "blocker": null,
      "blocker_category": null,
      "plan_steps_run": ["1", "2"],
      "videos": ["specs/{ticket}/videos/short-slug.webm"],
      "screenshots": []
    }
  ],
  "summary": {
    "all_passed": false,
    "pass": 0,
    "fail": 0,
    "not_exercised": 0
  }
}
```

Collect validates this against the schema and media policy. A dishonest
report fails the run (retry) — it is never posted as a greenwashed PR comment.

## Decide what runs next (see Control output below)

Always queue `finalize`, forwarding `specs/{ticket}/spec.md`,
`specs/{ticket}/review.md`, and `specs/{ticket}/qa.md`. That holds even when
nothing user-facing changed (write `qa.md` / `qa-report.json` saying so, with
empty media dirs) and when criteria failed — `qa` reports, it does not gate.
Note any failure prominently at the top of `qa.md` so the human merging the
PR sees it.

Cap the whole pass at 45 minutes. If the install or build eats that budget,
stop, write what you have with `not-exercised` verdicts, and queue finalize —
a partial honest QA is a valid outcome, a timed-out run is not.
