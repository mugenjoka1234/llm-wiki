"""Shared helpers for lint.py tests. Stdlib only.

Note: page() defaults to confidence: low with sources: [] — from Task 4 on,
empty sources + high/med confidence is an ERROR for entity pages, so the
neutral default for tests is low. Override per test when needed.
"""
import subprocess
import sys
from datetime import date
from pathlib import Path

LINT = Path(__file__).resolve().parents[2] / "assets" / "scripts" / "lint.py"
TODAY = date.today().isoformat()


def make_wiki(root: Path) -> Path:
    """Minimal valid wiki root: wiki/ dir + CLAUDE.md with Purpose + entity types."""
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    (root / "raw").mkdir(exist_ok=True)
    (root / "CLAUDE.md").write_text(
        "# test wiki\n\n## Purpose\n\nTest wiki.\n\n## Entity types\n\n"
        "- competitor\n- initiative\n- segment\n- decision\n- question\n- source\n"
    )
    return root


def page(type_name: str = "competitor", body: str = "# Page\n", **overrides) -> str:
    """A valid page. Overrides replace frontmatter values verbatim (strings)."""
    fm = {
        "type": type_name,
        "status": "active",
        "last-updated": TODAY,
        "quarter": "2026-Q3",
        "okr": "[]",
        "confidence": "low",
        "sources": "[]",
        "related": "[]",
        "tags": "[]",
        "summary": '"A sufficiently long one-line summary of what this page answers."',
    }
    fm.update(overrides)
    fm_lines = "\n".join(f"{k}: {v}" for k, v in fm.items())
    return f"---\n{fm_lines}\n---\n{body}"


def run_lint(root: Path, *flags):
    r = subprocess.run(
        [sys.executable, str(LINT), "--wiki-root", str(root), *flags],
        capture_output=True, text=True,
    )
    return r.returncode, r.stdout, r.stderr
