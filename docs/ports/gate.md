# `gate` (`engine.ports.Gate`)

Canonical (P0): `github-issue-comment` (default/`spec-approval` binding,
`config/components.yml`) -- an authorized-comment approval on the parent
(engine-repository) issue. `pr-review` remains registered for a task that
binds to it explicitly (code-review approval on a work-repo PR). D2 still
holds for both: every P0 gate is a post-gate (no native-approval dual path).

## Ops

- `request(group, subject) -> GateRequest` -- request approval from `group`
  on `subject`. Returns a `GateRequest` carrying the `request_id` recorded
  on the run (`gate_request_id`); calling twice for the same subject must
  not create a duplicate ask (comment or review request).
- `status(run: dict) -> GateDecision` -- current decision (`APPROVED` /
  `CHANGES_REQUESTED` / `REJECTED` / `PENDING` / `EXPIRED`) for the run's
  outstanding gate request. `GateDecision` also carries optional audit
  metadata (`comment_id`, `actor`, `decided_at`) a comment-based gate
  attaches to a decision; a PR-review-style gate leaves these `None`. The
  adapter only REPORTS this -- it writes no state itself. The engine appends
  the deduped approval event (keyed by `comment_id`, packed into the
  existing event `detail`) in the same state write that advances the run.
- `healthcheck() -> bool`

## `github-issue-comment`

Settings: `{"issue_repo": "org/engine-repo", "approvers": <approvers.yml
dict>}`. `issue_repo` is injected by `engine.engine.build_port_adapter` from
`intake_repo(config)` -- distinct from the (ignored here) work-repo `repo`
key `pr-review` uses.

- `request` posts a comment on the ticket's engine issue naming the run/task,
  `@`-mentioning the approver group, and stating the decision-command
  grammar; dedupe marker `<!--hq:gate:<run-id>-->` makes a second call a
  no-op that returns the existing comment id.
- `status` parses the authorized decision grammar
  (`docs/architecture.md` "Approval and reopen commands"):
  - `/agent-hq approve <run-id>` -> `APPROVED`
  - `/agent-hq request-changes <run-id> <reason>` -> `CHANGES_REQUESTED`
  - `/agent-hq reject <run-id> <reason>` -> `REJECTED`

  Only a comment whose `<run-id>` matches this run AND whose commenter is a
  member of the run's `approver_group` counts; everything else is ignored.
  The latest (by `created_at`) qualifying comment wins. With no qualifying
  comment, `status` falls back to the same `timeout_working_hours` ->
  `EXPIRED` check as `pr-review`, else `PENDING`.
- Guarded `reopen` (Task 16) reuses this same authorized-comment machinery
  for `/agent-hq reopen <reason>`, subject to its own allowed-block-source
  and PR-guard checks -- not a gate decision, so it is routed separately by
  the engine's event handler, not through this adapter's `status`.

## `pr-review`

Unchanged (`docs/ports/gate.md` history): settings `{"repo": "org/repo",
"approvers": ..., "default_base": "main"}`; `request` opens/reuses a draft
PR and requests reviewers; `status` reads PR reviews from the configured
approver group.

## Error semantics

All P0 gates are post-gates (D2 -- no native-approval dual path). A gate
past `timeout_working_hours` with no decision resolves to `EXPIRED` via the
sweep, not inside the adapter; the adapter only reports what it currently
sees.
