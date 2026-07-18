# `gate` (`engine.ports.Gate`)

Canonical (P0): `pr-review` only (D2 -- `github-environment` is a P1
adapter behind this same contract).

## Ops

- `request(group, subject) -> GateRequest` -- request approval from
  `group` on `subject` (e.g. a PR). Returns a `GateRequest` carrying the
  `request_id` recorded on the run (`gate_request_id`); calling twice for
  the same subject must not create duplicate review requests.
- `status(run: TaskRun) -> GateDecision` -- current decision
  (`APPROVED` / `CHANGES_REQUESTED` / `REJECTED` / `PENDING` / `EXPIRED`)
  for the run's outstanding gate request.
- `healthcheck() -> bool`

## Error semantics

All P0 gates are post-gates (D2 -- no native-approval dual path). A gate
past `timeout_working_hours` with no decision resolves to `EXPIRED` via the
sweep, not inside this adapter; the adapter only reports what it currently
sees.
