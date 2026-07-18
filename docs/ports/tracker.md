# `tracker` (`engine.ports.Tracker`)

Canonical (P0): `github-issues`.

## Ops

- `fetch_ticket(ref) -> TicketDetails` -- read the ticket's current
  title/body/labels into a `TicketDetails` (the tracker-fetched view; distinct
  from the persisted-state `Ticket`). Raises on a missing/inaccessible ref;
  never returns a partial ticket.
- `parse_event(payload, event_key) -> Event | None` -- normalize a raw
  webhook/poll payload into an `Event`, or `None` if the payload isn't one
  this adapter cares about (e.g. a bot-authored comment). `event_key` seeds
  `event_id` so re-delivery of the same source event produces the same id.
- `set_status_labels(ticket_id, status, labels)` -- replace the engine-owned
  label set on the ticket. Idempotent: setting the same labels twice is a
  no-op write.
- `upsert_pinned_comment(ticket_id, body, event_id) -> comment_id` -- create
  the pinned status comment on first call, edit it in place afterward.
  `event_id` guards against a duplicate edit from a re-delivered event.
- `post_closing_summary(ticket_id, body, event_id)` -- post once, keyed by
  `event_id`; a re-delivered close event must not double-post.
- `healthcheck() -> bool`

## Error semantics

Network/auth failures raise; callers (dispatcher/collector) catch, record
health, and retry per the run's budget. A ticket ref that never existed is a
hard failure, not a retryable one.
