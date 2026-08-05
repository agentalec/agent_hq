# Agent HQ issue drafts

These drafts were checked against the current Agent HQ source and configuration
on 2026-08-05.

## Validity summary

| Item | Status |
|---|---|
| Per-task model selection | Valid enhancement |
| QA passed unexercised flows | Confirmed QA-quality defect |
| Durable agent-run observability | Valid decision/spike, not a bug |
| QA video evidence | Valid enhancement; already listed as P2 roadmap work |
| Retry loses malformed-control feedback | Confirmed bug |
| Workflow-dispatch command injection | Confirmed security bug |
| Deleted `pages.yml` still dispatched | Confirmed bug |
| Documentation drift | Confirmed documentation defect |

Each section below is self-contained and can be copied into a GitHub issue.

---

# Add per-task executor/model selection

## Problem

Agent HQ currently selects the coding model globally through
`config/components.yml`.

Both `executor` and `agent-session` use `copilot-cli` with
`claude-sonnet-4.5`. A task can use the global binding, but cannot request a
different approved model for a specific purpose.

Different tasks have different needs:

- `spec` and `review` may benefit from a stronger reasoning model.
- `implement` may need a model optimized for code changes.
- `qa` may need a lower-cost model when its work is primarily browser-driven.
- Experimental model comparisons should be possible without changing the
  deployment-wide default.

## Current behavior

- `config/components.yml` owns the global adapter and model settings.
- `resolve_binding()` supports a label override for the adapter, but not a
  per-task model/settings override.
- Task definitions do not currently define executor/model policy.

## Proposed outcome

Allow a task definition to select an approved logical executor profile, such
as:

```yaml
components:
  agent-session: high-reasoning
```

Resolve that profile through deployment configuration rather than allowing a
task prompt to name arbitrary providers or model IDs.

## Acceptance criteria

- A task can select a named, configuration-defined executor/model profile.
- Unknown profiles fail task/config validation.
- Task definitions continue to contain logical names, not provider-specific
  credentials or raw secrets.
- Existing tasks keep the current global default when no override is declared.
- The selected profile is recorded on the run for auditability.
- Tests cover default selection, task override, and invalid profile rejection.

## Notes

This is an enhancement, not a current runtime bug.

---

# Prevent QA from marking unexercised acceptance criteria as passed

## Problem

