"""Integration tests for lint.py — schema validation, health, unacknowledged digests.

Exit code contract (from lint.py):
  0  = no issues (stdout: "OK: N pages, no issues.")
  1  = warnings only (stale / orphan / unacknowledged — printed to stdout)
  2  = schema errors (printed to stderr)
"""
from datetime import date
import pytest
from pathlib import Path
from conftest import run_lint, _write_synthesis_page

# Use today's date in all test pages so they don't trigger the 90-day stale check.
TODAY = date.today().isoformat()


def _valid_entity_page(type_name: str = "competitor", extra_fields: str = "") -> str:
    """Return a minimal valid entity page frontmatter block.

    confidence: low because sources: [] — source-less pages are capped at
    confidence: low (check_confidence_vs_sources); high/med would be a
    schema error here.
    """
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
        f"{extra_fields}"
        "---\n"
        f"# {type_name.capitalize()}\n"
    )


def test_clean_scaffold_passes_lint(wiki):
    """A freshly scaffolded wiki with no entity pages should exit 0."""
    code, out, err = run_lint(wiki)
    assert code == 0, f"Expected exit 0, got {code}.\nstdout: {out}\nstderr: {err}"
    assert "no issues" in out


def test_missing_type_field_is_schema_error(wiki):
    """A page without the 'type' frontmatter field is a schema error (exit 2, stderr)."""
    bad_page = wiki / "wiki/bad-page.md"
    bad_page.write_text(f"---\nstatus: active\nlast-updated: {TODAY}\n---\n# Bad\n")
    code, out, err = run_lint(wiki)
    assert code == 2, f"Expected exit 2, got {code}.\nstdout: {out}\nstderr: {err}"
    assert "missing required field 'type'" in err


def test_invalid_type_is_schema_error(wiki):
    """A page with a type not in CLAUDE.md or builtins is a schema error (exit 2, stderr)."""
    bad_page = wiki / "wiki/bad-page.md"
    bad_page.write_text(
        f"---\n"
        f"type: invalid-custom-type\n"
        f"status: active\n"
        f"last-updated: {TODAY}\n"
        f"quarter: 2026-Q2\n"
        f"okr: []\n"
        f"confidence: high\n"
        f"sources: []\n"
        f"related: []\n"
        f"tags: []\n"
        f"---\n"
        f"# Bad\n"
    )
    code, out, err = run_lint(wiki)
    assert code == 2, f"Expected exit 2, got {code}.\nstdout: {out}\nstderr: {err}"
    assert "invalid type" in err


def test_valid_custom_type_from_claude_md_passes(wiki):
    """A type listed in CLAUDE.md's ## Entity types section is valid (no schema error)."""
    # CLAUDE.md in the scaffold lists 'competitor' as a valid entity type
    page = wiki / "wiki/shopify-competitor.md"
    page.write_text(_valid_entity_page("competitor"))
    code, out, err = run_lint(wiki)
    # exit 0 (clean) or 1 (orphan warning) are both acceptable — no schema error
    assert code in (0, 1), f"Expected exit 0 or 1, got {code}.\nstdout: {out}\nstderr: {err}"
    assert "invalid type" not in err


def test_unacknowledged_digest_is_warning(wiki):
    """A digest that references an entity but the entity doesn't list it back → exit 1, stdout."""
    entity = wiki / "wiki/shopify-competitor.md"
    entity.write_text(_valid_entity_page("competitor"))

    digest = wiki / "wiki/digests/some-research.md"
    digest.write_text(
        f"---\n"
        f"type: source\n"
        f"status: active\n"
        f"last-updated: {TODAY}\n"
        f"quarter: 2026-Q2\n"
        f"okr: []\n"
        f"confidence: low\n"
        f"sources: []\n"
        f"related:\n"
        f'  - "[[shopify-competitor]]"\n'
        f"tags: []\n"
        f"---\n"
        f"# Research\n"
    )

    code, out, err = run_lint(wiki)
    assert code == 1, f"Expected exit 1 (warning), got {code}.\nstdout: {out}\nstderr: {err}"
    assert "UNACKNOWLEDGED DIGESTS" in out
    assert "shopify-competitor" in out


def test_acknowledged_digest_passes(wiki):
    """Entity that lists the digest in sources: → no unacknowledged warning."""
    entity = wiki / "wiki/shopify-competitor.md"
    entity.write_text(
        f"---\n"
        f"type: competitor\n"
        f"status: active\n"
        f"last-updated: {TODAY}\n"
        f"quarter: 2026-Q2\n"
        f"okr: []\n"
        f"confidence: high\n"
        f"sources:\n"
        f'  - "[[some-research]]"\n'
        f"related: []\n"
        f"tags: []\n"
        f"---\n"
        f"# Shopify\n"
    )

    digest = wiki / "wiki/digests/some-research.md"
    digest.write_text(
        f"---\n"
        f"type: source\n"
        f"status: active\n"
        f"last-updated: {TODAY}\n"
        f"quarter: 2026-Q2\n"
        f"okr: []\n"
        f"confidence: low\n"
        f"sources: []\n"
        f"related:\n"
        f'  - "[[shopify-competitor]]"\n'
        f"tags: []\n"
        f"---\n"
        f"# Research\n"
    )

    code, out, err = run_lint(wiki)
    assert "UNACKNOWLEDGED" not in out, f"Unexpected unacknowledged warning.\nstdout: {out}"


# ── Task 7: Evolution trigger warnings ───────────────────────────────────────

def test_oversize_entity_page_triggers_warning(wiki):
    """An entity page over 12,000 chars triggers an evolution warning (exit 1)."""
    page = wiki / "wiki/shopify-competitor.md"
    big_content = (
        "---\ntype: competitor\nstatus: active\n"
        f"last-updated: {TODAY}\nquarter: 2026-Q2\nokr: []\nconfidence: low\n"
        "sources: []\nrelated: []\ntags: []\n"
        "summary: \"Shopify: 70+ reports all plans; ShopifyQL query language; no Z report present\"\n"
        "---\n# Shopify\n\n"
        + ("x" * 13000)
    )
    page.write_text(big_content)
    code, out, err = run_lint(wiki)
    assert code == 1
    assert "oversize" in out.lower() or "exceeds" in out.lower()


def test_misplaced_research_file_triggers_warning(wiki):
    """A research-* named file in wiki/ root triggers an evolution warning."""
    page = wiki / "wiki/research-some-topic.md"
    page.write_text(
        "---\ntype: source\nstatus: active\n"
        f"last-updated: {TODAY}\nquarter: 2026-Q2\nokr: []\nconfidence: low\n"
        "sources: []\nrelated: []\ntags: []\n"
        'summary: "Research summary about some topic that is long enough to pass"\n'
        "---\n# Research\n"
    )
    code, out, err = run_lint(wiki)
    assert code == 1
    assert "digests" in out.lower()


def test_no_evolution_warnings_on_normal_wiki(wiki):
    """A normal wiki with no oversize pages or misplaced files has no evolution warnings."""
    page = wiki / "wiki/shopify-competitor.md"
    page.write_text(
        "---\ntype: competitor\nstatus: active\n"
        f"last-updated: {TODAY}\nquarter: 2026-Q2\nokr: []\nconfidence: low\n"
        "sources: []\nrelated: []\ntags: []\n"
        'summary: "Shopify: 70+ reports all plans; ShopifyQL query language; no Z report"\n'
        "---\n# Shopify\n\nSome normal content here.\n"
    )
    code, out, err = run_lint(wiki)
    assert "oversize" not in out.lower()
    assert "misplaced" not in out.lower()
