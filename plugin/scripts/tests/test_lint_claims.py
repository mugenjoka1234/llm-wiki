"""Numeric-claim citation gate: coverage tags, allowlist, %%[no-claim]%%, scoping."""
import shutil
import tempfile
import unittest
from pathlib import Path

from lint_test_utils import make_wiki, page, run_lint


class TestClaimGate(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = make_wiki(Path(self.tmpdir))
        self.w = self.root / "wiki"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _entity(self, body):
        (self.w / "acme.md").write_text(page("competitor", body))

    def test_untagged_percentage_is_error(self):
        self._entity("# Acme\n\nChurn is 38.1% among new users.\n")
        code, out, err = run_lint(self.root)
        self.assertEqual(code, 2, f"stdout: {out}\nstderr: {err}")
        self.assertIn("untagged numeric claim", err)

    def test_wikilink_in_paragraph_covers_it(self):
        self._entity("# Acme\n\nChurn is 38.1% among new users [[churn-digest]].\n")
        code, out, err = run_lint(self.root)
        self.assertNotIn("untagged numeric claim", err)

    def test_source_tag_covers_paragraph(self):
        self._entity("# Acme\n\nChurn is 38.1%. [external::web-search] https://x.test/a\n")
        code, out, err = run_lint(self.root)
        self.assertNotIn("untagged numeric claim", err)

    def test_no_claim_marker_suppresses(self):
        self._entity("# Acme\n\nWe list 500 example rows here. %%[no-claim]%%\n")
        code, out, err = run_lint(self.root)
        self.assertNotIn("untagged numeric claim", err)

    def test_dates_versions_years_allowlisted(self):
        self._entity("# Acme\n\nSince 2024-01-15 (v0.6, quarter 2026-Q3, year 2025) nothing changed.\n")
        code, out, err = run_lint(self.root)
        self.assertNotIn("untagged numeric claim", err)

    def test_tables_headings_code_fences_excluded(self):
        self._entity(
            "# Acme has 900 users\n\n"
            "| metric | value |\n|---|---|\n| MRR | $500,000 |\n\n"
            "```\nrevenue = 1200000\n```\n"
        )
        code, out, err = run_lint(self.root)
        self.assertNotIn("untagged numeric claim", err)

    def test_small_bare_integers_not_flagged(self):
        self._entity("# Acme\n\nWe compared 3 options across 12 criteria.\n")
        code, out, err = run_lint(self.root)
        self.assertNotIn("untagged numeric claim", err)

    def test_synthesis_pages_exempt(self):
        (self.w / "notes.md").write_text(
            page("synthesis", "# Notes\n\nRevenue hit $4M with 38% growth.\n")
        )
        code, out, err = run_lint(self.root)
        self.assertNotIn("untagged numeric claim", err)

    def test_migration_downgrades_to_warning(self):
        self._entity("# Acme\n\nChurn is 38.1% among new users.\n")
        code, out, err = run_lint(self.root, "--migration")
        self.assertEqual(code, 1, f"stdout: {out}\nstderr: {err}")
        self.assertIn("untagged numeric claim", out)

    def test_trust_line_never_triggers_claim_gate(self):
        self._entity("# Acme\n\n> Trust: 120 verified · 3 hypothesis · 1 refuted — last verification pass 2026-07-01\n\nProse [[x]].\n")
        code, out, err = run_lint(self.root)
        self.assertNotIn("untagged numeric claim", err + out)
