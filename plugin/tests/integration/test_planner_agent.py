"""Planner agent output validation + frontmatter checks."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.parent
VALIDATE = PLUGIN_ROOT / "scripts/validate_agent_output.py"


def _validate(agent: str, content: str) -> int:
    return subprocess.run(
        ["python3", str(VALIDATE), "--agent", agent, "--content", "-"],
        input=content, text=True, capture_output=True
    ).returncode


def test_planner_valid_plan_passes():
    content = '<wiki-plan>[{"url": "https://a.com", "why": "x", "recency": "m"}]</wiki-plan>'
    assert _validate("planner", content) == 0


def test_planner_missing_envelope_fails():
    assert _validate("planner", "just some text") == 1


def test_planner_empty_array_fails():
    assert _validate("planner", "<wiki-plan>[]</wiki-plan>") == 1


def test_planner_items_without_url_fail():
    assert _validate("planner", '<wiki-plan>[{"why": "no url"}]</wiki-plan>') == 1


import re

AGENT = PLUGIN_ROOT / "agents/wiki-planner.md"


def _frontmatter(path: Path) -> str:
    text = path.read_text()
    m = re.search(r"^---\n(.*?)\n---", text, re.DOTALL)
    return m.group(1) if m else ""


def test_planner_agent_exists_and_is_haiku():
    assert AGENT.is_file()
    fm = _frontmatter(AGENT)
    assert "claude-haiku-4-5" in fm
    assert "WebSearch" in fm
    # Planner searches but does not fetch bodies: WebFetch must not be an
    # allowed tool (it may appear in disallowedTools).
    tools_line = next((l for l in fm.splitlines() if l.startswith("tools:")), "")
    assert "WebFetch" not in tools_line


def test_researcher_with_need_more_still_valid():
    body = ("<wiki-output>\n# R\n## Sources\n- [T](https://a.com)\n"
            "## What I could NOT find\n- x\n## Confidence note\nok\n</wiki-output>\n"
            '<need-more queries="[\'more\']"/>')
    assert _validate("researcher", body) == 0
