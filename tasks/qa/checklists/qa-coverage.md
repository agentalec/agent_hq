# QA coverage checklist

Before finishing `specs/{ticket}/qa.md`, confirm:

- [ ] Every user-facing acceptance criterion in `spec.md` has its own section
      with a verdict — `pass`, `fail`, or `not-exercised` plus the reason.
- [ ] Every `pass` verdict has a screenshot backing it, committed under
      `specs/{ticket}/screenshots/` and embedded with a repo-relative link.
- [ ] Screenshots show the state *after* the interaction, and both viewports
      where the ticket touches responsive behavior.
- [ ] No test data resembles real patients — synthetic fixtures only.
- [ ] Anything you could not stand up is named in `## Limits`, not silently
      reported as a pass.
- [ ] Any failing criterion is called out at the top of the file.
