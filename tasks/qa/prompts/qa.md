# QA prompt

Read `constitution.md`, `specs/{ticket}/spec.md`, and `specs/{ticket}/plan.md`.

Stand up the target stack per the repo's `repos.yml` CI budget, using
synthetic fixtures only. Run Playwright on headless Chromium.

Write at least one integration test per user-facing Given/When/Then
acceptance criterion in `spec.md`. Commit new tests into the target repo's
own test suite -- not a scratch directory.

Record the criterion-to-test mapping in `specs/{ticket}/qa.md`.

Keep the smoke suite runtime at or under 10 minutes. If a test fails, retry
it once; if it still fails, mark it `flaky` rather than blocking on it.
Capture traces/screenshots/videos for any test failure and reference them from
`qa.md`.
