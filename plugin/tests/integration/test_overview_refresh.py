"""Integration tests for overview-refresh skill invariants.

overview-refresh rewrites wiki/overview.md. These tests verify that the
scaffold produces a valid overview.md that passes lint, and that the
required frontmatter fields are present.
"""
from datetime import date
from pathlib import Path
from conftest import run_lint

TODAY = date.today().isoformat()


def test_overview_md_exists_in_scaffold(wiki):
    """Scaffold should include a wiki/overview.md."""
    overview = wiki / "wiki/overview.md"
    assert overview.exists(), "wiki/overview.md missing from scaffold"


def test_overview_has_synthesis_type(wiki):
    """overview.md must declare type: synthesis in frontmatter."""
    overview = wiki / "wiki/overview.md"
    content = overview.read_text()
    assert "type: synthesis" in content, "overview.md missing 'type: synthesis'"


def test_overview_has_as_of_field(wiki):
    """overview.md must have an as-of: field (required for overview-refresh)."""
    overview = wiki / "wiki/overview.md"
    content = overview.read_text()
    assert "as-of:" in content, "overview.md missing 'as-of:' field"


def test_overview_passes_lint(wiki):
    """A freshly scaffolded wiki (with overview.md) should pass lint cleanly."""
    code, out, err = run_lint(wiki)
    assert code == 0, (
        f"Lint failed on clean scaffold with overview.md.\n"
        f"exit: {code}\nstdout: {out}\nstderr: {err}"
    )


def test_overview_survives_rewrite_and_still_passes_lint(wiki):
    """Simulated overview-refresh: rewrite overview.md, then lint should still pass."""
    overview = wiki / "wiki/overview.md"
    # Simulate an overview-refresh rewrite — update date fields to today
    overview.write_text(
        f"---\n"
        f"type: synthesis\n"
        f"status: active\n"
        f"last-updated: {TODAY}\n"
        f"as-of: {TODAY}\n"
        f"quarter: 2026-Q2\n"
        f"okr: []\n"
        f"confidence: high\n"
        f"sources: []\n"
        f"related: []\n"
        f"tags: []\n"
        f"---\n"
        f"# Overview\n\n"
        f"## As of\nRewritten {TODAY}.\n\n"
        f"## Current theses\n- Thesis one.\n"
    )
    code, out, err = run_lint(wiki)
    assert code == 0, (
        f"Lint failed after overview-refresh simulation.\n"
        f"exit: {code}\nstdout: {out}\nstderr: {err}"
    )
