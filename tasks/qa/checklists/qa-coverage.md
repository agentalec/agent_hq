# QA coverage checklist

Before finishing `specs/{ticket}/qa.md` and `specs/{ticket}/qa-report.json`,
confirm:

- [ ] Every **live** user-facing acceptance criterion in `spec.md` /
      `qa-plan.md` has its own section with a verdict — `pass`, `fail`, or
      `not-exercised` plus the reason and a `blocker_category`. Suite/CI /
      "Playwright tests must pass" items are out of agent-QA scope — omit
      them from the report, or mark `not-exercised` with an out-of-scope note;
      never score them as `pass` via code inspection.
- [ ] You executed `qa-plan.md` (or marked `no-qa-plan` / `not-exercised`).
      Facility-scoped flows verified a facility context first.
- [ ] You preferred fixtures / setup-notes auth. For missing localhost
      entities a criterion needs, you created them via the UI with unique
      synthetic names **before** using `missing-test-data`. Only after a
      failed create (or a true permission / facility wall) did you mark
      `not-exercised` + `missing-test-data` / `missing-permission` /
      `missing-facility-context`.
- [ ] Criteria ran **serially**, one isolated driver at a time. No parallel
      Playwright workers, no multi-file suite in one invocation, no shared
      browser context or shared recording across ACs. You did not run the
      repo's E2E suite as agent-QA evidence.
- [ ] Every `pass` is `evidence_kind: live-flow` with video exactly
      `specs/{ticket}/videos/{id}.webm` (basename = criterion `id`), linked
      repo-relatively from `qa.md` and listed in `qa-report.json`. Matching
      `specs/{ticket}/qa-drivers/{id}.mjs` and non-empty
      `specs/{ticket}/qa-logs/{id}.log` are present. Code inspection alone
      never backs a `pass` (engine rejects `pass` + `code-inspection`).
- [ ] **Every recording is the real application.** Could a reviewer tell this
      is the product? Page chrome — navigation, header, surrounding layout —
      has to be visible. A harness, story, demo page, or reimplementation of
      the spec is not evidence.
- [ ] Before driving each recorded flow you called
      `page.screencast.showActions({ cursor: "pointer" })` so clicks and the
      pointer are visible in the WebM (no custom DOM cursor overlay).
- [ ] You never manually reassigned opaque `recordVideo` clips between
      criterion ids.
- [ ] Screenshots (if any) are optional extras unless the media policy has
      `video: false`; they never substitute for video when video is on.
- [ ] `qa-report.json` summary counts match the criteria; `all_passed` is
      false whenever any criterion is `fail` or `not-exercised`.
- [ ] Nothing you created lives outside `.agent-hq/` — except declared ledger
      paths under `specs/{ticket}/`: `qa.md`, `qa-report.json`, `videos/`,
      `screenshots/`, `qa-drivers/`, and `qa-logs/`. Check with `git status`.
- [ ] No test data resembles real patients — synthetic fixtures only, and the
      app was never pointed at a non-localhost API.
- [ ] Anything you could not reach is named in `## Limits` as
      `not-exercised`, not silently reported as a pass.
- [ ] Any failing criterion is called out at the top of `qa.md`.
