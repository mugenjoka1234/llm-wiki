import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import session_ops

MARK = "<!-- session: 2026-07-11-demo -->"
SCRIPT = Path(__file__).parent.parent / "session_ops.py"


def _build_sweep_wiki(tmp: Path, with_manifest: bool = True) -> Path:
    """Build a fixture wiki + sibling docs dir for sweep_scan tests.

    Layout (wiki_root = tmp/project/research):
      tmp/project/docs/brief.md      -- docs_path file (../docs; never a stray)
      wiki_root/CLAUDE.md            -- ## Project config: docs_path ../docs,
                                         docs_ignore: [node_modules]
      wiki_root/README.md            -- root config file (skip-listed)
      wiki_root/notes.md             -- root stray
      wiki_root/misc/idea.md         -- nested stray
      wiki_root/node_modules/x.md    -- docs_ignore'd dir (not a stray)
      wiki_root/wiki/page.md         -- managed content (never a stray)
      wiki_root/raw/old.md           -- manifested (referenced in MANIFEST.md)
      wiki_root/raw/new-drop.md      -- unmanifested
      wiki_root/raw/MANIFEST.md      -- lists old.md only (omitted when
                                         with_manifest=False)
    """
    project = tmp / "project"
    wiki_root = project / "research"
    (project / "docs").mkdir(parents=True)
    (project / "docs" / "brief.md").write_text("# Brief\n")

    wiki_root.mkdir(parents=True)
    (wiki_root / "CLAUDE.md").write_text(
        "# research\n\n## Purpose\n\nTest wiki.\n\n"
        "## Project config\n\n```yaml\ndocs_path: ../docs\ndocs_ignore:\n"
        "  - node_modules\n```\n"
    )
    (wiki_root / "README.md").write_text("# README\n")
    (wiki_root / "notes.md").write_text("# stray notes\n")
    (wiki_root / "misc").mkdir()
    (wiki_root / "misc" / "idea.md").write_text("# stray idea\n")
    (wiki_root / "node_modules").mkdir()
    (wiki_root / "node_modules" / "x.md").write_text("# ignored\n")
    (wiki_root / "wiki").mkdir()
    (wiki_root / "wiki" / "page.md").write_text("# managed page\n")
    (wiki_root / "raw").mkdir()
    (wiki_root / "raw" / "old.md").write_text("# old raw drop\n")
    (wiki_root / "raw" / "new-drop.md").write_text("# new raw drop\n")
    if with_manifest:
        (wiki_root / "raw" / "MANIFEST.md").write_text(
            "# MANIFEST\n\n- [x] `old.md` — old drop, ingested.\n"
        )
    return wiki_root


