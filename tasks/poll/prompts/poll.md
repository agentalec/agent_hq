# Poll prompt

Read the `poll:*`-tagged open question this task was enqueued for in
`specs/{ticket}/spec.md`.

Frame it as ONE decision question, phrased neutrally -- no leading option.
List at most 8 mutually exclusive options (the GitHub reaction set limit).

Record in `specs/{ticket}/decisions.md`:
- The question and its options.
- The quorum rule (default: at least 3 votes) and the deadline (24 working
  hours).
- Once resolved: the binding decision and the final tally.

Fold the resolved decision back into the open-questions section of
`specs/{ticket}/spec.md`, replacing the `[open]` tag with the outcome.
