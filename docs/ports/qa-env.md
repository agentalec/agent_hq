# `qa-env` (`engine.ports.QaEnv`)

Protocol only in P0 (D3) -- no adapter ships until P1
(`docker-compose`). The `qa` task is registered and its cross-task graph
properties are validated (`agent-hq tasks validate`), but it declares no
`components` entry at all and stays unwired until a `qa-env` binding exists
in `components.yml` -- see `docs/task-authoring.md` "Dispositions".

## Ops

- `up(repos, fixtures) -> base_url` -- stand up an environment for `repos`
  seeded with `fixtures`, returning its base URL.
- `down()` -- tear the environment down.
- `capture(dest)` -- capture diagnostic artifacts (logs, screenshots) to
  `dest`.
- `healthcheck() -> bool`

## Multi-repo reads (deferred)

`up(repos, ...)` already takes multiple repos, but every wired task in P0
targets exactly one repo per run (`run.repo`, set by the handoff that
spawned it or by intake's root-run resolution) -- there is no task today
that needs to read more than one work-repo head at once. Reading multiple
work-repo heads for one QA run is a genuine multi-repo concern (e.g. a
`breakdown` fan-out across two repos both needing one integrated QA pass),
but it is deferred until this port actually gets a binding: no unused
multi-repo field is added to `run`/`work_repos` ahead of that need
(`docs/roadmap.md`).

## Error semantics

Deferred to the P1 adapter task; no P0 caller exercises this port.
