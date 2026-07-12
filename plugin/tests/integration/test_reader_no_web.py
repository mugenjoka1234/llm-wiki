"""The reworked reader must not have web/browser tools."""
from __future__ import annotations

import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.parent
AGENT = PLUGIN_ROOT / "agents/wiki-researcher.md"


def _frontmatter(path: Path) -> str:
    m = re.search(r"^---\n(.*?)\n---", path.read_text(), re.DOTALL)
    return m.group(1) if m else ""


def test_researcher_has_no_web_or_browser_tools():
    fm = _frontmatter(AGENT)
    tools_line = next((l for l in fm.splitlines() if l.startswith("tools:")), "")
    # Web tools must not be ALLOWED (they may appear in disallowedTools).
    for banned in ["WebSearch", "WebFetch"]:
        assert banned not in tools_line, f"{banned} must be removed from reader tools"
    # Browser/Playwright tools must not appear anywhere in the frontmatter.
    for banned in ["browser_navigate", "browser_snapshot", "playwright"]:
        assert banned not in fm.lower(), f"{banned} must be gone from reader frontmatter"
    assert "Read" in tools_line


def test_researcher_body_mentions_snapshots_and_source_url():
    body = AGENT.read_text()
    assert "snapshot" in body.lower()
    assert "source_url" in body
