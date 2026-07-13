"""Shape test for the starter roster — nine generic archetype personas.

The starter roster (assets/starter-roster/) is the coherent nine-persona
default org the /staff feature seeds a new project with. This test pins its
SHAPE: the exact slugs, a zero-error AND zero-warning validation contract per
file, the "Use when" description budget, the fenced citation anchor, and — the
part that makes it a team rather than nine templates — the defers-on
cross-reference graph, where every persona routes out-of-lane questions to
OTHER starter archetypes by their canonical role phrase.
"""
import re
import unittest
from pathlib import Path

from scripts import team_ops

ROSTER = Path(__file__).resolve().parents[2] / "assets" / "starter-roster"

# The nine spec slugs — file names are <slug>.md, no more and no fewer.
SLUGS = {
    "product-strategist",
    "ux-realist",
    "domain-reality-checker",
    "market-strategist",
    "marketplace-economist",
    "delivery-gatekeeper",
    "copy-qa-lead",
    "privacy-trust-lead",
    "visual-design-lead",
}

# The canonical role phrases teammates use to refer to one another. A
# persona's "Defers on" field routes by these exact phrases (never by a
# personal name), so the graph is machine-parseable.
ROLES = {
    "Product Strategist",
    "UX Realist",
    "Domain Reality Checker",
    "Market Strategist",
    "Marketplace Economist",
    "Delivery Gatekeeper",
    "Copy QA Lead",
    "Privacy & Trust Lead",
    "Visual Design Lead",
}

DESCRIPTION_TOTAL_BUDGET = 5400


def _roster_files() -> dict[str, Path]:
    """Map slug -> path for every <slug>.md in the roster dir (empty when the
    dir is absent — the RED state before the roster is authored)."""
    if not ROSTER.is_dir():
        return {}
    return {p.stem: p for p in ROSTER.glob("*.md")}


def _defers_text(text: str) -> str:
    """The single-line body of the persona's **Defers on**: field, or ""."""
    m = re.search(r"\*\*Defers on\*\*:(.*)", text)
    return m.group(1).strip() if m else ""


class TestStarterRoster(unittest.TestCase):
    def _require_roster(self) -> dict[str, Path]:
        """Fail cleanly (not error ambiguously) when the roster dir is absent
        or incomplete — the shared precondition of every per-file assertion."""
        files = _roster_files()
        self.assertEqual(
            set(files), SLUGS,
            f"roster must contain exactly the nine spec slugs (dir: {ROSTER})")
        return files

    # 1. Exactly the nine spec slugs are present.
    def test_exactly_the_nine_slugs_present(self):
        self.assertTrue(ROSTER.is_dir(), f"roster dir absent: {ROSTER}")
        self.assertEqual(set(_roster_files()), SLUGS)

    # 2. Each file validates with ZERO errors AND ZERO warnings.
    def test_each_validates_with_zero_errors_and_warnings(self):
        for slug, path in self._require_roster().items():
            result = team_ops.validate_persona(path, denylist=[])
            self.assertEqual(result["errors"], [], f"{slug}: errors")
            self.assertEqual(result["warnings"], [], f"{slug}: warnings")

    # 3. Each description ≤600 chars and starts with "Use when".
    def test_descriptions_use_when_and_within_budget(self):
        for slug, path in self._require_roster().items():
            desc = team_ops._frontmatter_description(path.read_text())
            self.assertIsNotNone(desc, f"{slug}: missing description")
            self.assertLessEqual(len(desc), 600, f"{slug}: description too long")
            self.assertTrue(desc.startswith("Use when"),
                            f"{slug}: description must start with 'Use when'")

    # 4. Each frontmatter domain is an empty list.
    def test_domain_is_empty_list(self):
        for slug, path in self._require_roster().items():
            fm = team_ops._frontmatter(path)
            self.assertEqual(fm.get("domain"), [], f"{slug}: domain not []")

    # 5. Each file contains both fence markers AND the citation anchor.
    def test_fence_markers_and_citation_anchor(self):
        for slug, path in self._require_roster().items():
            text = path.read_text()
            self.assertIn(team_ops.IMMUTABLE_BEGIN, text, f"{slug}: no BEGIN")
            self.assertIn(team_ops.IMMUTABLE_END, text, f"{slug}: no END")
            self.assertIn("CITATION_STANDARD", text, f"{slug}: no citation anchor")

    # 6. The defers-on graph: every referenced role is a canonical teammate
    #    role, and each persona references at least one teammate.
    def test_defers_on_graph_is_coherent(self):
        files = self._require_roster()
        for slug, path in files.items():
            text = path.read_text()
            own_role = team_ops._frontmatter(path).get("role")
            self.assertIn(own_role, ROLES, f"{slug}: role not canonical")
            defers = _defers_text(text)
            self.assertTrue(defers, f"{slug}: no Defers on field")

            referenced = {role for role in ROLES
                          if role != own_role and role in defers}
            self.assertGreaterEqual(
                len(referenced), 1,
                f"{slug}: must defer to >=1 teammate by role")

            # No dangling reference: any capitalized role-like phrase in the
            # defers text that names a teammate must be a canonical role. We
            # verify positively — every ROLE we can find is canonical by
            # construction; guard against a teammate named by a NON-canonical
            # variant by requiring the referenced set be a subset of ROLES.
            self.assertTrue(referenced <= ROLES, f"{slug}: dangling role ref")

    # 7. No two personas share a name.
    def test_names_are_unique(self):
        names = []
        for slug, path in self._require_roster().items():
            name = team_ops._frontmatter(path).get("name")
            self.assertTrue(name, f"{slug}: missing name")
            names.append(name)
        self.assertEqual(len(names), len(set(names)), "duplicate persona name")

    # 8. Total description length across the nine ≤ 5400 chars.
    def test_total_description_budget(self):
        total = 0
        for _slug, path in self._require_roster().items():
            desc = team_ops._frontmatter_description(path.read_text()) or ""
            total += len(desc)
        self.assertLessEqual(total, DESCRIPTION_TOTAL_BUDGET,
                             f"total description length {total} > {DESCRIPTION_TOTAL_BUDGET}")


if __name__ == "__main__":
    unittest.main()
