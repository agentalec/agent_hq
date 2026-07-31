"""The dashboard's untrusted-data invariant, enforced the way this repo
enforces its others (`tests/test_task_library.py` bans concrete adapter names
the same way).

`docs/dashboard-design-requirements.md` §4.4: every string in the state is
untrusted — ticket text, block reasons and artifact paths are issue and agent
output. The whole defence is that the page never mounts an HTML string, so a
`<script>` in a spec can only ever become text. That is a property of the
source, so it is checkable from Python without a JS runtime.
"""

import re
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard"

# Every API that turns a string into markup. `insertAdjacentText` and
# `textContent` are fine and deliberately absent.
FORBIDDEN = re.compile(
    r"\b(innerHTML|outerHTML|insertAdjacentHTML|document\.write|createContextualFragment)\b"
)
# `new Function` / `eval` would let artifact content become code.
FORBIDDEN_EVAL = re.compile(r"\beval\s*\(|new\s+Function\s*\(")


def _sources() -> list[Path]:
    files = sorted(DASHBOARD.glob("*.js")) + sorted(DASHBOARD.glob("*.html"))
    assert files, "dashboard sources not found"
    return files


def _code(path: Path) -> str:
    """Source with comments removed — the rule is about what the page *does*,
    and `markdown.js` explains at length why it doesn't use innerHTML. Only
    `/* */` blocks and whole-line `//` are stripped, so a `https://` inside a
    string literal survives.
    """
    text = re.sub(r"/\*.*?\*/", "", path.read_text(), flags=re.DOTALL)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))


def test_no_source_mounts_an_html_string():
    offenders = {
        path.name: FORBIDDEN.findall(_code(path)) for path in _sources() if FORBIDDEN.search(_code(path))
    }
    assert not offenders, (
        f"dashboard builds markup from a string: {offenders}. Artifact and ticket text is "
        "agent-written; build DOM nodes with createElement/textContent instead."
    )


def test_no_source_evaluates_a_string():
    offenders = [path.name for path in _sources() if FORBIDDEN_EVAL.search(_code(path))]
    assert not offenders, f"dashboard evaluates a string: {offenders}"


def test_markdown_renderer_loads_before_the_app_that_calls_it():
    """`app.js` calls `window.AgentHqMarkdown` at render time; both are plain
    classic scripts, so source order is the whole dependency mechanism."""
    html = (DASHBOARD / "index.html").read_text()
    assert html.index("markdown.js") < html.index("app.js")


def test_engine_repo_is_configured():
    """The page fails closed without it, so an empty meta ships a dead site."""
    html = (DASHBOARD / "index.html").read_text()
    match = re.search(r'name="agent-hq:engine-repo"\s+content="([^"]*)"', html)
    assert match, "index.html must carry the agent-hq:engine-repo meta tag"
    assert re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", match.group(1))


def test_run_chain_orders_by_queue_position_not_array_or_depth():
    """`queue_seq` is the queue's order, and the chain view has to use it.

    Depth stopped being an ordering axis once one run could declare several
    entries -- they share the declaring run's depth + 1, so every comparison
    tied and the tiebreak decided the order. Array order is wrong for a
    different reason: a retry inherits the position of the attempt it replaces,
    so it can belong EARLIER than a run appended after that attempt failed.

    Source-level, like the other rules here -- the dashboard is deliberately
    testable without a JS runtime.
    """
    code = _code(DASHBOARD / "app.js")
    assert "queue_seq" in code, "the chain view must read queue_seq"
    assert re.search(r"order\.sort\(.*?a\.pos\s*-\s*b\.pos", code, re.DOTALL), (
        "steps() must sort by queue position"
    )
    assert "firstIndex" not in code, (
        "array-appearance order is no longer a valid tiebreak -- a retry can sit "
        "earlier in the queue than a run appended after it"
    )


def test_cancelled_entries_are_rendered_as_a_distinct_state():
    """A cancelled entry is planned-then-dropped work, and the only place the
    ledger shows a route CHANGING rather than progressing. It must not fall
    through to the generic muted default with no explanation."""
    code = _code(DASHBOARD / "app.js")
    assert "CANCELLED" in code, "the chain view must know the CANCELLED state"
    assert "cancelled before it ran" in code
    assert ".step-note" in (DASHBOARD / "app.css").read_text()


def test_fixture_exercises_the_queue_fields():
    """The fixture is what a developer sees on `localhost` (README), so it has
    to actually contain the shapes the new rendering exists for -- otherwise
    the local page silently stops covering them."""
    import json

    tickets = json.loads((DASHBOARD / "fixture.json").read_text())["tickets"]
    runs = [r for t in tickets for r in t.get("runs", [])]

    assert any("queue_seq" in r for r in runs), "no run carries queue_seq"
    assert any(r.get("state") == "CANCELLED" for r in runs), "no cancelled entry"
    # The whole point of the split: whoever enqueued a run need not be whose
    # output it read.
    split = [
        r for r in runs
        if r.get("input_from_run_id") and r["input_from_run_id"] != r.get("parent_run_id")
    ]
    assert split, "no run where input_from_run_id differs from parent_run_id"
    # A pre-declared queue: several entries from one enqueuer at one depth,
    # distinguished only by queue_seq.
    by_parent: dict[str, list[dict]] = {}
    for r in runs:
        if r.get("parent_run_id"):
            by_parent.setdefault(r["parent_run_id"], []).append(r)
    assert any(
        len({r["queue_seq"] for r in group if "queue_seq" in r}) > 1
        and len({r.get("chain_depth") for r in group}) == 1
        for group in by_parent.values()
    ), "no ticket shows a multi-entry queue declared by one run"
