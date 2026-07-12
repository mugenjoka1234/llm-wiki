"""Bottom line and overview-theses readability checks (warning level)."""
import shutil
import tempfile
import unittest
from pathlib import Path

from lint_test_utils import make_wiki, page, run_lint

GOOD_BOTTOM = (
    "# Init\n\n## Bottom line\n\nSubscriptions collide with a short need window; "
    "commission on booked care is the survivable model. %%[no-claim]%%\n"
)


class TestReadability(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = make_wiki(Path(self.tmpdir))
        self.w = self.root / "wiki"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_initiative_without_bottom_line_warns(self):
        (self.w / "pricing.md").write_text(page("initiative", "# Init\n\nSome prose.\n"))
        code, out, err = run_lint(self.root)
        self.assertIn("Bottom line", out)
        self.assertEqual(code, 1)

    def test_initiative_with_bottom_line_ok(self):
        (self.w / "pricing.md").write_text(page("initiative", GOOD_BOTTOM))
        code, out, err = run_lint(self.root)
        self.assertNotIn("missing or thin '## Bottom line'", out)

    def test_nav_synthesis_pages_exempt(self):
        (self.w / "glossary.md").write_text(page("synthesis", "# Glossary\n"))
        (self.w / "pricing.md").write_text(page("initiative", GOOD_BOTTOM))
        code, out, err = run_lint(self.root)
        self.assertNotIn("glossary", out)

    def test_overview_without_theses_warns(self):
        (self.w / "overview.md").write_text(
            page("synthesis", "# Overview\n\n## Current theses\n\n<!-- fill in -->\n")
        )
        (self.w / "pricing.md").write_text(page("initiative", GOOD_BOTTOM))
        code, out, err = run_lint(self.root)
        self.assertIn("Current theses", out)

    def test_link_list_only_overview_warns(self):
        (self.w / "overview.md").write_text(page("synthesis", (
            "# Overview\n\n"
            "- [[pricing]]\n"
            "- [Strategy](../../docs/strategy.md)\n"
        )))
        (self.w / "pricing.md").write_text(page("initiative", GOOD_BOTTOM))
        code, out, err = run_lint(self.root)
        self.assertIn("link list", out)

    def test_fresh_scaffold_skips_readability_checks(self):
        # Zero entity pages: only synthesis skeleton. Must stay exit 0.
        (self.w / "overview.md").write_text(
            page("synthesis", "# Overview\n\n- [[index]]\n")
        )
        (self.w / "index.md").write_text(page("synthesis", "# Index\n"))
        code, out, err = run_lint(self.root)
        self.assertEqual(code, 0, f"stdout: {out}\nstderr: {err}")
