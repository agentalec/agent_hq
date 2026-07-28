# Spec quality checklist

Before finishing `specs/{ticket}/spec.md`, confirm:

- [ ] Every acceptance criterion is testable -- a reviewer could write a
      test from it alone.
- [ ] Acceptance criteria are phrased `Given X, when Y, then Z.`, one line
      each, at most 7 of them.
- [ ] Capability notes name real files, functions, or endpoints already in
      the repo, not assumptions about what "probably" exists -- a path per
      bullet, not a paragraph.
- [ ] Every open question is tagged `[open]`, states who/what resolves it,
      and blocks an acceptance criterion. Non-blocking ones are cut.
- [ ] No acceptance criterion depends on an unresolved open question.
- [ ] Under 400 words, and no section restates another.
