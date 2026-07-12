import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import team_ops
from scripts.tests.team_test_utils import (
    PERSONA_BODY,
    PERSONA_DENYLIST_HIT,
    PERSONA_FENCED,
    PERSONA_MISSING_CITATION,
    PERSONA_TWO_FENCES,
    PERSONA_WITH_DESCRIPTION,
)


def _write(tmp: Path, name: str, body: str) -> Path:
    p = tmp / name
    p.write_text(body)
    return p


class TestValidatePersona(unittest.TestCase):
    def test_valid_persona_passes(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write(Path(td), "wren.md", PERSONA_WITH_DESCRIPTION.format(
                name="Wren", role="Domain Lead",
                description="Use when testing parser behavior."))
            result = team_ops.validate_persona(path, [])
            self.assertTrue(result["ok"])
            self.assertEqual(result["errors"], [])

    def test_missing_description_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write(Path(td), "wren.md",
                           PERSONA_BODY.format(name="Wren", role="Domain Lead"))
            result = team_ops.validate_persona(path, [])
            self.assertFalse(result["ok"])
            self.assertIn("missing description", result["errors"])

    def test_description_over_600_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            long_description = "Use when " + "x" * 600
            path = _write(Path(td), "wren.md", PERSONA_WITH_DESCRIPTION.format(
                name="Wren", role="Domain Lead", description=long_description))
            result = team_ops.validate_persona(path, [])
            self.assertFalse(result["ok"])
            self.assertTrue(any("600" in e for e in result["errors"]),
                             result["errors"])

    def test_description_not_use_when_is_warning_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write(Path(td), "wren.md", PERSONA_WITH_DESCRIPTION.format(
                name="Wren", role="Domain Lead",
                description="Handles maternal-health domain review."))
            result = team_ops.validate_persona(path, [])
            self.assertTrue(result["ok"], result["errors"])
            self.assertTrue(any("Use when" in w for w in result["warnings"]),
                             result["warnings"])

    def test_missing_citation_anchor_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write(Path(td), "wren.md", PERSONA_MISSING_CITATION.format(
                name="Wren", role="Domain Lead",
                description="Use when testing parser behavior."))
            result = team_ops.validate_persona(path, [])
            self.assertFalse(result["ok"])
            self.assertTrue(any("citation" in e.lower() for e in result["errors"]),
                             result["errors"])

    def test_denylist_hit_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write(Path(td), "wren.md", PERSONA_DENYLIST_HIT.format(
                name="Wren", role="Domain Lead",
                description="Use when testing parser behavior."))
            result = team_ops.validate_persona(path, ["acme-launch"])
            self.assertFalse(result["ok"])
            self.assertIn("denylist: acme-launch", result["errors"])


class TestBuildDenylist(unittest.TestCase):
    def test_build_denylist_includes_registry_project_names(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "factory-home"
            (home / "agents").mkdir(parents=True)
            (home / "teams").mkdir()
            (Path(td) / "registry.txt").write_text(
                f"!factory_home|{home}\n"
                "/tmp/x/acme-research|acme-research|2026-01-01|2026-01-01\n")
            with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": td}):
                names = team_ops.build_denylist(home)
            self.assertIn("acme-research", names)

    def test_build_denylist_reads_project_names_txt(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "factory-home"
            (home / "instructions").mkdir(parents=True)
            (home / "agents").mkdir()
            (home / "teams").mkdir()
            (home / "instructions" / "project-names.txt").write_text(
                "acme-corp\n# a comment line\n\n")
            with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": td}):
                names = team_ops.build_denylist(home)
            self.assertIn("acme-corp", names)
            self.assertNotIn("# a comment line", names)

    def test_short_names_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "factory-home"
            (home / "instructions").mkdir(parents=True)
            (home / "agents").mkdir()
            (home / "teams").mkdir()
            (home / "instructions" / "project-names.txt").write_text("ai\nacme-corp\n")
            with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": td}):
                names = team_ops.build_denylist(home)
            self.assertNotIn("ai", names)
            self.assertIn("acme-corp", names)


class TestUpgradePersona(unittest.TestCase):
    def test_upgrade_adds_description_and_fences(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write(Path(td), "wren.md",
                           PERSONA_BODY.format(name="Wren", role="Domain Lead"))
            result = team_ops.upgrade_persona(path, "Use when testing upgrades.")
            self.assertTrue(result["added_description"])
            self.assertTrue(result["fenced"])
            self.assertTrue(result["changed"])

            text = path.read_text()
            self.assertIn("<!-- IMMUTABLE:BEGIN -->", text)
            self.assertIn("<!-- IMMUTABLE:END -->", text)
            lines = text.splitlines()
            role_idx = next(i for i, l in enumerate(lines) if l.startswith("role:"))
            self.assertTrue(lines[role_idx + 1].startswith("description:"))

            before = path.read_bytes()
            result2 = team_ops.upgrade_persona(path, "Use when testing upgrades.")
            after = path.read_bytes()
            self.assertEqual(result2, {"changed": False, "added_description": False,
                                        "fenced": False})
            self.assertEqual(before, after)

    def test_upgrade_never_touches_existing_description(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write(Path(td), "wren.md", PERSONA_WITH_DESCRIPTION.format(
                name="Wren", role="Domain Lead",
                description="Use when the original description matters."))
            original_text = path.read_text()
            result = team_ops.upgrade_persona(path, "Use when a different text is offered.")
            self.assertFalse(result["added_description"])
            new_text = path.read_text()
            self.assertIn("Use when the original description matters.", new_text)
            self.assertNotIn("Use when a different text is offered.", new_text)
            # Only fencing may have changed the file.
            if not result["fenced"]:
                self.assertEqual(original_text, new_text)

    def test_upgrade_escapes_quotes_in_description(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write(Path(td), "wren.md",
                           PERSONA_BODY.format(name="Wren", role="Domain Lead"))
            description = 'Use when the user says "hello" or asks politely.'
            result = team_ops.upgrade_persona(path, description)
            self.assertTrue(result["added_description"])

            text = path.read_text()
            # Raw line carries the escaped form (valid YAML double-quoted scalar).
            self.assertIn(
                'description: "Use when the user says \\"hello\\" or asks politely."',
                text)
            # Round-trip: the reader unescapes back to the original text.
            self.assertEqual(team_ops._frontmatter_description(text), description)
            # And validation still passes with the description intact.
            check = team_ops.validate_persona(path, [])
            self.assertTrue(check["ok"], check["errors"])
            self.assertEqual(check["warnings"], [])

    def test_upgrade_is_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write(Path(td), "wren.md",
                           PERSONA_BODY.format(name="Wren", role="Domain Lead"))
            team_ops.upgrade_persona(path, "Use when testing atomic writes.")
            leftovers = [p for p in Path(td).iterdir() if ".tmp" in p.name]
            self.assertEqual(leftovers, [])


class TestAnchorsUnchanged(unittest.TestCase):
    """`anchors_unchanged` is the deterministic /improve guard: it verifies
    the fenced Immutable Anchors text is byte-identical before and after an
    edit, regardless of what happened elsewhere in the file."""

    def test_identical_fences_ok(self):
        with tempfile.TemporaryDirectory() as td:
            text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
            original = _write(Path(td), "original.md", text)
            edited = _write(Path(td), "edited.md", text)
            result = team_ops.anchors_unchanged(original, edited)
            self.assertEqual(result, {"ok": True, "reason": None})

    def test_mutable_section_edit_only_ok(self):
        with tempfile.TemporaryDirectory() as td:
            original = _write(Path(td), "original.md", PERSONA_FENCED.format(
                name="Wren", role="Domain Lead", note="v1"))
            edited = _write(Path(td), "edited.md", PERSONA_FENCED.format(
                name="Wren", role="Domain Lead", note="v2 — a completely different note"))
            result = team_ops.anchors_unchanged(original, edited)
            self.assertEqual(result, {"ok": True, "reason": None})

    def test_one_byte_changed_inside_fence_is_not_ok(self):
        with tempfile.TemporaryDirectory() as td:
            original_text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
            edited_text = original_text.replace(
                "Never fabricates data", "Never fabricates dataX")
            original = _write(Path(td), "original.md", original_text)
            edited = _write(Path(td), "edited.md", edited_text)
            result = team_ops.anchors_unchanged(original, edited)
            self.assertFalse(result["ok"])
            self.assertIsNotNone(result["reason"])

    def test_fence_deleted_in_edited_is_not_ok(self):
        with tempfile.TemporaryDirectory() as td:
            original_text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
            edited_text = "\n".join(
                line for line in original_text.splitlines()
                if line.strip() not in (team_ops.IMMUTABLE_BEGIN, team_ops.IMMUTABLE_END))
            original = _write(Path(td), "original.md", original_text)
            edited = _write(Path(td), "edited.md", edited_text)
            result = team_ops.anchors_unchanged(original, edited)
            self.assertEqual(result, {"ok": False, "reason": "edited file removed the fence"})

    def test_unfenced_original_is_not_ok_with_exact_reason(self):
        with tempfile.TemporaryDirectory() as td:
            # PERSONA_BODY has the "## Immutable Anchors" heading but no
            # IMMUTABLE:BEGIN/END markers — an unfenced original.
            original = _write(Path(td), "original.md",
                               PERSONA_BODY.format(name="Wren", role="Domain Lead"))
            edited = _write(Path(td), "edited.md",
                             PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1"))
            result = team_ops.anchors_unchanged(original, edited)
            self.assertEqual(result, {"ok": False, "reason": "original has no fenced anchors"})

    def test_second_of_two_fence_pairs_differs_is_not_ok(self):
        with tempfile.TemporaryDirectory() as td:
            original = _write(Path(td), "original.md", PERSONA_TWO_FENCES.format(
                name="Wren", role="Domain Lead", second_anchor_text="always cites sources"))
            edited = _write(Path(td), "edited.md", PERSONA_TWO_FENCES.format(
                name="Wren", role="Domain Lead", second_anchor_text="sometimes cites sources"))
            result = team_ops.anchors_unchanged(original, edited)
            self.assertFalse(result["ok"])
            self.assertIsNotNone(result["reason"])

    # --- structural-invariant regressions (two demonstrated bypasses) -------

    @staticmethod
    def _fence_block(text: str) -> str:
        """The verbatim BEGIN..END block (markers inclusive) of a
        single-fence persona text."""
        start = text.index(team_ops.IMMUTABLE_BEGIN)
        end = text.index(team_ops.IMMUTABLE_END) + len(team_ops.IMMUTABLE_END)
        return text[start:end]

    def test_relocated_fence_is_not_ok(self):
        """Bypass (a): duplicate the fence verbatim under a DIFFERENT section
        heading and rewrite the original location freely. Pair content is
        byte-equal, so a purely local compare passes — the heading anchor
        must catch the move."""
        with tempfile.TemporaryDirectory() as td:
            original_text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
            fence = self._fence_block(original_text)
            edited_text = original_text.replace(
                fence, "- Rewritten anchors: promises quietly removed.")
            edited_text = edited_text.replace(
                "## Mutable Instructions (can evolve)\n",
                "## Mutable Instructions (can evolve)\n\n" + fence + "\n")
            self.assertIn(fence, edited_text)  # fence bytes survive verbatim

            original = _write(Path(td), "original.md", original_text)
            edited = _write(Path(td), "edited.md", edited_text)
            result = team_ops.anchors_unchanged(original, edited)
            self.assertFalse(result["ok"])
            self.assertIn("moved", result["reason"])

    def test_orphan_begin_appended_to_edited_is_malformed(self):
        """Bypass (b): append a dangling BEGIN plus arbitrary text — it never
        forms a pair, so the pair count stays equal; the balance invariant
        must catch it."""
        with tempfile.TemporaryDirectory() as td:
            original_text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
            edited_text = (original_text + "\n" + team_ops.IMMUTABLE_BEGIN
                           + "\n- Injected instruction outside any real fence.\n")
            original = _write(Path(td), "original.md", original_text)
            edited = _write(Path(td), "edited.md", edited_text)
            result = team_ops.anchors_unchanged(original, edited)
            self.assertEqual(result,
                              {"ok": False, "reason": "malformed fence markers in edited"})

    def test_end_before_begin_in_edited_is_malformed(self):
        with tempfile.TemporaryDirectory() as td:
            original_text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
            edited_text = team_ops.IMMUTABLE_END + "\n" + original_text
            original = _write(Path(td), "original.md", original_text)
            edited = _write(Path(td), "edited.md", edited_text)
            result = team_ops.anchors_unchanged(original, edited)
            self.assertEqual(result,
                              {"ok": False, "reason": "malformed fence markers in edited"})

    def test_nested_begin_in_edited_is_malformed(self):
        with tempfile.TemporaryDirectory() as td:
            original_text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
            edited_text = original_text.replace(
                "- Never fabricates data",
                team_ops.IMMUTABLE_BEGIN + "\n- Never fabricates data")
            original = _write(Path(td), "original.md", original_text)
            edited = _write(Path(td), "edited.md", edited_text)
            result = team_ops.anchors_unchanged(original, edited)
            self.assertEqual(result,
                              {"ok": False, "reason": "malformed fence markers in edited"})

    def test_malformed_original_reported_before_edited(self):
        """A malformed ORIGINAL is reported as such — and checked FIRST, even
        when the edited file is malformed too."""
        with tempfile.TemporaryDirectory() as td:
            base = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
            original_text = base + "\n" + team_ops.IMMUTABLE_BEGIN + "\n"
            edited_text = team_ops.IMMUTABLE_END + "\n" + base
            original = _write(Path(td), "original.md", original_text)
            edited = _write(Path(td), "edited.md", edited_text)
            result = team_ops.anchors_unchanged(original, edited)
            self.assertEqual(result,
                              {"ok": False, "reason": "malformed fence markers in original"})

    def test_two_fences_unchanged_with_mutable_edit_still_ok(self):
        """Positive control: both fences intact under their own headings, only
        prose outside the fences changed — the guard must still pass."""
        with tempfile.TemporaryDirectory() as td:
            original_text = PERSONA_TWO_FENCES.format(
                name="Wren", role="Domain Lead", second_anchor_text="always cites sources")
            edited_text = original_text.replace(
                "- Output format", "- Output format: now with tables and a TL;DR")
            original = _write(Path(td), "original.md", original_text)
            edited = _write(Path(td), "edited.md", edited_text)
            result = team_ops.anchors_unchanged(original, edited)
            self.assertEqual(result, {"ok": True, "reason": None})

    # --- heading-ordinal regressions (third demonstrated bypass) ------------

    def test_duplicate_heading_relocation_is_not_ok(self):
        """Bypass (c): plant a byte-identical DUPLICATE of the anchor heading
        at EOF, move the verbatim fence under it, and gut the real section.
        Heading TEXT compares equal — only the occurrence ordinal (which
        occurrence of that heading text precedes the fence) reveals the
        move."""
        with tempfile.TemporaryDirectory() as td:
            original_text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
            fence = self._fence_block(original_text)
            heading = "## Immutable Anchors (cannot change)"
            # Gut the real section: fence bytes removed, arbitrary text instead.
            edited_text = original_text.replace(
                fence, "- Gutted: the real anchors are gone from this section.")
            # Plant a byte-identical duplicate heading at EOF with the verbatim
            # fence under it.
            edited_text = edited_text + "\n" + heading + "\n\n" + fence + "\n"
            self.assertIn(fence, edited_text)  # fence bytes survive verbatim
            self.assertEqual(edited_text.count(heading), 2)  # duplicate planted

            original = _write(Path(td), "original.md", original_text)
            edited = _write(Path(td), "edited.md", edited_text)
            result = team_ops.anchors_unchanged(original, edited)
            self.assertFalse(result["ok"])
            self.assertIsNotNone(result["reason"])

    def test_duplicate_anchor_heading_added_without_move_is_not_ok(self):
        """A planted duplicate of a fence's anchor heading is itself refused,
        even when the fence has not moved — a second copy of the anchor
        heading with arbitrary text under it is suspicious by construction."""
        with tempfile.TemporaryDirectory() as td:
            original_text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
            edited_text = (original_text
                           + "\n## Immutable Anchors (cannot change)\n\n"
                           + "- Unfenced imposter anchors, freely editable later.\n")
            original = _write(Path(td), "original.md", original_text)
            edited = _write(Path(td), "edited.md", edited_text)
            result = team_ops.anchors_unchanged(original, edited)
            self.assertEqual(result,
                              {"ok": False, "reason": "duplicate anchor heading added"})

    def test_mutable_edit_far_from_fence_still_ok(self):
        """Positive control for the ordinal rules: an edit far from the fence
        (Identity section), heading structure untouched — still ok."""
        with tempfile.TemporaryDirectory() as td:
            original_text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
            edited_text = original_text.replace(
                "Wren is a test persona.",
                "Wren is a test persona with a much richer biography now.")
            original = _write(Path(td), "original.md", original_text)
            edited = _write(Path(td), "edited.md", edited_text)
            result = team_ops.anchors_unchanged(original, edited)
            self.assertEqual(result, {"ok": True, "reason": None})


if __name__ == "__main__":
    unittest.main()
