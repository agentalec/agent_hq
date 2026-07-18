# `poll` (`engine.ports.Poll`)

Protocol only in P0 (D3) -- no adapter ships until P1
(`github-issue-reactions`).

## Ops

- `open(question, options, audience) -> poll_ref` -- open a poll, returning
  an opaque reference used by `tally`/`resolve`.
- `tally(poll_ref) -> dict` -- current vote counts per option.
- `resolve(poll_ref, quorum) -> dict` -- a decision record once `quorum` is
  met, or a pending/expired result otherwise.
- `healthcheck() -> bool`

## Error semantics

Deferred to the P1 adapter task; no P0 caller exercises this port.
