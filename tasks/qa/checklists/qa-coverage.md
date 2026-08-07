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
- [ ] **Discovery consulted** before inventing selectors/payloads: qa-plan
      Data setup → `tests/PLAYWRIGHT_GUIDE.md` → `rg` under `tests/` for
      helpers/`beforeAll`/`apiSetup` → `src/types/**/*Api.ts` (verbatim
      paths). Valueset codes via UI picker / expand API — never invent LOINC.
- [ ] You preferred fixtures / setup-notes auth, then climbed the seed
      ladder before `missing-test-data`: (1) fixtures/setup-notes,
      (2) **executed** numbered UI Data setup steps until a concrete visible
      error (inspecting a form ≠ attempt), (3) facility-scoped API escape
      only when the plan marks a deep graph or UI create failed — prefer
      paths/bodies in qa-plan; on 4xx retry from a known-working test/helper
      payload (proven plan body → `validation-error`, not automatic
      `missing-test-data`); else discover from `*Api.ts` (never invent
      unscoped BE routes), (4) only then `not-exercised` +
      `missing-test-data` / `missing-permission` /
      `missing-facility-context`. Ban: unscoped API “blocked” claims or
      “exceeds budget” without a concrete failed UI/API attempt.
- [ ] Fixture-independent criteria were exercised independently even when a
      sibling seed graph stayed blocked.
- [ ] **Auth shell readiness** passed before facility criteria: storageState
      loaded, viewport matches `recordVideo.size` (care_fe: 1440×900; no grey
      letterboxing), spinner gone, facility nav label or
      `[data-sidebar="sidebar"]` visible. Ban: URL without `/login` or title
      “CARE” as auth proof. Login UI on a facility URL ⇒ auth failure path.
- [ ] **Auth recovery** on `token_not_valid` / expired: JWT refresh via
      `/api/v1/auth/token/refresh/` rewriting storageState, else UI re-login;
      prefer browser continuation if file token is stale. Ban: `auth-failure`
      without recovery attempt, or cascading siblings without one recovery.
- [ ] Criteria ran **serially**, one isolated driver at a time. No parallel
      Playwright workers, no multi-file suite in one invocation, no shared
      browser context or shared recording across ACs. You did not run the
      repo's E2E suite as agent-QA evidence.
- [ ] Canonical `qa-drivers/{id}.mjs` and `qa-logs/{id}.log` were started
      **before** seeding; attempts (fixture/UI/API/auth/verify) are appended
      to the log. Scratch under `.agent-hq/` does not count as evidence.
- [ ] Every `pass` is `evidence_kind: live-flow` with video exactly
      `specs/{ticket}/videos/{id}.webm` (basename = criterion `id`), linked
      repo-relatively from `qa.md` and listed in `qa-report.json`. Matching
      `specs/{ticket}/qa-drivers/{id}.mjs` and non-empty
      `specs/{ticket}/qa-logs/{id}.log` are present. Code inspection alone
      never backs a `pass` (engine rejects `pass` + `code-inspection`).
- [ ] Attempted non-pass (`fail` / `not-exercised` with work tried) has
      non-empty `plan_steps_run` naming each seed/live step executed, plus
      non-empty ledger log. `missing-test-data` never ships with empty
      `plan_steps_run` or empty/missing driver+log; fill `seed_attempt`
      honestly (`method` ≠ `none`).
- [ ] **Every recording is the real application.** Could a reviewer tell this
      is the product? Page chrome — navigation, header, surrounding layout —
      has to be visible. A harness, story, demo page, or reimplementation of
      the spec is not evidence.
- [ ] Before driving each recorded flow you called
      `page.screencast.showActions({ cursor: "pointer" })` so clicks and the
      pointer are visible in the WebM (no custom DOM cursor overlay).
- [ ] **Viewport matches `recordVideo.size`** (shared size object; care_fe
      1440×900). Ban: video size set with a smaller/default viewport (grey
      letterboxing in evidence).
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
