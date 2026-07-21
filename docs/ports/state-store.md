# State store (`GitJsonStateStore`)

Not a port. Per PD-7 this is a fixed, single implementation until a second
one is ever needed -- `engine/state.py` is constructed directly with a
worktree path, never resolved through the adapter registry.

## Storage

State lives as JSON on the orphan `agent-hq-state` branch of the engine
repo, checked out as a worktree (production: `./_state`). Layout:

- `tickets/<id>/state.json` -- one document per ticket: `ticket_id`,
  `pinned_comment_id`, `status`, `runs[]` (matches
  `schemas/state.schema.json`).
- `tickets/<id>/events.jsonl` -- append-only, one JSON object per line
  (matches `schemas/event.schema.json`).
- `health/latest.json` -- map `"<port>/<adapter>"` -> `{ok, detail, ts}`
  (matches `schemas/health.schema.json`).

## Contract

- `read_state(ticket_id) -> dict | None` -- the raw `state.json` document,
  or `None` if the ticket has no state yet.
- `write(fn)` -- the single write primitive. `fn(txn)` mutates in memory via:
  - `txn.set_ticket(ticket_id, **fields)` -- merge ticket-level fields.
  - `txn.put_run(ticket_id, run_dict)` -- insert or fully replace a run.
  - `txn.update_run(ticket_id, run_id, **fields)` -- field-level merge into
    an existing run; raises `KeyError` if the run isn't present.
  - `txn.append_event(ticket_id, event_dict)` -- appends unless an event
    with the same `event_id` already exists for that ticket (idempotent).
  - `txn.record_health(port, adapter, ok, detail)` -- upserts
    `health/latest.json` with `ts` set to now.

  After `fn` returns, every changed file is written, staged, and pushed as
  **one commit**. If nothing changed, `write` is a no-op (no commit, no
  push). Pushes authenticate via a command-scoped credential helper reading
  `AGENT_HQ_TOKEN` when set; with no `AGENT_HQ_TOKEN` (local/test), a plain
  push is used.

  Concurrent writers are serialized externally (Actions concurrency group
  `agent-hq-state`, D5). If a push is rejected as non-fast-forward anyway,
  `write` does one `git fetch` + `git reset --hard origin/<branch>` and
  re-runs `fn` against the fresh state before pushing again. A second
  rejection raises.
  `# ponytail: Actions concurrency group serializes writers; this retry is a safety net only`

- `claim_run(ticket_id, run_id, now_iso, max_runtime_min) -> bool` -- inside
  a `write`, idempotently transitions `QUEUED -> RUNNING`. Sets
  `deadline = now + max_runtime_min` only if the run has no deadline yet
  (deadlines are immutable across re-claims); always refreshes
  `attempt_started_at`. Returns `False` (no-op, no commit) if the run isn't
  `QUEUED`.

## Not covered

No listing/query API beyond `read_state` -- callers that need to scan all
tickets read the worktree directory tree directly. No caching: every read
hits disk in the worktree.

## Isolated-job access (hardening plan Task 12)

`prepare` and `collect` are credentialed Actions jobs and read/write this
store normally. `execute` is credential-free (`permissions: {}`, only
`COPILOT_GITHUB_TOKEN`) and never calls `write()` -- it only needs the
already-claimed run's record, fetched via a read-only, anonymous clone/pull
of the (public) engine repo's `agent-hq-state` branch (PD-5: a public repo
needs no clone credential); no `AGENT_HQ_TOKEN` ever reaches that job.
