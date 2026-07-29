# `agent-session` (`engine.ports.AgentSession`)

Canonical (P0): `copilot-cli` (default binding, `config/components.yml`);
`claude-code-headless` is the one-line-swap fallback for direct Anthropic
API billing (`CopilotCli` subclasses `ClaudeCodeHeadless` and inherits its
git/PR plumbing unchanged).

**Isolated-job split (hardening plan Task 12):** `prepare_worktree` / `run` /
`collect_outputs` / `materialize_work_patch` run in **execute**'s
credential-free job; `prepare_worktree` (again, for a fresh landing clone) /
`apply_patch` / `land_branch` / `open_draft_pr` / `mark_pr_ready` /
`request_reviewers` run only in **collect**'s credentialed job. Execute
never holds a push credential and never calls the last group.

`pr_state` is the one op the **dispatcher** calls (from `sweep`, to resolve
an `AWAITING_MERGE` ticket) rather than a run phase -- it is a pure read, so
it needs no push credential and belongs to no run.

## Ops

- `prepare_worktree(run_id, repo, base_commit) -> Path` -- checkout `repo`
  at `base_commit` into an isolated worktree for `run_id`. Fixes artifact
  lineage: every output is traceable to the exact commit the run started
  from. Called by **execute** for its own worktree (a plain clone of a
  public repo needs no credential -- PD-5) and again by **collect**, with a
  distinct run id (`<run_id>-collect`), for a fresh landing clone.
- `run(bundle, tools, deadline) -> dict` -- execute the prompt/context
  bundle (from `bundle.json`, `docs/task-authoring.md` "Artifact
  namespace") with an allowlisted tool set (PD-5: the agent never holds
  credentials the host process doesn't hand it) until it finishes or
  `deadline` passes.
- `collect_outputs(worktree, declared) -> list[str]` -- verify and return the artifact
  paths the task definition declared as outputs; missing declared artifacts
  is a failure, not a partial success. Called by execute, against its own
  worktree, before staging.
- `materialize_work_patch(worktree, exclude_paths) -> str` -- diff the
  agent's committed+uncommitted changes against the run's base tag,
  excluding `exclude_paths` (the declared `outputs.artifacts` and any
  restored `input_artifacts` -- neither is work-repo code) and `.agent-hq/`.
  This patch is the ONLY payload that ever reaches the target repo; execute
  never pushes it directly.
- `apply_patch(worktree, patch_text) -> None` -- `git apply` a transported
  work patch onto collect's fresh landing clone. Raises if it doesn't apply
  cleanly -- a patch that fails to apply fails the run, never a partial
  land.
- `land_branch(run_id, worktree, branch, base_branch) -> dict` -- commit the
  applied patch (if dirty) and fast-forward-push onto the ticket's stable
  `branch` (created from `base_branch` on the first push). Returns
  `{"landed": True, "head": <sha>}` on success -- including when a rejected
  push turns out to be an identical retry (same tree/parent, adopted rather
  than reapplied) -- or `{"landed": False, "head": ..., "remote_head": ...}`
  on a real divergence, for the caller to block (`branch_conflict`) rather
  than force over unknown work.
- `open_draft_pr(repo, branch, base, title, body) -> str` -- create-or-get:
  collect only calls this once per repo per ticket (checking
  `work_repos[repo].pr_ref` first), after a successful land.
- `pr_state(pr_ref) -> dict` -- `{"state": "open"|"closed", "merged": bool}`
  for a recorded work PR. Read-only, called by the sweep, never by a run.
  `merged` must be reported separately from `state`: a closed-unmerged PR is
  a human declining the work (ticket `BLOCKED`), a merged one is the work
  landing (ticket `DONE`), and `state` is `"closed"` for both.
- `healthcheck() -> bool`

## Control output and the four artifact payloads

A run's outcome and its handoff proposals are never returned from `run()`
directly -- the agent process itself writes them to disk inside the
worktree, and execute reads them back to build its own transported output:

- **The work patch** (`materialize_work_patch`) -- everything else the
  agent changed in the worktree, excluding the declared outputs and
  restored inputs. Collect `apply_patch`es this to a fresh clone and
  `land_branch`es it -- the only payload that ever reaches the target work
  repo.
- **`execute-result.json`** (`schemas/execute-result.schema.json`) --
  `outcome` (`"success"`/`"failure"`), `usage_known`, nullable
  `cost_usd`/`tokens`. The adapter normalizes its own raw output into this
  shape (no `session_id`; a timeout maps to `failure` + `detail` -- the
  schema only knows success/failure). Collect validates this against the
  schema ALWAYS and records it unconditionally, before looking at anything
  else; on `"failure"` it runs only retry/failure accounting and reads no
  further payload -- no apply, no land, no push.
- **`control.json`** (`schemas/control.schema.json`) -- read only when
  `execute-result.json` reports `"success"`. One of the three control
  outcomes (`handoff`/`complete`/`blocked`,
  `docs/task-authoring.md` "Control outcomes"); validated by
  `engine.handoff.validate_handoffs` before anything in it is trusted.
- **The staged declared/input artifacts** -- execute containment-checks and
  copies the declared `outputs.artifacts` and any restored `input_artifacts`
  into a staging directory (the first traversal boundary); collect
  re-validates containment on the transported copy before persisting any of
  it to the ledger (`tickets/<id>/artifacts/<run_id>/`).

`.agent-hq/bundle.json` (prepare's own manifest -- prompt, tools, deadline,
repo, base_commit, declared output paths, and the parent's `diff_base`/
`diff_head` commit ids when a task's prompt needs the parent diff) is a
fifth transport artifact, produced by prepare (no clone -- it never runs
`_write_parent_diff` itself) and consumed by execute. None of this crosses
a job boundary as anything other than plain files -- a normal Actions
artifact (`actions/upload-artifact`/`download-artifact`), never a custom
tar: `bundle-<run_id>` (prepare -> execute) and `execute-out-<run_id>`
(execute -> collect). `.git` is never transferred.

## Error semantics

No checkpoint/resume in P0 (D1): a killed session is retried from scratch
by the dispatcher, bounded by `budget.retries`. `run` never partially
succeeds from the caller's point of view -- it returns a complete result or
raises/times out.
