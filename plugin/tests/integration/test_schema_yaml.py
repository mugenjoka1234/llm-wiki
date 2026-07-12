# plugin/tests/integration/test_schema_yaml.py
"""Tests for schema.yaml parsing in lint.py."""
from datetime import date
import pytest
from pathlib import Path
from conftest import run_lint, _write_synthesis_page

TODAY = date.today().isoformat()


def _make_schema_yaml(entity_types: list, domain: str = "test") -> str:
    types_lines = "\n".join(f"  - {t}" for t in entity_types)
    return f"domain: {domain}\nentity_types:\n{types_lines}\n"


def _valid_page(type_name: str) -> str:
    return (
        "---\n"
        f"type: {type_name}\n"
        "status: active\n"
        f"last-updated: {TODAY}\n"
        "quarter: 2026-Q2\n"
        "okr: []\n"
        "confidence: high\n"
        "sources: []\n"
        "related: []\n"
        "tags: []\n"
        "---\n"
        "# Page\n"
    )


def test_schema_yaml_type_accepted(wiki):
    """A type in schema.yaml is accepted even if not in CLAUDE.md."""
    (wiki / "schema.yaml").write_text(_make_schema_yaml(["paper", "author", "construct"]))
    (wiki / "wiki/some-paper.md").write_text(_valid_page("paper"))
    code, out, err = run_lint(wiki)
    assert "invalid type" not in err, f"schema.yaml type was rejected: {err}"


def test_schema_yaml_takes_precedence_over_claude_md(wiki):
    """When schema.yaml exists, CLAUDE.md entity types are ignored."""
    # CLAUDE.md has 'competitor'; schema.yaml does not — competitor should be invalid
    (wiki / "schema.yaml").write_text(_make_schema_yaml(["paper"]))
    (wiki / "wiki/shopify-competitor.md").write_text(_valid_page("competitor"))
    code, out, err = run_lint(wiki)
    assert code == 2, f"competitor not in schema.yaml should be schema error, got {code}"
    assert "invalid type" in err


def test_schema_yaml_synthesis_always_valid(wiki):
    """synthesis type is always valid regardless of schema.yaml contents."""
    (wiki / "schema.yaml").write_text(_make_schema_yaml(["paper"]))
    # index.md is type: synthesis — should not get invalid type error
    code, out, err = run_lint(wiki)
    assert "invalid type 'synthesis'" not in err


def test_no_schema_yaml_falls_back_to_claude_md(wiki):
    """Without schema.yaml, CLAUDE.md entity types are used (existing behavior)."""
    # No schema.yaml in scaffold — CLAUDE.md has competitor, feature, decision
    (wiki / "wiki/shopify-competitor.md").write_text(_valid_page("competitor"))
    code, out, err = run_lint(wiki)
    assert "invalid type" not in err
