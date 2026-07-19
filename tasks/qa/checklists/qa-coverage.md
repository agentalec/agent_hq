# QA coverage checklist

Before finishing `specs/{ticket}/qa.md`, confirm:

- [ ] Every user-facing Given/When/Then acceptance criterion in `spec.md`
      maps to at least one integration test.
- [ ] No test data resembles real patients -- synthetic fixtures only.
- [ ] The smoke suite runtime is at or under 10 minutes.
- [ ] The retry-once-then-flaky policy was applied to any failing test,
      not silently skipped.
- [ ] Failure artifacts (traces/screenshots/videos) are captured and referenced
      for any test that failed.
