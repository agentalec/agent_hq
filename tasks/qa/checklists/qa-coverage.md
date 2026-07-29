# QA coverage checklist

Before finishing `specs/{ticket}/qa.md`, confirm:

- [ ] Every user-facing acceptance criterion in `spec.md` has its own section
      with a verdict — `pass`, `fail`, or `not-exercised` plus the reason.
- [ ] Every `pass` verdict has a screenshot backing it, saved under
      `specs/{ticket}/screenshots/` and embedded with a repo-relative link.
- [ ] **Every screenshot is the real application.** Open each one and ask:
      could a reviewer tell this is the product? The page chrome — navigation,
      header, surrounding layout — has to be visible. A cropped element on a
      blank background, or any page you generated yourself, is not evidence
      and must not back a `pass`.
- [ ] No screenshot came from a harness, story, demo page, or a
      reimplementation of the spec's logic.
- [ ] Screenshots are full-page, show the state *after* the interaction, and
      cover both viewports where the ticket touches responsive behavior.
- [ ] Nothing you created lives outside `.agent-hq/` — except the screenshots.
      Check with `git status`: anything else untracked would land in the PR.
- [ ] No test data resembles real patients — synthetic fixtures only, and the
      app was never pointed at a non-localhost API.
- [ ] Anything you could not reach is named in `## Limits` as
      `not-exercised`, not silently reported as a pass.
- [ ] Any failing criterion is called out at the top of the file.
