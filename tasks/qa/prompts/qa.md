# QA prompt

Read `constitution.md`, `specs/{ticket}/spec.md`, and `specs/{ticket}/review.md`.
Your worktree is already checked out at the implemented branch — the code
under test is there, and you have Bash, Node 22, and Docker.

## Stand the app up

Use the repo's own tooling to install and run it (`package.json` scripts,
`Makefile`, `README`, `docker-compose.yml`). Synthetic fixtures only — never
real patient data.

If the app needs a backend you cannot stand up, **do not fake a pass**. In
order of preference: mock at the network boundary, use whatever
component/story/route-level harness the repo already has, or fall back to
screenshotting the component in isolation. Whatever you end up doing, say so
plainly in `qa.md` — an honest "could not exercise the live queue board,
screenshotted the component with mocked props" is worth more than a green
tick that means nothing.

## Screenshot every user-facing change

Install the browser once, then drive the UI:

```bash
npx playwright install --with-deps chromium
```

For each user-facing acceptance criterion in `spec.md`, navigate to the state
it describes and capture a screenshot. Save each PNG to
`qa-screenshots/{ticket}/<short-slug>.png` and commit it — that path is
work-repo code, so it lands on the PR branch with your other changes.

If the ticket touches responsive behavior, capture both viewports: desktop
1440x900 and mobile 390x844, suffixed `-desktop` / `-mobile`.

Screenshot the state **after** the interaction the criterion describes, not
just the page it starts on — a dropdown criterion wants the dropdown open.

## Write `specs/{ticket}/qa.md`

One `## <criterion>` section per acceptance criterion, each with:

- the verdict — `pass`, `fail`, or `not-exercised` (with the reason)
- what you actually did to reach that state (the steps, briefly)
- the screenshot, embedded with a **repo-relative** markdown image link:
  `![service point dropdown — mobile](qa-screenshots/{ticket}/dropdown-mobile.png)`

Keep those links repo-relative. The engine rewrites them to raw URLs pinned
to the commit you landed when it posts this file as a PR comment — an
absolute URL you write yourself will not survive that.

Finish with a `## Limits` section: what you could not exercise, and why.

Cap the whole pass at 45 minutes. If the install or build eats that budget,
stop, write what you have with `not-exercised` verdicts, and hand off — a
partial honest QA is a valid outcome, a timed-out run is not.

## Decide the handoff (see Control output below)

Always hand off to `finalize`, forwarding `specs/{ticket}/spec.md`,
`specs/{ticket}/review.md`, and `specs/{ticket}/qa.md`. That holds even when
nothing user-facing changed (write `qa.md` saying so, with no screenshots)
and when criteria failed — `qa` reports, it does not gate. Note any failure
prominently at the top of `qa.md` so the human merging the PR sees it.
