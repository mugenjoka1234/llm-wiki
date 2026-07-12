# plugin/tests/integration/test_summary_field.py
"""Tests for summary: field validation in lint.py."""
from datetime import date
import pytest
from pathlib import Path
from conftest import run_lint, _write_synthesis_page

TODAY = date.today().isoformat()


def _entity_page_without_summary(type_name: str = "competitor") -> str:
    return (
        "---\n"
        f"type: {type_name}\n"
        "status: active\n"
        f"last-updated: {TODAY}\n"
        "quarter: 2026-Q2\n"
        "okr: []\n"
        "confidence: low\n"
        "sources: []\n"
        "related: []\n"
        "tags: []\n"
        "---\n"
        "# Test Entity\n"
    )


def _entity_page_with_summary(summary: str, type_name: str = "competitor") -> str:
    return (
        "---\n"
        f"type: {type_name}\n"
        "status: active\n"
        f"last-updated: {TODAY}\n"
        "quarter: 2026-Q2\n"
        "okr: []\n"
        "confidence: low\n"
        "sources: []\n"
        "related: []\n"
        "tags: []\n"
        f"summary: \"{summary}\"\n"
        "---\n"
        "# Test Entity\n"
    )


def test_missing_summary_produces_warning_not_error(wiki):
    """Missing summary: is a warning (exit 1), not a schema error (exit 2)."""
    page = wiki / "wiki/shopify-competitor.md"
    page.write_text(_entity_page_without_summary())
    code, out, err = run_lint(wiki)
    assert code == 1, f"Expected exit 1 (warning), got {code}.\nstdout: {out}\nstderr: {err}"
    assert "summary" in out.lower()
    assert "summary" not in err.lower()  # NOT a schema error


def test_short_summary_produces_warning(wiki):
    """A summary under 40 chars is a warning."""
    page = wiki / "wiki/shopify-competitor.md"
    page.write_text(_entity_page_with_summary("Too short"))
    code, out, err = run_lint(wiki)
    assert code == 1, f"Expected exit 1, got {code}.\nstdout: {out}\nstderr: {err}"
    assert "summary" in out.lower()


def test_adequate_summary_no_warning(wiki):
    """A summary of 40+ chars with entity name produces no summary warning."""
    page = wiki / "wiki/shopify-competitor.md"
    long_summary = "Shopify: 70+ reports on all plans; ShopifyQL query language; no Z report"
    page.write_text(_entity_page_with_summary(long_summary))
    code, out, err = run_lint(wiki)
    # exit 1 is acceptable (orphan warning), but no summary warning
    assert "summary" not in out.lower(), f"Unexpected summary warning: {out}"


def test_synthesis_pages_exempt_from_summary(wiki):
    """Synthesis pages (index, overview, _health) do not need summary:."""
    # The scaffold already has synthesis pages without summary: — they must pass clean
    code, out, err = run_lint(wiki)
    assert code == 0, f"Scaffold should pass clean, got {code}.\nstdout: {out}\nstderr: {err}"
