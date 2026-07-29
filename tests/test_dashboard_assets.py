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