class TestAppendOnce(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.f = Path(self.td.name) / "log.md"
        self.f.write_text("# Log\n\n## What changed this quarter\n\n- old entry\n\n## Other\n\nbody\n")

    def tearDown(self):
        self.td.cleanup()

    def test_appends_under_heading_before_next_section(self):
        out = session_ops.append_once(self.f, MARK, f"- new entry {MARK}",
                                      heading="## What changed this quarter")
        self.assertTrue(out["appended"])
        text = self.f.read_text()
        self.assertLess(text.index("- new entry"), text.index("## Other"))
        self.assertGreater(text.index("- new entry"), text.index("- old entry"))

    def test_second_call_is_byte_identical_noop(self):
        session_ops.append_once(self.f, MARK, f"- new entry {MARK}",
                                heading="## What changed this quarter")
        before = self.f.read_bytes()
        out = session_ops.append_once(self.f, MARK, f"- new entry {MARK}",
                                      heading="## What changed this quarter")
        self.assertFalse(out["appended"])
        self.assertEqual(before, self.f.read_bytes())

    def test_marker_must_be_in_text(self):
        with self.assertRaises(ValueError):
            session_ops.append_once(self.f, MARK, "- unmarked entry")

    def test_missing_heading_created_at_eof(self):
        out = session_ops.append_once(self.f, MARK, f"- entry {MARK}",
                                      heading="## Nonexistent")
        self.assertTrue(out["appended"])
        self.assertTrue(out.get("created_heading"))
        self.assertIn("## Nonexistent", self.f.read_text())

    def test_missing_file_created(self):
        g = Path(self.td.name) / "new.md"
        out = session_ops.append_once(g, MARK, f"- entry {MARK}")
        self.assertTrue(out["appended"] and out.get("created"))

    def test_eof_append_no_heading(self):
        out = session_ops.append_once(self.f, MARK, f"- tail entry {MARK}")
        self.assertTrue(out["appended"])
        self.assertTrue(self.f.read_text().rstrip().endswith(MARK))

    def test_no_tmp_leftovers(self):
        session_ops.append_once(self.f, MARK, f"- entry {MARK}")
        self.assertEqual([p for p in Path(self.td.name).iterdir() if ".tmp" in p.name], [])


class TestJotAppend(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.home = Path(self.td.name)
        self.jot = self.home / "patterns" / "pattern-log.jsonl"

    def tearDown(self):
        self.td.cleanup()

    def test_appends_lines_with_exact_schema(self):
        out = session_ops.jot_append(
            self.home, "2026-07-11-demo", "2026-07-11",
            ["user always wants concise summaries", "user dislikes emoji"])
        self.assertEqual(out, {"appended": 2, "skipped": False})
        lines = self.jot.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        for line, obs in zip(lines, ["user always wants concise summaries", "user dislikes emoji"]):
            row = json.loads(line)
            self.assertEqual(set(row.keys()), {"session", "date", "observation", "source"})
            self.assertEqual(row["session"], "2026-07-11-demo")
            self.assertEqual(row["date"], "2026-07-11")
            self.assertEqual(row["observation"], obs)
            self.assertEqual(row["source"], "user-turn")

    def test_rerun_same_session_skips_entirely(self):
        session_ops.jot_append(self.home, "2026-07-11-demo", "2026-07-11", ["first observation"])
        before = self.jot.read_bytes()
        out = session_ops.jot_append(self.home, "2026-07-11-demo", "2026-07-11", ["a different observation"])
        self.assertEqual(out, {"appended": 0, "skipped": True})
        self.assertEqual(before, self.jot.read_bytes())

    def test_different_session_appends(self):
        session_ops.jot_append(self.home, "2026-07-11-demo", "2026-07-11", ["first observation"])
        out = session_ops.jot_append(self.home, "2026-07-12-other", "2026-07-12", ["second observation"])
        self.assertEqual(out, {"appended": 1, "skipped": False})
        lines = self.jot.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        sessions = {json.loads(line)["session"] for line in lines}
        self.assertEqual(sessions, {"2026-07-11-demo", "2026-07-12-other"})

    def test_garbled_line_ignored(self):
        self.jot.parent.mkdir(parents=True, exist_ok=True)
        with open(self.jot, "a") as f:
            f.write("not json\n")
        out = session_ops.jot_append(self.home, "2026-07-11-demo", "2026-07-11", ["clean observation"])
        self.assertEqual(out, {"appended": 1, "skipped": False})
        lines = self.jot.read_text().splitlines()
        self.assertEqual(lines[0], "not json")
        self.assertEqual(len(lines), 2)
        row = json.loads(lines[1])
        self.assertEqual(row["session"], "2026-07-11-demo")

    def test_creates_patterns_dir_and_file(self):
        self.assertFalse(self.jot.parent.exists())
        out = session_ops.jot_append(self.home, "2026-07-11-demo", "2026-07-11", ["first observation"])
        self.assertEqual(out, {"appended": 1, "skipped": False})
        self.assertTrue(self.jot.is_file())

    def test_no_trailing_newline_normalized(self):
        self.jot.parent.mkdir(parents=True, exist_ok=True)
        seeded = json.dumps({"session": "2026-07-10-seeded", "date": "2026-07-10",
                             "observation": "seeded line", "source": "user-turn"})
        self.jot.write_text(seeded)  # NO trailing newline
        out = session_ops.jot_append(self.home, "2026-07-11-demo", "2026-07-11", ["new observation"])
        self.assertEqual(out, {"appended": 1, "skipped": False})
        lines = self.jot.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        # BOTH lines must parse independently — no concatenation.
        self.assertEqual(json.loads(lines[0])["session"], "2026-07-10-seeded")
        self.assertEqual(json.loads(lines[1])["session"], "2026-07-11-demo")
        # Dedup for the ORIGINAL seeded session must still work after the append.
        out2 = session_ops.jot_append(self.home, "2026-07-10-seeded", "2026-07-10", ["dupe"])
        self.assertEqual(out2, {"appended": 0, "skipped": True})

    def test_zero_observations_no_side_effects(self):
        out = session_ops.jot_append(self.home, "2026-07-11-demo", "2026-07-11", [])
        self.assertEqual(out, {"appended": 0, "skipped": False})
        self.assertFalse(self.jot.parent.exists())

    def test_personas_key_written_when_given(self):
        out = session_ops.jot_append(
            self.home, "2026-07-11-demo", "2026-07-11",
            ["observation about wren"], personas=["wren"])
        self.assertEqual(out, {"appended": 1, "skipped": False})
        row = json.loads(self.jot.read_text().splitlines()[0])
        self.assertEqual(row["personas"], ["wren"])

    def test_personas_key_omitted_when_absent(self):
        out = session_ops.jot_append(
            self.home, "2026-07-11-demo", "2026-07-11", ["general observation"])
        self.assertEqual(out, {"appended": 1, "skipped": False})
        row = json.loads(self.jot.read_text().splitlines()[0])
        self.assertNotIn("personas", row)

    def test_phase4_schema_lines_still_dedup(self):
        # A pre-existing 4-key (no "personas") line for a session must still
        # trigger the dedup skip for that session — backward compat with
        # jot lines written before this field existed.
        self.jot.parent.mkdir(parents=True, exist_ok=True)
        seeded = json.dumps({"session": "2026-07-10-seeded", "date": "2026-07-10",
                             "observation": "seeded line", "source": "user-turn"})
        self.jot.write_text(seeded + "\n")
        out = session_ops.jot_append(self.home, "2026-07-10-seeded", "2026-07-10", ["dupe"])
        self.assertEqual(out, {"appended": 0, "skipped": True})

    def test_missing_home_exit_2(self):
        missing_home = self.home / "does-not-exist"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "jot-append",
             "--home", str(missing_home),
             "--session", "2026-07-11-demo",
             "--date", "2026-07-11",
             "--observation", "first observation"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["appended"], 0)

    def test_cli_appends_and_reports_json(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "jot-append",
             "--home", str(self.home),
             "--session", "2026-07-11-demo",
             "--date", "2026-07-11",
             "--observation", "first observation",
             "--observation", "second observation"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        payload = json.loads(result.stdout)
        self.assertEqual(payload, {"appended": 2, "skipped": False})
        lines = self.jot.read_text().splitlines()
        self.assertEqual(len(lines), 2)


class TestSweepScan(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.tmp = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_root_and_nested_strays_found(self):
        wiki_root = _build_sweep_wiki(self.tmp)
        out = session_ops.sweep_scan(wiki_root)
        self.assertIn("notes.md", out["strays"])
        self.assertIn(str(Path("misc") / "idea.md"), out["strays"])

    def test_docs_path_and_ignores_excluded(self):
        wiki_root = _build_sweep_wiki(self.tmp)
        out = session_ops.sweep_scan(wiki_root)
        self.assertNotIn(str(Path("node_modules") / "x.md"), out["strays"])
        self.assertFalse(any("brief.md" in s for s in out["strays"]))
        self.assertEqual(Path(out["docs_path"]).resolve(),
                          (wiki_root.parent / "docs").resolve())

    def test_config_files_not_strays(self):
        wiki_root = _build_sweep_wiki(self.tmp)
        (wiki_root / "GEMINI.md").write_text("# gemini\n")
        (wiki_root / "AGENTS.md").write_text("# agents\n")
        out = session_ops.sweep_scan(wiki_root)
        for name in ("CLAUDE.md", "README.md", "GEMINI.md", "AGENTS.md"):
            self.assertNotIn(name, out["strays"])

    def test_unmanifested_raw_listed(self):
        wiki_root = _build_sweep_wiki(self.tmp)
        out = session_ops.sweep_scan(wiki_root)
        self.assertIn(str(Path("raw") / "new-drop.md"), out["raw_unmanifested"])

    def test_manifested_raw_not_listed(self):
        wiki_root = _build_sweep_wiki(self.tmp)
        out = session_ops.sweep_scan(wiki_root)
        self.assertNotIn(str(Path("raw") / "old.md"), out["raw_unmanifested"])

    def test_missing_manifest_flags_all(self):
        wiki_root = _build_sweep_wiki(self.tmp, with_manifest=False)
        out = session_ops.sweep_scan(wiki_root)
        self.assertEqual(
            set(out["raw_unmanifested"]),
            {str(Path("raw") / "old.md"), str(Path("raw") / "new-drop.md")})
        self.assertTrue(out.get("no_manifest"))

    def test_manifest_substring_is_not_a_match(self):
        # `a.md` is a substring of `data.md` — bare substring matching would
        # silently treat a.md as manifested. Word-boundary matching must not.
        wiki_root = _build_sweep_wiki(self.tmp)
        (wiki_root / "raw" / "a.md").write_text("# tiny drop\n")
        (wiki_root / "raw" / "data.md").write_text("# data drop\n")
        (wiki_root / "raw" / "MANIFEST.md").write_text(
            "# MANIFEST\n\n- [x] `data.md` — data drop, ingested.\n"
            "- [x] `old.md` — old drop, ingested.\n"
        )
        out = session_ops.sweep_scan(wiki_root)
        self.assertIn(str(Path("raw") / "a.md"), out["raw_unmanifested"])
        self.assertNotIn(str(Path("raw") / "data.md"), out["raw_unmanifested"])

    def test_underscore_dirs_not_strays(self):
        wiki_root = _build_sweep_wiki(self.tmp)
        (wiki_root / "_templates").mkdir()
        (wiki_root / "_templates" / "x.md").write_text("# template\n")
        (wiki_root / "_drafts").mkdir()
        (wiki_root / "_drafts" / "y.md").write_text("# draft\n")
        out = session_ops.sweep_scan(wiki_root)
        self.assertFalse(any(s.startswith("_templates") for s in out["strays"]))
        self.assertFalse(any(s.startswith("_drafts") for s in out["strays"]))
        # Positive control: a genuine stray in the same run is still detected.
        self.assertIn("notes.md", out["strays"])

    def test_wiki_own_docs_dir_not_strays(self):
        wiki_root = _build_sweep_wiki(self.tmp)
        (wiki_root / "docs").mkdir()
        (wiki_root / "docs" / "schema-decisions.md").write_text("# ADR log\n")
        out = session_ops.sweep_scan(wiki_root)
        self.assertFalse(any(s.startswith("docs") for s in out["strays"]))
        # Positive control: a genuine stray in the same run is still detected.
        self.assertIn(str(Path("misc") / "idea.md"), out["strays"])

    def test_read_only(self):
        wiki_root = _build_sweep_wiki(self.tmp)

        def snapshot():
            return {p: p.read_bytes() for p in wiki_root.rglob("*") if p.is_file()}

        before = snapshot()
        session_ops.sweep_scan(wiki_root)
        after = snapshot()
        self.assertEqual(before, after)


class TestBreadcrumb(unittest.TestCase):
    """record_breadcrumb: SessionEnd's write side. Wiki resolution mirrors
    resolve_wiki's own cwd-then-registry logic (is_wiki(cwd) first); the
    breadcrumbs file lives alongside registry.txt in the same
    CLAUDE_PLUGIN_DATA-derived data dir, which is what makes this trivial to
    isolate per-test."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.tmp = Path(self.td.name)
        self.data_dir = self.tmp / "plugin-data"
        self.wiki = self.tmp / "wiki-project"
        self.wiki.mkdir(parents=True)
        (self.wiki / "CLAUDE.md").write_text("# wiki\n\n## Purpose\n\nTest wiki.\n")
        self.breadcrumbs = self.data_dir / "session-breadcrumbs.jsonl"
        self.env_patch = mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.data_dir)})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.td.cleanup()

    def test_no_wiki_silent_and_not_recorded(self):
        non_wiki = self.tmp / "not-a-wiki"
        non_wiki.mkdir()
        result = session_ops.record_breadcrumb(non_wiki, "sess-1", "2026-07-11")
        self.assertEqual(result, {"recorded": False, "reason": "no wiki"})
        self.assertFalse(self.breadcrumbs.exists())

    def test_wiki_resolved_line_appended_with_all_keys(self):
        result = session_ops.record_breadcrumb(self.wiki, "sess-1", "2026-07-11")
        self.assertTrue(result["recorded"])
        lines = self.breadcrumbs.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        row = json.loads(lines[0])
        self.assertEqual(set(row.keys()), {"cwd", "wiki", "date", "session_id"})
        self.assertEqual(row["cwd"], str(self.wiki.resolve()))
        self.assertEqual(row["wiki"], str(self.wiki.resolve()))
        self.assertEqual(row["date"], "2026-07-11")
        self.assertEqual(row["session_id"], "sess-1")

    def test_appends_accumulate(self):
        session_ops.record_breadcrumb(self.wiki, "sess-1", "2026-07-11")
        session_ops.record_breadcrumb(self.wiki, "sess-2", "2026-07-12")
        lines = self.breadcrumbs.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["session_id"], "sess-1")
        self.assertEqual(json.loads(lines[1])["session_id"], "sess-2")

    def _register(self, wiki: Path):
        """Write a registry.txt in the isolated data dir with `wiki` as its
        single entry — the exact shape resolve_wiki.load_registry reads."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "registry.txt").write_text(
            f"{wiki.resolve()}|test-wiki|2026-01-01|2026-01-01\n")

    def test_unrelated_cwd_not_resolved_via_registry(self):
        # The user's real state: exactly one registered wiki. A cwd with NO
        # path relationship to it must never be attributed to that wiki —
        # hooks in unrelated projects must produce zero noise.
        self._register(self.wiki)
        unrelated = self.tmp / "unrelated-project"
        unrelated.mkdir()
        result = session_ops.record_breadcrumb(unrelated, "sess-1", "2026-07-11")
        self.assertEqual(result, {"recorded": False, "reason": "no wiki"})
        self.assertFalse(self.breadcrumbs.exists())

    def test_cwd_above_wiki_resolves(self):
        # cwd is an ancestor of the registered wiki (e.g. a project root
        # above its nested research/ wiki) -> resolves to that wiki.
        self._register(self.wiki)
        result = session_ops.record_breadcrumb(self.tmp, "sess-1", "2026-07-11")
        self.assertTrue(result["recorded"])
        self.assertEqual(result["wiki"], str(self.wiki.resolve()))

    def test_cwd_inside_wiki_resolves(self):
        # cwd is a descendant of the registered wiki -> resolves to it.
        self._register(self.wiki)
        sub = self.wiki / "raw"
        sub.mkdir()
        result = session_ops.record_breadcrumb(sub, "sess-1", "2026-07-11")
        self.assertTrue(result["recorded"])
        self.assertEqual(result["wiki"], str(self.wiki.resolve()))

    def test_breadcrumbs_trimmed_after_1000_lines(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.breadcrumbs, "w") as f:
            for i in range(1000):
                f.write(json.dumps({"cwd": "x", "wiki": "y",
                                    "date": "2026-01-01",
                                    "session_id": f"old-{i}"}) + "\n")
        session_ops.record_breadcrumb(self.wiki, "newest", "2026-07-11")
        lines = self.breadcrumbs.read_text().splitlines()
        self.assertEqual(len(lines), 500)
        self.assertEqual(json.loads(lines[-1])["session_id"], "newest")
        # The kept tail is the NEWEST 500 lines of the post-append file.
        self.assertEqual(json.loads(lines[0])["session_id"], "old-501")


class TestSessionCheck(unittest.TestCase):
    """session_check: SessionStart's read side. Compares the newest
    breadcrumb date for this wiki against the newest wiki/sessions/*.md
    page date (filename-prefix parsed); breadcrumb newer -> unclosed."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.tmp = Path(self.td.name)
        self.data_dir = self.tmp / "plugin-data"
        self.wiki = self.tmp / "wiki-project"
        self.wiki.mkdir(parents=True)
        (self.wiki / "CLAUDE.md").write_text("# wiki\n\n## Purpose\n\nTest wiki.\n")
        self.breadcrumbs = self.data_dir / "session-breadcrumbs.jsonl"
        self.env_patch = mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.data_dir)})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.td.cleanup()

    def test_no_wiki_silent(self):
        non_wiki = self.tmp / "not-a-wiki"
        non_wiki.mkdir()
        result = session_ops.session_check(non_wiki)
        self.assertEqual(result, {"status": "no-wiki"})

    def test_unrelated_cwd_with_registered_wiki_is_no_wiki(self):
        # Registered wiki + a cwd with no path relationship to it: the
        # session-check must stay silent, not nag the unrelated project.
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "registry.txt").write_text(
            f"{self.wiki.resolve()}|test-wiki|2026-01-01|2026-01-01\n")
        session_ops.record_breadcrumb(self.wiki, "sess-1", "2026-07-11")
        unrelated = self.tmp / "unrelated-project"
        unrelated.mkdir()
        result = session_ops.session_check(unrelated)
        self.assertEqual(result, {"status": "no-wiki"})

    def test_breadcrumb_newer_than_session_page_is_unclosed(self):
        (self.wiki / "wiki" / "sessions").mkdir(parents=True)
        (self.wiki / "wiki" / "sessions" / "2026-07-10-earlier.md").write_text("# session\n")
        session_ops.record_breadcrumb(self.wiki, "sess-1", "2026-07-11")
        result = session_ops.session_check(self.wiki)
        self.assertEqual(result["status"], "unclosed")
        self.assertEqual(result["last_activity"], "2026-07-11")
        self.assertEqual(result["last_close"], "2026-07-10")

    def test_session_page_same_or_newer_is_closed_and_silent(self):
        (self.wiki / "wiki" / "sessions").mkdir(parents=True)
        (self.wiki / "wiki" / "sessions" / "2026-07-11-closed.md").write_text("# session\n")
        session_ops.record_breadcrumb(self.wiki, "sess-1", "2026-07-11")
        result = session_ops.session_check(self.wiki)
        self.assertEqual(result["status"], "closed")

    def test_no_sessions_dir_with_breadcrumb_is_unclosed(self):
        session_ops.record_breadcrumb(self.wiki, "sess-1", "2026-07-11")
        result = session_ops.session_check(self.wiki)
        self.assertEqual(result["status"], "unclosed")
        self.assertIsNone(result["last_close"])

    def test_no_breadcrumb_at_all_is_closed(self):
        (self.wiki / "wiki" / "sessions").mkdir(parents=True)
        result = session_ops.session_check(self.wiki)
        self.assertEqual(result["status"], "closed")

    def test_garbled_breadcrumb_lines_skipped(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with open(self.breadcrumbs, "a") as f:
            f.write("not json\n")
        session_ops.record_breadcrumb(self.wiki, "sess-1", "2026-07-11")
        result = session_ops.session_check(self.wiki)
        self.assertEqual(result["status"], "unclosed")
        self.assertEqual(result["last_activity"], "2026-07-11")
