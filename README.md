# Operator dashboard

Static, read-only projection of the `agent-hq-state` branch. Implements the
`Operator Dashboard.dc.html` design against
[`docs/dashboard-design-requirements.md`](../docs/dashboard-design-requirements.md).

No build step, no framework, no dependency. Four files ship:

| File | |
|---|---|
| `index.html` | shell, landmarks, per-deployment config |
| `app.js` | fetch, derive, render — DOM API only, no `innerHTML` |
| `app.css` | component styles (the design carried these inline) |
| `tokens.css` | **vendored verbatim** from the Claude Design project — re-import, don't hand-edit |
| `fixture.json` | sample state for local development; it ships with the site but is only ever fetched on `localhost` |

## Configure per deployment

One line in `index.html`:

```html
<meta name="agent-hq:engine-repo" content="agentalec/agent_hq">
```

The engine repo must be **public** — that is what makes the state branch
readable without a token. On a private install the page fails closed with the
FETCH FAILED state and points at the `agent-hq` CLI, which is intended
(`docs/operations.md` §9).

## Run it locally

```bash
cd dashboard && python3 -m http.server 8099
open http://127.0.0.1:8099/index.html
```

On `localhost`/`127.0.0.1` the page reads `fixture.json` instead of the live
branch, so the whole UI is exercisable offline. The fixture deliberately
includes the awkward cases: a ticket with no `block_reason`, a run with
`usage_known: false`, `AWAITING_MERGE`, a five-attempt step, and the hostile
artifact string from `tests/fixtures/state/tickets/HQ-1/state.json`.

## Data contract

Fetches **one** document — `dashboard.json` at the root of the state branch:

```jsonc
{
  "generated_at": "2026-07-29T02:16:23Z",  // required: the staleness stamp
  "engine_repo": "owner/repo",             // optional: overrides the meta tag for links
  "tickets": [ /* whole ticket docs, exactly as tickets/<id>/state.json */ ],
  "health":  { /* health/latest.json verbatim */ }
}
```

`tickets` entries are the **unmodified** ticket documents (`schemas/state.schema.json`)
— the run chain, `work_repos`, `block_reason` and per-run `artifacts` are all
read from them. Nothing is precomputed server-side; every view is derived in
the browser.

`GitJsonStateStore.write()` emits this document on every state write
(`engine/dashboard.py`), so the projection is never staler than the branch.
`agent-hq dashboard --state <worktree>` rebuilds it by hand if a branch's
copy goes missing.

## Two rules the code holds to

**Every string in the data is untrusted** — ticket text, block reasons and
artifact paths come from issues and agent output. Nodes are built with
`createElement` + `textContent`; there is no `innerHTML` anywhere. Hrefs are
validated before they are trusted: a PR ref must match `owner/repo#N`, an
artifact path carrying a scheme, a `//` prefix or a `..` segment renders as
plain text rather than a link, and `--tone` is only ever set from a fixed
allowlist keyed by run state, never from data.

**Zero is not free.** `cost_usd: null` / `usage_known: false` means *unmetered*.
Those runs are excluded from every total and counted separately, and the spend
card says so in words.

## Deriving the run chain

The one model easy to get wrong. A logical step is `(parent_run_id, handoff_key)`;
`attempt` is the retry axis inside it. Steps are ordered by `chain_depth` then
first appearance — enqueue order alone puts a depth-8 run *before* a depth-7
retry (ticket 30 does exactly this). `chain_depth` is neither unique nor a row
index, and the same task appears many times, so nothing here assumes a fixed
task sequence.

## Known gaps

- **320 px not verified.** The CSS is there (`auto-fit` grids, a 520 px
  breakpoint, `overflow-wrap: anywhere`) but the narrowest viewport actually
  rendered was the Chrome window minimum, ~500 px.
- **No auto-refresh.** The stamp plus an explicit Refresh button is what the
  requirements ask for; `cache: 'reload'` is the strongest ask available and
  `raw.githubusercontent.com` still serves up to 5 minutes stale.
- Theme choice persists in `localStorage`. That is a per-user preference,
  which §6 lists as a non-goal — kept because the design ships a toggle and
  one that resets on every visit is worse than none.
