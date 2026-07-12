"""Session type, author requirement, revisit-scheduled status, --migration flag."""
import shutil
import tempfile
import unittest
from pathlib import Path

from lint_test_utils import make_wiki, page, run_lint


class TestSchemaV2(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = make_wiki(Path(self.tmpdir))

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_session_type_is_always_valid(self):
        (self.root / "wiki" / "2026-07-08-kickoff.md").write_text(
            page("session", "# Session\n", **{"author": "[wren]"})
        )
        code, out, err = run_lint(self.root)
        self.assertNotIn("invalid type 'session'", err)
        self.assertNotEqual(code, 2, f"stderr: {err}")

    def test_decision_without_author_is_error(self):
        (self.root / "wiki" / "2026-07-08-pricing.md").write_text(page("decision"))
        code, out, err = run_lint(self.root)
        self.assertEqual(code, 2, f"stdout: {out}\nstderr: {err}")
        self.assertIn("requires non-empty 'author'", err)

    def test_decision_with_author_passes(self):
        (self.root / "wiki" / "2026-07-08-pricing.md").write_text(
            page("decision", **{"author": "[wren, juno]"})
        )
        code, out, err = run_lint(self.root)
        self.assertNotEqual(code, 2, f"stderr: {err}")

    def test_migration_downgrades_author_error_to_warning(self):
        (self.root / "wiki" / "2026-07-08-pricing.md").write_text(page("decision"))
        code, out, err = run_lint(self.root, "--migration")
        self.assertEqual(code, 1, f"stdout: {out}\nstderr: {err}")
        self.assertIn("MIGRATION-DEFERRED", out)
        self.assertIn("requires non-empty 'author'", out)

    def test_revisit_scheduled_status_is_valid(self):
        (self.root / "wiki" / "2026-07-08-pricing.md").write_text(
            page("decision", **{"author": "[wren]", "status": "revisit-scheduled"})
        )
        code, out, err = run_lint(self.root)
        self.assertNotIn("invalid status", err)
        self.assertNotEqual(code, 2, f"stderr: {err}")
