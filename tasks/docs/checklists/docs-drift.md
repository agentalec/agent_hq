# Docs drift checklist

Before finishing `specs/{ticket}/docs.md`, confirm:

- [ ] The docs written match `spec.md` -- no contradicted acceptance
      criterion.
- [ ] The docs written match the shipped tests -- no described behavior
      the tests don't exercise.
- [ ] Any detected drift was reported in `docs.md` and left unresolved
      rather than silently reconciled.
- [ ] A changelog entry was added for the change.
- [ ] Docs live under the target repo's own `docs/` directory, not
      `specs/{ticket}/`.
