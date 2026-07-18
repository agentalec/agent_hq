# Spec quality checklist

Before finishing `specs/{ticket}/spec.md`, confirm:

- [ ] Every acceptance criterion is testable -- a reviewer could write a
      test from it alone.
- [ ] Acceptance criteria are phrased as Given/When/Then.
- [ ] Capability notes name real files, functions, or endpoints already in
      the repo, not assumptions about what "probably" exists.
- [ ] Every open question is tagged `[open]` and states who/what resolves it.
- [ ] No acceptance criterion depends on an unresolved open question.
