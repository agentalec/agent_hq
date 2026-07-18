# `qa-env` (`engine.ports.QaEnv`)

Protocol only in P0 (D3) -- no adapter ships until P1
(`docker-compose`).

## Ops

- `up(repos, fixtures) -> base_url` -- stand up an environment for `repos`
  seeded with `fixtures`, returning its base URL.
- `down()` -- tear the environment down.
- `capture(dest)` -- capture diagnostic artifacts (logs, screenshots) to
  `dest`.
- `healthcheck() -> bool`

## Error semantics

Deferred to the P1 adapter task; no P0 caller exercises this port.
