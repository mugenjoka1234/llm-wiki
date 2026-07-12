"""Trust markup: [verified: date], [hypothesis], [REFUTED] -> trust line + catalog ratio."""
import shutil
import tempfile
import unittest
from pathlib import Path

from lint_test_utils import make_wiki, page, run_lint

BODY = (
    "# Acme\n\n"
    "Night rates are $300-600 [verified: 2026-07-05] [[rates-digest]].\n\n"
    "Booking windows close at 20 weeks [hypothesis].\n\n"
    "~~Traffic is 500K/mo~~ [REFUTED] [[traffic-digest]].\n"
)


class TestTrustLine(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = make_wiki(Path(self.tmpdir))
        self.w = self.root / "wiki"
        (self.w / "rates-digest.md").write_text(page("source", "# D1\n"))
        (self.w / "traffic-digest.md").write_text(page("source", "# D2\n"))
        self.page_path = self.w / "acme.md"
        self.page_path.write_text(
            page("competitor", BODY, **{"sources": '["rates-digest"]', "confidence": "med"})
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_trust_line_upserted_after_h1(self):
        run_lint(self.root)
        text = self.page_path.read_text()
        self.assertIn(
            "> Trust: 1 verified · 1 hypothesis · 1 refuted — last verification pass 2026-07-05",
            text,
        )
        lines = text.splitlines()
        h1 = next(i for i, l in enumerate(lines) if l.startswith("# "))
        self.assertTrue(lines[h1 + 2].startswith("> Trust:"), f"got: {lines[h1:h1+3]}")

    def test_trust_line_idempotent(self):
        run_lint(self.root)
        first = self.page_path.read_text()
        run_lint(self.root)
        second = self.page_path.read_text()
        self.assertEqual(first, second)
        self.assertEqual(second.count("> Trust:"), 1)

    def test_catalog_shows_trust_ratio_instead_of_confidence(self):
        (self.w / "index.md").write_text(page("synthesis", "# Index\n"))
        run_lint(self.root)
        index = (self.w / "index.md").read_text()
        self.assertIn("trust:1✓/1~/1✗", index)
        # the acme line specifically must not carry the flat confidence suffix
        acme_line = next(l for l in index.splitlines() if "[[acme]]" in l)
        self.assertNotIn("confidence:", acme_line)

    def test_page_without_markers_gets_no_trust_line(self):
        clean = self.w / "clean.md"
        clean.write_text(page("competitor", "# Clean\n\nNo claims here at all.\n"))
        run_lint(self.root)
        self.assertNotIn("> Trust:", clean.read_text())

    def test_stale_trust_line_removed_when_markers_gone(self):
        # First run: page has markers, trust line is inserted
        run_lint(self.root)
        text_after_first = self.page_path.read_text()
        self.assertIn("> Trust:", text_after_first)

        # Simulate manual edit: remove all markers, then manually add the trust line back
        # to simulate a stale trust line left over from a previous lint run
        from lint_test_utils import page as mkpage
        body_without_markers = (
            "# Acme\n\n"
            "Night rates are $300-600 [[rates-digest]].\n\n"
            "Booking windows close at 20 weeks.\n"
        )
        page_content = mkpage("competitor", body_without_markers, **{"sources": '["rates-digest"]', "confidence": "med"})
        # Insert a stale trust line after the H1 to simulate a page that had markers before
        lines = page_content.splitlines()
        h1_idx = next(i for i, l in enumerate(lines) if l.startswith("# "))
        lines.insert(h1_idx + 1, "")
        lines.insert(h1_idx + 2, "> Trust: 1 verified · 1 hypothesis · 1 refuted — last verification pass 2026-07-05")
        self.page_path.write_text("\n".join(lines))

        # Second run: should detect zero markers and remove stale trust line
        run_lint(self.root)
        self.assertNotIn("> Trust:", self.page_path.read_text())

    def test_blank_line_ensured_after_trust_line(self):
        tight = self.w / "tight.md"
        from lint_test_utils import page as mkpage
        tight.write_text(mkpage(
            "competitor",
            "# Tight\nRates verified [verified: 2026-07-01] [[rates-digest]].\n",
            **{"sources": '["rates-digest"]', "confidence": "med"},
        ))
        run_lint(self.root)
        lines = tight.read_text().splitlines()
        ti = next(i for i, l in enumerate(lines) if l.startswith("> Trust:"))
        self.assertEqual(lines[ti + 1].strip(), "", f"no blank after trust line: {lines[ti:ti+2]}")

    def test_fenced_trust_example_not_rewritten(self):
        body = (
            "# Doc\n\nMarked claim [verified: 2026-07-01] [[rates-digest]].\n\n"
            "```\n> Trust: 9 verified · 9 hypothesis · 9 refuted\n```\n"
        )
        from lint_test_utils import page as mkpage
        doc = self.w / "doc.md"
        doc.write_text(mkpage("competitor", body, **{"sources": '["rates-digest"]', "confidence": "med"}))
        run_lint(self.root)
        text = doc.read_text()
        self.assertIn("> Trust: 9 verified · 9 hypothesis · 9 refuted", text)  # example untouched
        lines = text.splitlines()
        h1 = next(i for i, l in enumerate(lines) if l.startswith("# "))
        self.assertTrue(lines[h1 + 2].startswith("> Trust: 1 verified"), f"real line missing: {lines[h1:h1+3]}")
