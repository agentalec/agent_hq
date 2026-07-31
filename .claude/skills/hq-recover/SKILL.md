---
name: hq-recover
description: Guided manual repair of a stuck agent_hq ticket using only documented procedures — branch_conflict recovery, crashed queue-empty completion, manual re-enqueue of a failed/blocked run, pause/resume via kill switch. Use when the operator says "recover ticket N", "repair the state branch", "re-enqueue this run", "unstick this ticket", or "pause/resume dispatch". Invoked explicitly by the operator only.
argument-hint: "[issue-number]"
disable-model-invocation: true
---
# hq-recover

Contract: only the procedures below are permitted. Any situation they do not cover means stop and report — never improvise a state edit. Until the operator CLI (`retry`/`block`/`unblock`/`reopen`, hardening Tasks 14-18) lands, repair means hand-editing the `agent-hq-state` branch; this skill is the safe path for that.

Diagnose first with `hq-ticket`; this skill assumes you already know which procedure applies. If reading `agent-hq-state` fails because the branch does not exist, there is no deployment state yet — nothing to recover; stop.

## Steps

1. **State-edit setup (shared by B and C).** Work in a fresh clone or worktree of `agent-hq-state` — never `./_state` (owned by the workflows):
   ```bash
   git -C "$SCRATCH" clone --branch agent-hq-state <engine-repo-url> state-repair
   ```
   Ticket state is `tickets/<issue-number>/state.json`; events are `tickets/<issue-number>/events.jsonl`; ledger artifacts are `tickets/<issue-number>/artifacts/<run_id>/`. After any edit: show the operator the full `git diff`, get explicit confirmation, then commit as `state: <ticket-id> manual repair: <what>` and plain-push (never force). Afterwards wake the dispatcher: `gh workflow run dispatch.yml`.

2. **(A) `branch_conflict`** — ticket `BLOCKED`, `block_reason: branch_conflict`. Follow `docs/operations.md` §10 exactly:
   1. In the target work repo, diff the remote `agent-hq/<issue-number>` head against `work_repos[repo].recorded_head` from `state.json` to see what unexpected work landed.
   2. If that work is worth keeping, copy it aside first: `git branch rescue/<issue-number> origin/agent-hq/<issue-number>` and push `rescue/<issue-number>`.
   3. Force-reset `agent-hq/<issue-number>` back to exactly `recorded_head`. Do NOT hand-merge: a merge moves the head off `recorded_head`, so the retried attempt just re-blocks.
   4. §10 says "retry" — that CLI does not exist yet; perform procedure (C) below as its manual equivalent.

3. **(B) Crashed queue-empty completion** — ticket `ACTIVE`, every run terminal, no pending entries, the terminal run's task IS `config/projects.yml` `final_task`, but closing side effects are partial (the sweep never re-drives this; hardening Task 15 gap). If the terminal run is NOT `final_task`, the queue ran dry early and the engine should have BLOCKED the ticket — that is not this procedure; report it. Mirror `engine/engine.py:_complete_if_queue_empty`:
   1. Determine which side effects already happened: closing summary comment on the issue (dedupe marker `<!--hq:evt:<ticket>:<run_id>:done:closing-summary-->`)? Each `work_repos[].pr_ref` marked ready? Issue closed?
   2. Complete only the missing ones, confirming each with the operator first: post the summary from the terminal run's ledger copy (`tickets/<id>/artifacts/<run_id>/specs/<id>/summary.md`) including its dedupe marker; for each recorded PR, split `pr_ref` (`owner/repo#<number>`) on `#` and run `gh pr ready <number> -R <owner/repo>` (mirrors `mark_pr_ready` in `engine/adapters/claude_code_headless.py`); `gh issue close <issue-number>`.
   3. Edit `state.json`: `"status": "DONE"`. Diff, confirm, commit, push per step 1.

4. **(C) Manual re-enqueue of a failed/blocked run** — the `engine.engine.reenqueue_same` equivalent; mirror it exactly:
   1. Identify the terminal run to retry in `state.json` `runs`. NEVER edit it — append a new run object instead, with `attempt` = old attempt + 1.
   2. New `run_id`: for a handoff-spawned run (has `handoff_key`) it MUST be
      ```bash
      .venv/bin/python -c "from engine.models import compute_handoff_run_id; print(compute_handoff_run_id('<parent_run_id>', '<handoff_key>', <attempt+1>))"
      ```
      using the old run's `parent_run_id` as source. For a root run (no `handoff_key`) it MUST be
      ```bash
      .venv/bin/python -c "from engine.models import compute_run_id; print(compute_run_id('<parent_run_id or source_event_id>', <enqueue_index or 0>, '<task_id>', <attempt+1>))"
      ```
      using the old run's `parent_run_id` if set, else its `source_event_id`. If you cannot recompute the id (missing `handoff_key` on a run that should have one, or a root run whose causal fields — `parent_run_id`/`source_event_id` — are unclear) — stop and report.
   3. The new run copies the old run's `task_id`, `ticket_id`, `bindings`, `chain_depth`, `parent_run_id`, `handoff_key`, `repo`, and `input_artifacts` (a root run copies `source_event_id` and `enqueue_index` instead of the last three), with `"state": "QUEUED"`, `"cost_usd": null`, `"tokens": null`, `"usage_known": false`, `"artifacts": []`. `task_version` is NOT copied from the old run: use the current `version` in `tasks/<task_id>/task.yml` (what `taskdef["version"]` resolves to), matching `reenqueue_same`.
   4. Append the matching event to `events.jsonl`: `{"event_id": "<new_run_id>:queued", "kind": "run.queued", "ticket_id": ..., "run_id": ..., "task_id": ..., "task_version": ..., "state": "QUEUED", "bindings": {...}}`.
   5. Set the ticket back to `"status": "ACTIVE"` and null out `block_reason`/`block_source`/`interrupted_run_id`. Diff, confirm, commit, push, then `gh workflow run dispatch.yml`.

5. **(D) Pause/resume dispatch.** `gh variable set AGENT_HQ_KILL_SWITCH --body 1` pauses all new dispatch (in-flight runs finish; intake still records). `gh variable delete AGENT_HQ_KILL_SWITCH` resumes. See `docs/operations.md` §6.

## Hard rules

- Show the full diff and get explicit operator confirmation before ANY push, issue close, or PR mutation.
- Never force-push `agent-hq-state`.
- Never mutate a terminal run's recorded history — append a new run at `attempt + 1`.
- Never hand-merge in a `branch_conflict` — rescue-branch then reset to `recorded_head`.
- Never invent a procedure not listed here; a `run_id` you cannot recompute correctly = stop and report.
- Validate an edited `state.json` against `schemas/state.schema.json` before committing.

## References

- `docs/operations.md` §10 (branch_conflict recovery), §11 (push/replay serialization), §6 (kill switch)
- `docs/setup-new-repo.md` §8 (operating limits of the current build)
- `docs/architecture.md` (Lifecycle)
- `engine/engine.py` (`reenqueue_same`, `_complete_if_queue_empty`), `engine/models.py` (`compute_handoff_run_id`)
