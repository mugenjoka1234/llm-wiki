"""Confidence-vs-sources, digest naming, stray files, dead refs, health signals."""
import shutil
import tempfile
import unittest
from pathlib import Path

from lint_test_utils import make_wiki, page, run_lint


class TestFilingRules(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = make_wiki(Path(self.tmpdir))
        self.w = self.root / "wiki"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_sourceless_high_confidence_is_error(self):
        (self.w / "acme.md").write_text(page("competitor", **{"confidence": "high"}))
        code, out, err = run_lint(self.root)
        self.assertEqual(code, 2, f"stdout: {out}\nstderr: {err}")
        self.assertIn("capped at confidence: low", err)

    def test_sourceless_low_confidence_ok(self):
        (self.w / "acme.md").write_text(page("competitor", **{"confidence": "low"}))
        code, out, err = run_lint(self.root)
        self.assertNotIn("capped at confidence: low", err)

    def test_synthesis_exempt_from_confidence_rule(self):
        (self.w / "notes.md").write_text(page("synthesis", **{"confidence": "high"}))
        code, out, err = run_lint(self.root)
        self.assertNotIn("capped at confidence: low", err)

    def test_versioned_digest_name_warns(self):
        (self.w / "digests").mkdir()
        (self.w / "digests" / "extra-findings-v0.6.md").write_text(page("source"))
        code, out, err = run_lint(self.root)
        self.assertIn("session/version-based", out)

    def test_stray_root_markdown_warns_but_raw_is_fine(self):
        (self.root / "deep dive on failures.md").write_text("# stray\n")
        (self.root / "raw" / "anything.md").write_text("raw drop, zero ceremony\n")
        code, out, err = run_lint(self.root)
        self.assertIn("STRAY FILES", out)
        self.assertIn("deep dive on failures.md", out)
        self.assertNotIn("anything.md", out)

    def test_readme_claude_not_stray(self):
        (self.root / "README.md").write_text("# readme\n")
        code, out, err = run_lint(self.root)
        self.assertNotIn("STRAY FILES", out)

    def test_dead_related_ref_warns(self):
        (self.w / "acme.md").write_text(
            page("competitor", **{"related": "[ghost-page]"})
        )
        code, out, err = run_lint(self.root)
        self.assertIn("dead related ref 'ghost-page'", out)

    def test_raw_path_refs_not_dead(self):
        (self.w / "acme.md").write_text(
            page("competitor", **{"sources": '["raw/snapshots/x.md"]'})
        )
        code, out, err = run_lint(self.root)
        self.assertNotIn("dead sources ref", out)

    def test_scalar_sources_field_not_iterated_by_char(self):
        (self.w / "acme.md").write_text(page("competitor", **{"sources": "churn-digest"}))
        code, out, err = run_lint(self.root)
        self.assertNotIn("dead sources ref 'c'", out)
        self.assertIn("dead sources ref 'churn-digest'", out)

    def test_health_lists_new_signals_and_stale_pages(self):
        (self.w / "acme.md").write_text(
            page("competitor", **{"last-updated": "2020-01-01", "related": "[ghost]"})
        )
        run_lint(self.root)
        health = (self.w / "_health.md").read_text()
        self.assertIn("Dead refs: 1", health)
        self.assertIn("Stray files: 0", health)
        self.assertIn("Untagged claims: 0", health)
        self.assertIn("## Stale pages", health)
        self.assertIn("acme", health)
