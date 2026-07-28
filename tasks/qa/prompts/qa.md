# QA prompt

Read `constitution.md`, `specs/{ticket}/spec.md`, and `specs/{ticket}/review.md`.
Your worktree is already checked out at the implemented branch — the code
under test is there, and you have Bash, Node 22, and Docker.

## The app is already running

If the repository configured a setup command, it has already installed
dependencies, started services and loaded fixtures — see the Environment
section above and `.agent-hq/setup-notes.md`. **Do not stand anything up
yourself**, and never point the app at a non-localhost API: a real deployment
holds real patient data, and nothing here may touch it. Synthetic fixtures
only.

If the environment is not there — no setup was configured for this repo, or
it left less than you need — **do not fake a pass** and do not spend the run
building one by hand. Screenshot whatever you can reach, mark the rest
`not-exercised` with the reason, and say plainly in `qa.md` what was missing.
An honest "the queue board needs a backend this repo has no setup command
for" is worth more than a green tick that means nothing, and it tells the
operator exactly which command to add.

## Screenshot every user-facing change

For each user-facing acceptance criterion in `spec.md`, navigate to the state
it describes and capture a screenshot. Save each PNG to
`specs/{ticket}/screenshots/<short-slug>.png`. That directory is a declared
output, so the engine collects whatever you leave there — you do not need to
commit them, and they deliberately stay out of the work repo, which is for
product code only.

If the ticket touches responsive behavior, capture both viewports: desktop
1440x900 and mobile 390x844, suffixed `-desktop` / `-mobile`.

Screenshot the state **after** the interaction the criterion describes, not
just the page it starts on — a dropdown criterion wants the dropdown open.

## Write `specs/{ticket}/qa.md`

One `## <criterion>` section per acceptance criterion, each with:

- the verdict — `pass`, `fail`, or `not-exercised` (with the reason)
- what you actually did to reach that state (the steps, briefly)
- the screenshot, embedded with a **repo-relative** markdown image link:
  `![service point dropdown — mobile](specs/{ticket}/screenshots/dropdown-mobile.png)`

Keep those links repo-relative. The engine rewrites them to their ledger URLs
when it posts this file as a PR comment — an absolute URL you write yourself
will not survive that.

Every image you embed must be a file you actually saved. The engine checks
each one against what reached the ledger and replaces any it cannot find with
a visible "missing screenshot" note, so a link to a PNG you never wrote is
worse than no link at all: it advertises a screenshot that does not exist.

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
