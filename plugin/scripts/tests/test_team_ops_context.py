import tempfile
import unittest
from pathlib import Path

from scripts import team_ops
from scripts.tests.team_test_utils import (
    DECISION_WITH_POSITION,
    make_wiki_with_positions,
)

PERSONA_WITH_DOMAIN = """---
name: {name}
role: {role}
domain: [{domain}]
version: v1.0
---

# {name} — {role}

## Identity
{name} is a test persona.

## Immutable Anchors (cannot change)

- Never fabricates data
- **Always attribute claims.** Every claim must carry a source tag per `CITATION_STANDARD.md`.

## Mutable Instructions (can evolve)

- Output format
"""

PERSONA_NO_DOMAIN = """---
name: {name}
role: {role}
version: v1.0
---

# {name} — {role}

## Identity
{name} is a test persona with no domain tags.

## Immutable Anchors (cannot change)

- Never fabricates data
- **Always attribute claims.** Every claim must carry a source tag per `CITATION_STANDARD.md`.

## Mutable Instructions (can evolve)

- Output format
"""


def _write_persona(tmp: Path, template: str, **kwargs) -> Path:
    p = tmp / "ada.md"
    p.write_text(template.format(**kwargs))
    return p


def _find(entries: list[dict], slug: str) -> dict | None:
    wikilink = f"[[{slug}]]"
    for e in entries:
        if e["page"] == wikilink:
            return e
    return None


class TestAssembleContextOrientation(unittest.TestCase):
    def test_orientation_caps_at_five_and_sorts_by_recency(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = make_wiki_with_positions(tmp)
            persona = _write_persona(tmp, PERSONA_WITH_DOMAIN,
                                      name="Ada", role="Lead Tester", domain="pricing")

            result = team_ops.assemble_context(tmp, project, persona)

            wiki_dir = project / "wiki"
            expected = [
                str((wiki_dir / "index.md").resolve()),
                str((wiki_dir / "overview.md").resolve()),
                str((wiki_dir / "entity-7.md").resolve()),
                str((wiki_dir / "entity-6.md").resolve()),
                str((wiki_dir / "entity-5.md").resolve()),
                str((wiki_dir / "entity-4.md").resolve()),
                str((wiki_dir / "entity-3.md").resolve()),
            ]
            self.assertEqual(result["orientation"], expected)
            self.assertEqual(result["warnings"], [])
            self.assertEqual(result["budget"],
                              {"focus_pages": 5, "prior_positions": 10})

    def test_no_domain_tags_means_no_focus_pages(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = make_wiki_with_positions(tmp)
            persona = _write_persona(tmp, PERSONA_NO_DOMAIN, name="Ada", role="Lead Tester")

            result = team_ops.assemble_context(tmp, project, persona)

            wiki_dir = project / "wiki"
            self.assertEqual(result["orientation"], [
                str((wiki_dir / "index.md").resolve()),
                str((wiki_dir / "overview.md").resolve()),
            ])

    def test_missing_overview_warns_not_fails(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = make_wiki_with_positions(tmp)
            (project / "wiki" / "overview.md").unlink()
            persona = _write_persona(tmp, PERSONA_NO_DOMAIN, name="Ada", role="Lead Tester")

            result = team_ops.assemble_context(tmp, project, persona)

            self.assertEqual(result["orientation"],
                              [str((project / "wiki" / "index.md").resolve())])
            self.assertTrue(any("overview.md" in w for w in result["warnings"]),
                             result["warnings"])


class TestAssembleContextPriorPositions(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.project = make_wiki_with_positions(self.tmp)
        self.persona = _write_persona(self.tmp, PERSONA_NO_DOMAIN,
                                       name="Ada", role="Lead Tester")
        self.result = team_ops.assemble_context(self.tmp, self.project, self.persona)

    def tearDown(self):
        self._td.cleanup()

    def test_prior_positions_caps_at_ten_newest_first(self):
        prior = self.result["prior_positions"]
        self.assertEqual(len(prior), team_ops.PRIOR_POSITIONS_LIMIT)
        # Fixture dates: session-01 = 2026-05-14 (newest), decision-13 =
        # 2026-05-13, decision-NN = 2026-05-NN. Newest-first, cap 10 means
        # decision-04..01 fall off the end.
        expected_pages = ["[[session-01]]", "[[decision-13]]"] + [
            f"[[decision-{n:02d}]]" for n in range(12, 4, -1)  # 12..05
        ]
        self.assertEqual([e["page"] for e in prior], expected_pages)
        expected_dates = ["2026-05-14"] + [
            f"2026-05-{n:02d}" for n in range(13, 4, -1)  # 13..05
        ]
        self.assertEqual([e["date"] for e in prior], expected_dates)
        self.assertEqual(prior[0]["type"], "session")

    def test_position_line_is_self_authored_verbatim(self):
        entry = _find(self.result["prior_positions"], "decision-12")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["position"], "- **Ada**: position 12")
        self.assertEqual(entry["type"], "decision")
        self.assertEqual(entry["date"], "2026-05-12")

    def test_missing_position_line_falls_back_to_flagged_summary(self):
        entry = _find(self.result["prior_positions"], "decision-13")
        self.assertIsNotNone(entry)
        self.assertTrue(
            entry["position"].startswith("(no self-authored position recorded) "),
            entry["position"])
        self.assertIn("Pricing bands finalized without a recorded position.",
                       entry["position"])

    def test_author_match_case_insensitive(self):
        # session-01.md has `author: [ada]` (lowercase) in its frontmatter;
        # the persona's frontmatter `name:` is "Ada". The match must still
        # succeed and surface the page in prior_positions.
        entry = _find(self.result["prior_positions"], "session-01")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["position"], "- **ada**: shipped the api scaffold")


class TestRecencySortEdgeCases(unittest.TestCase):
    def test_malformed_date_sorts_last(self):
        # `last-updated: TBD` (the entity-template placeholder) would sort
        # FIRST under a plain reversed string sort ('T' > '2' in ASCII);
        # it must deliberately sort LAST instead.
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            project = tmp / "wiki-project"
            wiki_dir = project / "wiki"
            wiki_dir.mkdir(parents=True)
            (wiki_dir / "decision-old.md").write_text(
                DECISION_WITH_POSITION.format(n=1, date="2020-01-01", author="Ada"))
            (wiki_dir / "decision-tbd.md").write_text(
                DECISION_WITH_POSITION.format(n=2, date="TBD", author="Ada"))
            persona = _write_persona(tmp, PERSONA_NO_DOMAIN,
                                      name="Ada", role="Lead Tester")

            result = team_ops.assemble_context(tmp, project, persona)

            self.assertEqual([e["page"] for e in result["prior_positions"]],
                              ["[[decision-old]]", "[[decision-tbd]]"])


if __name__ == "__main__":
    unittest.main()