The QA report for [care_fe_agent_hq PR #1](https://github.com/yash-learner/care_fe_agent_hq/pull/1#issuecomment-5168902595)
reported every acceptance criterion as `pass`.

However, the same report states that several required live flows were not
fully exercised because of navigation, data, or permission constraints. Those
criteria were verified only by code inspection.

For example, the report says that questionnaire entity selection, medicine
instructions, role selection, and device selection were not fully exercised
in the running application, but still presents a full-pass result.

This creates false confidence: code inspection can support a finding, but it
does not prove a user-facing flow behaved correctly.

## Expected behavior

If the QA agent cannot reach and perform the required interaction in the real
application, the criterion must be reported as `not-exercised` with a clear
reason.

A criterion may be `pass` only when the QA run performed the required flow and
produced evidence from the real application.

## Scope

Review and strengthen:

- `tasks/qa/prompts/qa.md`
- `tasks/qa/checklists/qa-coverage.md`
- QA artifact/report validation in the engine, where feasible

## Acceptance criteria

- A `pass` verdict requires evidence of an actual interaction with the real
  application, not only source-code reasoning.
- A screenshot alone is insufficient when it does not show the required
  post-interaction state.
- Unreachable flows are marked `not-exercised`, with the exact blocker.
- The QA summary cannot claim that all criteria passed when any criterion is
  `fail` or `not-exercised`.
- The QA report clearly separates live-flow evidence, code inspection,
  emulator/browser limitations, and real-device limitations.
- Add a regression test or structured QA-report validation for this policy.

## Reference

- [PR #1 QA report](https://github.com/yash-learner/care_fe_agent_hq/pull/1#issuecomment-5168902595)

---

# Evaluate durable observability for agent runs

## Problem

Agent HQ records durable run metadata, artifacts, cost, token counts, patch
output, and selected failure detail. It does not currently retain a complete
operational record of an agent session, such as:

- the rendered prompt;
- tool/command activity, where available;
- structured execution logs;
- session/checkpoint references;
- a useful investigation timeline for failed or surprising runs.

This makes it difficult to understand why an agent took a particular path or
why QA evidence was weak.

## Proposal

Run a small, private proof of concept for an observability integration such as
Entire, or document an equivalent native approach.

This is not a request to collect private chain-of-thought. The goal is
operational traceability: prompts, commands/tool events where available,
patches, checkpoints, outputs, and failure diagnostics.

## Questions to answer

- Can it capture Copilot CLI sessions used by Agent HQ?
- Can records be linked to ticket ID, run ID, commit, and PR?
- Can it operate on a private repository/remote?
- What data is stored, where, and for how long?
- How are secrets, patient data, issue text, and repository contents redacted
  or excluded?
- Is it best-effort observability, or would it become a delivery dependency?
- What are the cost and retention implications?

## Acceptance criteria

- A private sandbox proof of concept is documented.
- Captured data is linked to an Agent HQ run without exposing secrets.
- The integration is best-effort: a telemetry failure cannot block a task,
  patch collection, PR creation, or ticket completion.
- Retention, access controls, and redaction rules are documented.
- The result recommends adopt, defer, or reject with evidence and operational
  trade-offs.

## Notes

This is an architectural decision/spike, not a defect.

---

# Add optional video evidence for QA runs

## Problem

Full-page screenshots are useful point-in-time evidence, but they do not show
the interaction sequence.

For UI workflows such as drawers, focus behavior, keyboard appearance,
navigation, and responsive layout changes, a short video can show:

- how the agent reached the state;
- whether a drawer actually opened;
- focus movement;
- whether a keyboard/layout jump occurred;
- whether the screenshot represents the real flow.

## Proposed outcome

Add optional, short video artifacts to the QA task for interaction-heavy
acceptance criteria.

Videos should complement screenshots, not replace them. Screenshots remain
useful for fast PR review and stable evidence links.

## Scope

- Add a declared QA video artifact directory.
- Define a size, duration, and retention limit.
- Capture only the real running application.
- Include video links in `qa.md` when a video was captured.

## Acceptance criteria

- QA can capture an optional short video for a specified acceptance criterion.
- Videos are stored as run ledger artifacts, not committed to the work repo.
- QA reports link each video to the criterion it demonstrates.
- Capture failure does not produce a false `pass`.
- Artifact limits prevent excessive storage or Actions costs.
- Screenshots remain required for visual acceptance criteria.
- The solution documents browser/emulator limitations, especially for iOS
  virtual-keyboard behavior.

## Notes

A “Demo-video task” is already listed as deferred P2 work in
`docs/roadmap.md`. This issue should define the implementation scope and
priority rather than duplicating the roadmap item silently.

---

# Pass malformed control-output feedback to retry attempts

## Problem

When a task emits an invalid `.agent-hq/control.json`, the engine records a
`handoff.rejected` event and retries the task when its retry budget allows it.

The retry does not receive the rejection reason.

The retry prompt currently reads feedback only from `run.rework` events for
the retry run. A malformed control document is recorded as
`handoff.rejected` on the failed attempt, so attempt 2 starts with the same
prompt and can repeat the exact same schema mistake.

Observed example:

```text
control.json schema violation: <root>: 'outcome' is a required property
```

Ticket 4 then retried the task and failed with the same validation error.

## Expected behavior

A retry caused by invalid control output should receive concise, safe feedback
explaining why the prior attempt was rejected.

For the example above, the retry should be told:

```text
Your previous control.json was rejected because it was missing the required
"outcome" property. Produce a schema-valid control.json.
```

## Likely implementation options

1. Write the rejection reason as retry feedback for the newly queued retry.
2. Extend retry feedback loading to include the failed predecessor's relevant
   `handoff.rejected` event.

The implementation must preserve the distinction between a human-requested
`run.rework` event and an engine-generated validation rejection.

## Acceptance criteria

- A control-schema rejection followed by a retry includes the rejection reason
  in the retry prompt.
- The retry receives feedback only from its own immediate failed predecessor,
  not unrelated ticket events.
- The feedback is concise and does not expose secrets or raw sensitive output.
- Human rework comments continue to work unchanged.
- A regression test reproduces invalid control output, retry creation, and a
  retry prompt containing the validation reason.
- The retry can produce a corrected control document without manual
  intervention.

## Reference

- [Ticket 4 events](https://github.com/yash-learner/agent_hq/blob/agent-hq-state/tickets/4/events.jsonl)

---

# Security: prevent command injection through workflow-dispatch run_id

## Severity

High

## Problem

`.github/workflows/run.yml` interpolates the manually supplied
`inputs.run_id` directly into shell commands in credentialed jobs:

```yaml
run: bash scripts/run-phases.sh "${{ inputs.run_id }}" prepare
```

GitHub expression substitution occurs before Bash parses the generated script.
A shell metacharacter or command substitution in `run_id` can therefore run
before `scripts/run-phases.sh` validates whether the run ID exists.

The same unsafe pattern exists in the `execute` and `collect` paths.

`prepare` and `collect` expose `AGENT_HQ_TOKEN` and have write-capable GitHub
permissions.

## Reproduction

A controlled marker-only test on a fork demonstrated that Bash executed a
command substitution before the script ran:

```text
INJECTION_PROOF
scripts/run-phases.sh: line 16: 1: usage: run-phases.sh ...
```

The script rejected the resulting invalid argument only after the injected
shell expression had already run.

## Impact

A user permitted to manually dispatch the workflow can execute arbitrary shell
commands in a credentialed GitHub Actions job.

## Required fix

- Do not interpolate `inputs.run_id` directly into a shell `run:` command.
- Pass it as data through an environment variable or a non-shell argument
  boundary.
- Validate the value against the expected run-ID format before using it.
- Review every use of `inputs.run_id`, including workflow command steps,
  `devcontainers/ci` `runCmd`, artifact names and paths, and concurrency/display
  fields.

## Acceptance criteria

- A command-substitution payload is treated as a literal invalid run ID and
  never executes.
- Valid dispatcher-created run IDs still complete prepare, execute, and
  collect normally.
- Invalid IDs fail before state access or worktree/path use.
- Add a regression test or workflow-level security test for unsafe characters.
- Document the trust boundary for `workflow_dispatch` inputs.

---

# Remove obsolete pages.yml dispatches and update hq-doctor

## Problem

Dashboard deployment now uses the `gh-pages` branch directly. No
`pages.yml` workflow exists.

However, both workflows still attempt to dispatch it:

- `.github/workflows/intake.yml`
- `.github/workflows/dispatch.yml`

They call the GitHub API for:

```text
actions/workflows/pages.yml/dispatches
```

The request always returns 404 and is hidden by `|| true`.

The `hq-doctor` skill also incorrectly requires `pages.yml` and instructs
operators to enable Pages using GitHub Actions, even though the current
deployment model is branch-based `gh-pages`.

## Impact

- Every intake/dispatch run makes a guaranteed failing API request.
- The failure is silently hidden, making operational troubleshooting harder.
- `hq-doctor` falsely reports a healthy branch-based Pages deployment as
  broken.
- Documentation and operational guidance disagree with the actual deployment.

## Expected behavior

Dashboard source is published explicitly to `gh-pages`; state updates do not
trigger a Pages workflow.

## Acceptance criteria

- Remove the nonexistent `pages.yml` dispatch calls from intake and dispatch.
- Remove obsolete comments and environment assumptions associated with those
  calls.
- Update `hq-doctor` to validate the current deployment model:
  - required workflows are `intake.yml`, `dispatch.yml`, and `run.yml`;
  - Pages, if enabled, serves the `gh-pages` branch.
- Update doctor guidance from “GitHub Actions source” to the branch-based
  Pages setup.
- Add or update tests so a deleted/absent `pages.yml` is not required.
- Verify a normal intake and dispatch run no longer makes the 404 request.

---

# Reconcile documentation with the current queue-based engine

## Problem

Several prominent documents still describe retired behavior, while the current
engine uses queue-based control outcomes and branch-based dashboard deployment.

Examples of stale concepts include:

- `handoff.allowed` and `handoff.max`;
- `handoff` and `complete` control outcomes;
- task-defined static routes;
- workflow-based Pages deployment via `pages.yml`;
- old completion/lifecycle descriptions.

Current code and task schemas use `queue` and `blocked` outcomes. The queue is
declared by the run’s control document; tasks do not declare a fixed
`handoff.allowed` route.

## Affected documents

At minimum, review and reconcile:

- `README.md`
- `docs/architecture.md`
- `docs/task-definition.md`
- `docs/building-tasks.md`
- `docs/setup-new-repo.md`
- `docs/live-smoke-test.md`
- `docs/roadmap.md`
- `.claude/skills/hq-doctor/SKILL.md`

## Why this matters

Operators and task authors can configure invalid fields, expect nonexistent
workflows, or misunderstand how a run reaches completion. This has already
made debugging and deployment setup confusing.

## Acceptance criteria

- Documentation accurately describes only supported control outcomes:
  `queue` and `blocked`.
- Removed `handoff.allowed`, `handoff.max`, `handoff`, and `complete`
  instructions are deleted or clearly labelled as historical context.
- The task-routing explanation matches the current runtime behavior:
  a completed run declares ordered queue entries in `.agent-hq/control.json`.
- Dashboard setup correctly states that Pages serves the `gh-pages` branch and
  no `pages.yml` workflow is required.
- Lifecycle/completion text matches `final_task` and current
  `AWAITING_MERGE` behavior.
- `hq-doctor` instructions match the current workflow and Pages model.
- Links and examples are checked with the documentation/test validation suite.
