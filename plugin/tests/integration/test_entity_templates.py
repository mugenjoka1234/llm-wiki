"""Integration tests for entity templates in assets/entity-templates/.

Tests verify template structure, required frontmatter fields, and the
external-ref field (v1.1 feature — fully landed across all templates as of Wave 2F).

Template inventory (14 total):
  competitor, decision, experiment, feature, initiative, jtbd,
  metric, overview, question, segment, session, source, stub, subdomain-stub
"""
from pathlib import Path
import pytest

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "assets/entity-templates"

# Required frontmatter keys present in every entity template
BASE_REQUIRED_FIELDS = [
    "type:",
    "status:",
    "last-updated:",
    "quarter:",
    "okr:",
    "confidence:",
    "sources:",
    "related:",
    "tags:",
]

# Templates that carry the external-ref field (all 14 as of Wave 2F v1.1 rollout)
EXPECTED_TEMPLATES = {
    "competitor.md",
    "decision.md",
    "experiment.md",
    "feature.md",
    "initiative.md",
    "jtbd.md",
    "metric.md",
    "overview.md",
    "question.md",
    "segment.md",
    "session.md",
    "source.md",
    "stub.md",
    "subdomain-stub.md",
}


def test_template_directory_exists():
    """The entity-templates directory must exist under assets/."""
    assert TEMPLATES_DIR.exists(), f"entity-templates dir not found at {TEMPLATES_DIR}"
    assert TEMPLATES_DIR.is_dir()


def test_expected_template_set():
    """Should have exactly the expected 14 entity templates (no missing, no extras)."""
    actual = {t.name for t in TEMPLATES_DIR.glob("*.md")}
    missing = EXPECTED_TEMPLATES - actual
    extra = actual - EXPECTED_TEMPLATES
    assert not missing, f"Missing expected templates: {sorted(missing)}"
    assert not extra, (
        f"Unexpected templates found: {sorted(extra)}. "
        f"Add them to EXPECTED_TEMPLATES in this test file."
    )


def test_all_templates_have_frontmatter_delimiters():
    """Every template should start with '---' frontmatter delimiters."""
    for t in sorted(TEMPLATES_DIR.glob("*.md")):
        content = t.read_text()
        assert content.startswith("---"), f"{t.name}: does not start with '---' frontmatter"
        assert content.count("---") >= 2, (
            f"{t.name}: missing closing '---' frontmatter delimiter"
        )


def test_all_templates_have_base_required_fields():
    """Every entity template must have the 9 base frontmatter fields."""
    missing_by_template = {}
    for t in sorted(TEMPLATES_DIR.glob("*.md")):
        content = t.read_text()
        missing = [f for f in BASE_REQUIRED_FIELDS if f not in content]
        if missing:
            missing_by_template[t.name] = missing

    assert not missing_by_template, (
        "Templates missing required fields:\n"
        + "\n".join(f"  {name}: {fields}" for name, fields in missing_by_template.items())
    )


def test_entity_templates_have_external_ref():
    """Entity templates (non-subdomain) should have the external-ref field (v1.1 rollout).

    subdomain-stub.md is excluded — it uses source-wiki: instead as it's a
    synthesis page that tracks which parent wiki it mirrors, not an entity ref.
    """
    # subdomain-stub.md uses source-wiki: rather than external-ref
    excluded = {"subdomain-stub.md"}
    missing = []
    for t in sorted(TEMPLATES_DIR.glob("*.md")):
        if t.name in excluded:
            continue
        if "external-ref" not in t.read_text():
            missing.append(t.name)
    assert not missing, (
        f"Templates missing external-ref field: {missing}\n"
        f"Add 'external-ref: \"\"' to each missing template's frontmatter."
    )


def test_stub_template_exists():
    """stub.md must exist — it's the canonical template for cross-wiki stub pages."""
    stub = TEMPLATES_DIR / "stub.md"
    assert stub.exists(), "stub.md not found in entity-templates/"


def test_stub_template_has_tbd_type():
    """stub.md uses 'type: TBD' since its type is resolved at creation time."""
    stub = TEMPLATES_DIR / "stub.md"
    content = stub.read_text()
    assert "type: TBD" in content, "stub.md should have 'type: TBD' as placeholder"


def test_stub_template_has_external_ref():
    """stub.md must have external-ref (its primary purpose is cross-wiki linking)."""
    stub = TEMPLATES_DIR / "stub.md"
    content = stub.read_text()
    assert "external-ref" in content, "stub.md must have external-ref field"


def test_subdomain_stub_template_exists():
    """subdomain-stub.md must exist — used for federation fan-out pages."""
    subdomain = TEMPLATES_DIR / "subdomain-stub.md"
    assert subdomain.exists(), "subdomain-stub.md not found in entity-templates/"


def test_subdomain_stub_has_synthesis_type():
    """subdomain-stub.md is a synthesis page (auto-generated index, not an entity)."""
    subdomain = TEMPLATES_DIR / "subdomain-stub.md"
    content = subdomain.read_text()
    assert "type: synthesis" in content, "subdomain-stub.md should have 'type: synthesis'"


def test_subdomain_stub_has_source_wiki_field():
    """subdomain-stub.md uses source-wiki: (not external-ref) to track its parent wiki."""
    subdomain = TEMPLATES_DIR / "subdomain-stub.md"
    content = subdomain.read_text()
    assert "source-wiki:" in content, (
        "subdomain-stub.md should have 'source-wiki:' field "
        "(tracks which parent wiki the subdomain mirrors)"
    )
