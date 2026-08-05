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
2. **Open the real app.** Start from `.agent-hq/setup-notes.md` (preview URL,
   `tests/.auth/*.json`). Verify the session, then facility context when the
   plan marks a flow facility-scoped. Missing facility → `not-exercised` /
   `missing-facility-context`.
3. **Execute steps with Playwright.** Default evidence is **video**
   (`recordVideo`); copy finished clips into
   `specs/{ticket}/videos/<short-slug>.webm`. Optional stills only when the
   Evidence media policy (injected above) has `screenshots: true`, or as
   extras that do not count for pass. Prefer `getByRole` / exact i18n labels
   from the plan's research map — never invent button names.
4. **Validate success signals** from the plan (toast, URL, visible state).
5. **Write `qa.md` + `qa-report.json`.** Live evidence is primary; code
   inspection belongs only in notes / Limits — never as a `pass`.

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

**Everything you create except evidence media goes under `.agent-hq/`** —
driver scripts, throwaway fixtures, temp pages, downloaded data, all of it.
That directory never reaches the work repo. Anything you leave anywhere else
lands in the pull request.

Evidence media is the exception:

- videos → `specs/{ticket}/videos/<short-slug>.webm` (default; required for pass)
- screenshots → `specs/{ticket}/screenshots/<short-slug>.png` (optional unless
  the media policy disables video)

Do not commit anything.

## Live-flow evidence (not code inspection)

For each user-facing acceptance criterion, drive the **running application**
through the plan's steps and record the interaction.

This means the real app, at its real route, in a browser signed in with the
session the setup step left you. A reviewer must recognise the product in the
recording; if it could be any web page, it is not evidence.

Enable Playwright `recordVideo` on the browser context (respect
`video_max_seconds` from the media policy). One clip per criterion is enough
when it includes the interactions the plan marked **Record through**.

Do **not**, under any circumstances:

- build a standalone HTML page, harness, story, or demo and treat that as pass
- mark `pass` because the research map / source code "looks correct"
- reimplement the spec's rules in your own script and verify the reimplementation

Those prove only that you can restate the spec. Code inspection may appear
under a **Code inspection** note or in `## Limits` — it never yields `pass`.

If you cannot reach the real page — route needs data you cannot create, a
flow you cannot complete, a role you do not have, video capture fails — that
criterion is `not-exercised` or `fail` with a blocker category from the list
below. That is a perfectly good outcome. A substitute render is not.

Small recovery is allowed (one alternate visible control). Rewriting the
journey from scratch is not a `pass` path.

### Blocker categories

Use exactly one of: `app-not-loading` | `auth-failure` |
`missing-facility-context` | `missing-permission` | `missing-test-data` |
`navigation-mismatch` | `video-failure` | `screenshot-failure` |
`validation-error` | `emulator-limit` | `device-limit` | `no-qa-plan` | `other`

### Honesty rules the engine also enforces

- `pass` ⇒ `evidence_kind: live-flow` + ≥1 video path that reached the ledger
  (default). Stills never required for pass unless video is disabled in
  config.
- Non-live `evidence_kind` ⇒ never `pass`.
- Summary cannot claim `all_passed` if any `fail` / `not-exercised`.
- If video capture fails → `not-exercised` / `fail` with `video-failure`, not
  a code-inspection `pass`.

## Write `specs/{ticket}/qa.md`

Group criteria under clear headings. Prefer separate sections:

- `## Live-flow` — criteria you drove in the running app
- `## Code inspection` — notes only; no passes here
- `## Emulator-browser` / `## Real-device` — when those limits apply
- `## Limits` — what you could not exercise, and why

One subsection per acceptance criterion, each with:

- the verdict — `pass`, `fail`, or `not-exercised` (with reason + category)
- what you actually did (plan steps run, briefly)
- the video, linked with a **repo-relative** markdown link:
  `[dropdown open — desktop](specs/{ticket}/videos/dropdown-desktop.webm)`
- optional screenshot embeds only when stills were taken:
  `![…](specs/{ticket}/screenshots/….png)`

Keep those links repo-relative. The engine rewrites them to ledger URLs when
it posts this file as a PR comment.

Every media path you link must be a file you actually saved.

## Write `specs/{ticket}/qa-report.json`

Required structured twin of `qa.md`. Shape:

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
      "videos": ["specs/{ticket}/videos/….webm"],
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
