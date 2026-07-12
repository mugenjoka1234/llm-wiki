"""Integration tests for synthesize --update mode logic.

The synthesize skill's --update mode groups entity pages by type and
uses pluralized section headers (e.g., "competitors", "features").
These tests verify the pluralization rules mirror what the skill produces.
"""
import pytest


def _pluralize(type_name: str) -> str:
    """Mirror the pluralization logic from synthesize/SKILL.md.

    Rules:
      - Types already ending in 's' get 'es' appended (e.g. 'process' → 'processes')
      - All others get 's' appended (e.g. 'competitor' → 'competitors')
      - Hyphenated types get 's' at the end of the full string (e.g. 'use-case' → 'use-cases')
    """
    if type_name.endswith("s"):
        return type_name + "es"
    return type_name + "s"


class TestPluralizationRules:
    def test_competitor_pluralizes(self):
        assert _pluralize("competitor") == "competitors"

    def test_feature_pluralizes(self):
        assert _pluralize("feature") == "features"

    def test_tool_pluralizes(self):
        assert _pluralize("tool") == "tools"

    def test_use_case_pluralizes(self):
        assert _pluralize("use-case") == "use-cases"

    def test_decision_pluralizes(self):
        assert _pluralize("decision") == "decisions"

    def test_initiative_pluralizes(self):
        assert _pluralize("initiative") == "initiatives"

    def test_jtbd_pluralizes(self):
        assert _pluralize("jtbd") == "jtbds"

    def test_metric_pluralizes(self):
        assert _pluralize("metric") == "metrics"

    def test_segment_pluralizes(self):
        assert _pluralize("segment") == "segments"

    def test_experiment_pluralizes(self):
        assert _pluralize("experiment") == "experiments"

    def test_type_ending_in_s_gets_es(self):
        """Types that already end in 's' should get 'es', not just 's'."""
        assert _pluralize("process") == "processes"
        assert _pluralize("analysis") == "analysises"  # per rule, not linguistic correctness

    def test_synthesis_gets_es(self):
        """'synthesis' ends in 's' → 'synthesises' per the rule."""
        assert _pluralize("synthesis") == "synthesises"


class TestSectionHeaderFormat:
    """The --update mode uses '## <Pluralized type>' as section headers."""

    def _section_header(self, type_name: str) -> str:
        """Produce the section header as the synthesize skill would."""
        return f"## {_pluralize(type_name).capitalize()}"

    def test_competitor_section_header(self):
        assert self._section_header("competitor") == "## Competitors"

    def test_feature_section_header(self):
        assert self._section_header("feature") == "## Features"

    def test_decision_section_header(self):
        assert self._section_header("decision") == "## Decisions"

    def test_initiative_section_header(self):
        assert self._section_header("initiative") == "## Initiatives"
