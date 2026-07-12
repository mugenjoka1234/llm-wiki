"""Start-here block, sessions section, external deliverables, decision ordering."""
import shutil
import tempfile
import unittest
from pathlib import Path

from lint_test_utils import make_wiki, page, run_lint


class TestIndexLayout(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = make_wiki(Path(self.tmpdir))
        self.w = self.root / "wiki"
        (self.w / "index.md").write_text(page("synthesis", "# Index\n"))
        (self.w / "overview.md").write_text(page("synthesis", "# Overview\n"))
        (self.w / "2026-07-01-old-decision.md").write_text(
            page("decision", "# D1\n", **{"author": "[wren]"})
        )
        (self.w / "2026-07-08-new-decision.md").write_text(
            page("decision", "# D2\n", **{"author": "[juno]"})
        )
        (self.w / "2026-07-08-kickoff.md").write_text(
            page("session", "# S\n", **{"author": "[orchestrator]"})
        )
        (self.w / "brief-stub.md").write_text(
            page("source", "# Stub\n", **{"external-ref": '"~/somewhere/brief.html"'})
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _index(self):
        run_lint(self.root)
        return (self.w / "index.md").read_text()

    def test_start_here_block_present_with_overview_first(self):
        index = self._index()
        self.assertIn("## Start here", index)
        start = index[index.find("## Start here"):index.find("## Agent Catalog")]
        self.assertIn("[[overview]]", start)
        self.assertIn("[[2026-07-08-new-decision]]", start)
        self.assertIn("[[2026-07-08-kickoff]]", start)

    def test_decisions_listed_newest_first_by_filename(self):
        index = self._index()
        self.assertLess(
            index.find("[[2026-07-08-new-decision]]"),
            index.find("[[2026-07-01-old-decision]]"),
        )

    def test_sessions_have_own_section(self):
        index = self._index()
        self.assertIn("### Sessions (1)", index)
        # session must not appear inside a generic "### Sessions"-less entity group
        self.assertNotIn("### Sessions (1)\n\n### ", index)

    def test_external_deliverables_section_with_stub_prefix(self):
        index = self._index()
        self.assertIn("### External deliverables (1)", index)
        self.assertIn("📎 [[brief-stub]]", index)

    def test_start_here_includes_open_question_and_digest(self):
        (self.w / "questions").mkdir(exist_ok=True)
        (self.w / "questions" / "will-parents-pay.md").write_text(
            page("question", "# Q\n", **{"status": "open"})
        )
        (self.w / "digests").mkdir(exist_ok=True)
        (self.w / "digests" / "care-market.md").write_text(page("source", "# D\n"))
        index = self._index()
        start = index[index.find("## Start here"):index.find("## Agent Catalog")]
        self.assertIn("[[will-parents-pay]] — top open question", start)
        self.assertIn("[[care-market]] — newest digest", start)

    def test_start_here_omits_resolved_questions(self):
        (self.w / "questions").mkdir(exist_ok=True)
        (self.w / "questions" / "answered.md").write_text(
            page("question", "# Q\n", **{"status": "resolved"})
        )
        index = self._index()
        start = index[index.find("## Start here"):index.find("## Agent Catalog")]
        self.assertNotIn("top open question", start)
