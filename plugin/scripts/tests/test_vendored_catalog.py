"""Vendored agency-agents catalog: presence, frontmatter, attribution, layout.

Stdlib only. Exercises the *synced output*, not the sync script itself — the
script is run for real (network, maintainer-only) to populate
plugin/assets/agency-agents/, and these tests verify what landed.
"""
import re
import unittest
from pathlib import Path

CATALOG_ROOT = Path(__file__).resolve().parents[2] / "assets" / "agency-agents"
ATTRIBUTION = CATALOG_ROOT / "ATTRIBUTION.md"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _catalog_md_files():
    if not CATALOG_ROOT.is_dir():
        return []
    return [
        p
        for p in CATALOG_ROOT.rglob("*.md")
        if p.name != "ATTRIBUTION.md"
    ]


class TestCatalogPresent(unittest.TestCase):
    def test_catalog_present_and_large(self):
        files = _catalog_md_files()
        self.assertGreaterEqual(
            len(files),
            250,
            f"expected >=250 vendored agent files, found {len(files)}",
        )


class TestCatalogFrontmatter(unittest.TestCase):
    def test_catalog_files_have_parseable_frontmatter(self):
        failures = []
        for path in _catalog_md_files():
            text = path.read_text(encoding="utf-8")
            m = FRONTMATTER_RE.match(text)
            if not m:
                failures.append(f"{path}: no frontmatter block")
                continue
            block = m.group(1)
            if not re.search(r"^name:\s*\S", block, re.MULTILINE):
                failures.append(f"{path}: missing 'name:' in frontmatter")
            if not re.search(r"^description:\s*\S", block, re.MULTILINE):
                failures.append(f"{path}: missing 'description:' in frontmatter")
        self.assertEqual(failures, [])


class TestAttribution(unittest.TestCase):
    def test_attribution_present(self):
        self.assertTrue(ATTRIBUTION.is_file(), "ATTRIBUTION.md missing")
        text = ATTRIBUTION.read_text(encoding="utf-8")
        self.assertIn("MIT", text)
        self.assertIn("msitarzewski/agency-agents", text)
        self.assertRegex(
            text,
            r"\b\d{4}-\d{2}-\d{2}\b",
            "expected a sync date (YYYY-MM-DD) in ATTRIBUTION.md",
        )


class TestDivisionIsDirectory(unittest.TestCase):
    def test_division_is_directory(self):
        for path in _catalog_md_files():
            rel = path.relative_to(CATALOG_ROOT)
            self.assertGreaterEqual(
                len(rel.parts),
                2,
                f"{rel} has no division directory component",
            )


if __name__ == "__main__":
    unittest.main()
