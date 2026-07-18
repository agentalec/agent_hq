# `messaging` (`engine.ports.Messaging`)

Canonical (P0): `github-comment` (@-mentions ride GitHub notifications).

## Ops

- `notify(audience, message, links, event_id)` -- post `message` (plus
  `links`) to `audience`, a dict of
  `{"ticket_id": <ticket ref>, "mentions": [<recipient>, ...]}` (adapters
  interpret both keys for their medium). `event_id` makes re-delivery
  idempotent: the same
  `event_id` must not produce a second notification.
- `healthcheck() -> bool`

## Error semantics

Failures raise; callers record health and do not block the run on a failed
notification (messaging is best-effort relative to state transitions, which
are the source of truth).
