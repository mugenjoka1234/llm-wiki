"""Shared pytest fixtures for llm-wiki integration tests."""
import os
import shutil
import subprocess
import json
from pathlib import Path
import pytest

PLUGIN_ROOT = Path(__file__).parent.parent.parent  # ~/llm-wiki/plugin/
LINT = PLUGIN_ROOT / "assets/scripts/lint.py"
RESOLVE = PLUGIN_ROOT / "scripts/resolve_wiki.py"


@pytest.fixture
def tmp_registry(tmp_path, monkeypatch):
    """Override CLAUDE_PLUGIN_DATA to an isolated tmp directory."""
    registry_dir = tmp_path / "plugin_data"
    registry_dir.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(registry_dir))
    return registry_dir


@pytest.fixture
def wiki(tmp_path, tmp_registry):
    """Scaffold a minimal valid wiki at tmp_path/test-wiki/, register it, return the path."""
    wiki_path = tmp_path / "test-wiki"
    wiki_path.mkdir()
    _scaffold_wiki(wiki_path, domain="test", purpose="Test wiki for integration tests")
    # Register in isolated registry
    from datetime import date
    today = date.today().isoformat()
    registry = tmp_registry / "registry.txt"
    registry.write_text(f"{wiki_path}|test|{today}|{today}\n")
    return wiki_path


def _scaffold_wiki(wiki_path: Path, domain: str, purpose: str):
    """Create a minimal valid wiki scaffold for testing."""
    # Directory structure
    for d in ["raw/_ingest", "raw/snapshots", "wiki/log", "wiki/digests",
              "wiki/_drafts", "wiki/_archive", "wiki/_pii", "_templates", "scripts"]:
        (wiki_path / d).mkdir(parents=True, exist_ok=True)

    # Copy lint script so wiki can run it from scripts/lint.py
    shutil.copy(LINT, wiki_path / "scripts/lint.py")

    # CLAUDE.md — must have ## Purpose and ## Entity types sections
    (wiki_path / "CLAUDE.md").write_text(f"""# {domain} Wiki

## Purpose
{purpose}

## Entity types
- competitor
- feature
- decision
- source
""")

    # Use today's date so pages don't trigger the 90-day stale check
    from datetime import date
    today = date.today().isoformat()
    _write_synthesis_page(wiki_path / "wiki/index.md", today)
    _write_synthesis_page(wiki_path / "wiki/overview.md", today)
    _write_synthesis_page(wiki_path / "wiki/_health.md", today)

    # wiki/log/2026-Q2.md
    (wiki_path / "wiki/log/2026-Q2.md").write_text(f"""---
type: synthesis
status: active
last-updated: {today}
as-of: {today}
quarter: 2026-Q2
okr: []
confidence: high
sources: []
related: []
tags: [log]
---
# Log — 2026-Q2
""")

    # raw/MANIFEST.md
    (wiki_path / "raw/MANIFEST.md").write_text("# Manifest\n\n---\n")


def _write_synthesis_page(path: Path, today: str):
    path.write_text(f"""---
type: synthesis
status: active
last-updated: {today}
as-of: {today}
quarter: 2026-Q2
okr: []
confidence: high
sources: []
related: []
tags: []
---
# {path.stem}
""")


def run_lint(wiki_path: Path, *args) -> tuple[int, str, str]:
    """Run lint.py and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        ["python3", str(wiki_path / "scripts/lint.py"), *args],
        capture_output=True, text=True, cwd=wiki_path
    )
    return result.returncode, result.stdout, result.stderr


def run_resolve(wiki_path: Path, *args) -> tuple[int, str]:
    """Run resolve_wiki.py and return (exit_code, stdout)."""
    env = os.environ.copy()
    result = subprocess.run(
        ["python3", str(RESOLVE), *args],
        capture_output=True, text=True, env=env
    )
    return result.returncode, result.stdout.strip()
