"""CLI-level integration tests for session_ops.py.

Unlike the function-level tests in test_session_ops.py, these drive the
script end-to-end via `subprocess.run([sys.executable, str(SCRIPT), ...])` —
the layer `/session-close` actually calls. They pin the bookkeeping
contract that makes the skill safe to re-run: "a crashed close is fixed by
re-running it; a completed close re-run is a no-op" (spec, verbatim in
plugin/skills/session-close/SKILL.md Step 7).

Env-isolation mirrors test_team_ops_integration.py's pattern: session_ops.py
subcommands don't read CLAUDE_PLUGIN_DATA today (sweep-scan's only registry-
adjacent dependency, resolve_wiki.parse_project_config, reads CLAUDE.md from
the wiki root itself, not the registry) but every subprocess still gets an
explicit, isolated `env=` so the tests stay immune to future subprocess-call
changes and never risk touching a developer machine's real registry.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "session_ops.py"

HEADING = "## What changed this quarter"


def _env(isolation_root: Path) -> dict:
    """Copy of the current environment with CLAUDE_PLUGIN_DATA pinned to an
    isolated temp dir, so subprocess calls never touch the real registry."""
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_DATA"] = str(isolation_root / "plugin-data")
    return env


def _run(*args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )


def _make_wiki(root: Path) -> Path:
    """Fixture wiki with overview.md (quarterly heading) and a pre-existing
    quarterly log file — the two append-once targets session-close touches
    in Step 4. append_once() never mkdir's a missing parent, so the log
    file (and its `wiki/log/` parent) must pre-exist, same as a real wiki
    that has already logged at least one prior entry."""
    wiki_root = root / "wiki-project"
    (wiki_root / "wiki" / "log").mkdir(parents=True)
    (wiki_root / "wiki" / "overview.md").write_text(
        f"# Overview\n\n{HEADING}\n\n- baseline entry\n"
    )
    (wiki_root / "wiki" / "log" / "2026-Q3.md").write_text(
        "# 2026 Q3 Log\n\n"
        "## [2026-07-01 09:00] init — baseline entry | touched: [...] | setup\n"
    )
    return wiki_root


def _make_sweep_fixture(root: Path) -> Path:
    """Minimal sweep-scan fixture: one stray .md outside wiki/raw, one
    unmanifested .md under raw/ (MANIFEST.md exists but never mentions it)."""
    wiki_root = root / "sweep-wiki"
    (wiki_root / "wiki").mkdir(parents=True)
    (wiki_root / "wiki" / "page.md").write_text("# managed page\n")
    (wiki_root / "stray-notes.md").write_text("# stray notes\n")
    (wiki_root / "raw").mkdir()
    (wiki_root / "raw" / "unmanifested.md").write_text("# unmanifested raw drop\n")
    (wiki_root / "raw" / "MANIFEST.md").write_text("# MANIFEST\n\nnothing ingested yet.\n")
    return wiki_root


def _close_calls(wiki_root: Path, factory_home: Path, session_id: str,
                  date: str, env: dict):
    """The three deterministic writes a `/session-close` run performs
    (Steps 4 + 5 of the skill): overview append-once (under the quarterly
    heading), quarterly-log append-once (EOF, no heading), pattern jot."""
    marker = f"<!-- session: {session_id} -->"
    overview = wiki_root / "wiki" / "overview.md"
    log = wiki_root / "wiki" / "log" / "2026-Q3.md"

    overview_result = _run(
        "append-once", str(overview),
        "--marker", marker,
        "--heading", HEADING,
        "--text", f"- did the thing this session {marker}",
        env=env)
    log_result = _run(
        "append-once", str(log),
        "--marker", marker,
        "--text", (f"## [2026-07-11 10:00] session — [[{session_id}]] | "
                    f"touched: [...] | did the thing {marker}"),
        env=env)
    jot_result = _run(
        "jot-append",
        "--home", str(factory_home),
        "--session", session_id,
        "--date", date,
        "--observation", "user always wants concise summaries",
        "--observation", "user dislikes emoji",
        env=env)
    return overview_result, log_result, jot_result


class TestFullCloseBookkeepingRerunNoop(unittest.TestCase):
    """A completed close, re-run with identical inputs, is a no-op: all
    three deterministic files stay byte-identical, and every call reports
    the no-op shape (appended: False / skipped: True)."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_full_close_bookkeeping_rerun_noop(self):
        wiki_root = _make_wiki(self.root)
        factory_home = self.root / "factory-home"
        factory_home.mkdir()
        env = _env(self.root)
        session_id = "2026-07-11-demo"
        date = "2026-07-11"

        overview = wiki_root / "wiki" / "overview.md"
        log = wiki_root / "wiki" / "log" / "2026-Q3.md"
        jsonl = factory_home / "patterns" / "pattern-log.jsonl"

        o1, l1, j1 = _close_calls(wiki_root, factory_home, session_id, date, env)
        self.assertEqual(o1.returncode, 0, o1.stderr)
        self.assertEqual(l1.returncode, 0, l1.stderr)
        self.assertEqual(j1.returncode, 0, j1.stderr)
        self.assertTrue(json.loads(o1.stdout)["appended"])
        self.assertTrue(json.loads(l1.stdout)["appended"])
        self.assertEqual(json.loads(j1.stdout), {"appended": 2, "skipped": False})

        overview_bytes = overview.read_bytes()
        log_bytes = log.read_bytes()
        jsonl_bytes = jsonl.read_bytes()

        # Identical re-run.
        o2, l2, j2 = _close_calls(wiki_root, factory_home, session_id, date, env)
        self.assertEqual(o2.returncode, 0, o2.stderr)
        self.assertEqual(l2.returncode, 0, l2.stderr)
        self.assertEqual(j2.returncode, 0, j2.stderr)
        self.assertEqual(json.loads(o2.stdout), {"appended": False})
        self.assertEqual(json.loads(l2.stdout), {"appended": False})
        self.assertEqual(json.loads(j2.stdout), {"appended": 0, "skipped": True})

        self.assertEqual(overview_bytes, overview.read_bytes())
        self.assertEqual(log_bytes, log.read_bytes())
        self.assertEqual(jsonl_bytes, jsonl.read_bytes())


class TestCrashedCloseResumes(unittest.TestCase):
    """A close that crashes after the overview append but before the log/jot
    writes is fixed by re-running ALL of Steps 4-5: the overview call is now
    a no-op (marker already present, not duplicated), the log and jot calls
    land for the first time, and the final three-file state is byte-for-byte
    identical to a single uninterrupted clean run over the same fixture."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_crashed_close_resumes(self):
        clean_root = self.root / "clean"
        crash_root = self.root / "crash"
        clean_root.mkdir()
        crash_root.mkdir()

        clean_wiki = _make_wiki(clean_root)
        crash_wiki = _make_wiki(crash_root)
        clean_home = clean_root / "factory-home"
        crash_home = crash_root / "factory-home"
        clean_home.mkdir()
        crash_home.mkdir()

        env = _env(self.root)
        session_id = "2026-07-11-crash-demo"
        date = "2026-07-11"
        marker = f"<!-- session: {session_id} -->"

        # Clean fixture: a single, uninterrupted close.
        co, cl, cj = _close_calls(clean_wiki, clean_home, session_id, date, env)
        self.assertEqual(co.returncode, 0, co.stderr)
        self.assertEqual(cl.returncode, 0, cl.stderr)
        self.assertEqual(cj.returncode, 0, cj.stderr)

        # Crash fixture: only the overview append happens ("crash" before
        # the log write), using the exact same call the clean run made.
        crash_overview = crash_wiki / "wiki" / "overview.md"
        first = _run(
            "append-once", str(crash_overview),
            "--marker", marker,
            "--heading", HEADING,
            "--text", f"- did the thing this session {marker}",
            env=env)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(json.loads(first.stdout)["appended"])

        # Resume: re-run ALL of the close's deterministic calls.
        ro, rl, rj = _close_calls(crash_wiki, crash_home, session_id, date, env)
        self.assertEqual(ro.returncode, 0, ro.stderr)
        self.assertEqual(rl.returncode, 0, rl.stderr)
        self.assertEqual(rj.returncode, 0, rj.stderr)
        # The overview write was already satisfied pre-crash -> no-op now,
        # and NOT duplicated.
        self.assertEqual(json.loads(ro.stdout), {"appended": False})
        self.assertTrue(json.loads(rl.stdout)["appended"])
        self.assertEqual(json.loads(rj.stdout), {"appended": 2, "skipped": False})

        crash_overview_text = crash_overview.read_text()
        self.assertEqual(crash_overview_text.count(marker), 1)

        # Final state equals the single-clean-run state, byte-for-byte.
        self.assertEqual(
            (clean_wiki / "wiki" / "overview.md").read_bytes(),
            crash_overview.read_bytes())
        self.assertEqual(
            (clean_wiki / "wiki" / "log" / "2026-Q3.md").read_bytes(),
            (crash_wiki / "wiki" / "log" / "2026-Q3.md").read_bytes())
        self.assertEqual(
            (clean_home / "patterns" / "pattern-log.jsonl").read_bytes(),
            (crash_home / "patterns" / "pattern-log.jsonl").read_bytes())


class TestDegradedHomeJotExit2ButBookkeepingUnaffected(unittest.TestCase):
    """The factory-home jot degrading (home unavailable) is isolated from
    the rest of the close: jot-append exits 2 with a JSON error, but the
    overview and quarterly-log appends still succeed independently — this
    is the skill's DEGRADED-mode contract (Step 0/5 of SKILL.md): nothing
    but the jot depends on the factory home."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_degraded_home_jot_exit_2_but_bookkeeping_unaffected(self):
        wiki_root = _make_wiki(self.root)
        missing_home = self.root / "does-not-exist-home"
        env = _env(self.root)
        session_id = "2026-07-11-degraded"
        date = "2026-07-11"
        marker = f"<!-- session: {session_id} -->"

        jot_result = _run(
            "jot-append",
            "--home", str(missing_home),
            "--session", session_id,
            "--date", date,
            "--observation", "some observation",
            env=env)
        self.assertEqual(jot_result.returncode, 2)
        jot_payload = json.loads(jot_result.stdout)
        self.assertEqual(jot_payload["appended"], 0)
        self.assertIn("error", jot_payload)
        self.assertFalse(missing_home.exists())  # degraded path never creates it

        overview = wiki_root / "wiki" / "overview.md"
        log = wiki_root / "wiki" / "log" / "2026-Q3.md"

        overview_result = _run(
            "append-once", str(overview),
            "--marker", marker,
            "--heading", HEADING,
            "--text", f"- did the thing this session {marker}",
            env=env)
        log_result = _run(
            "append-once", str(log),
            "--marker", marker,
            "--text", (f"## [2026-07-11 10:00] session — [[{session_id}]] | "
                        f"touched: [...] | did the thing {marker}"),
            env=env)

        self.assertEqual(overview_result.returncode, 0, overview_result.stderr)
        self.assertEqual(log_result.returncode, 0, log_result.stderr)
        self.assertTrue(json.loads(overview_result.stdout)["appended"])
        self.assertTrue(json.loads(log_result.stdout)["appended"])
        self.assertIn(marker, overview.read_text())
        self.assertIn(marker, log.read_text())


class TestSweepScanCliShape(unittest.TestCase):
    """sweep-scan's CLI surface: a fixture with one stray and one
    unmanifested raw drop is reported in both lists, exit 0, read-only."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_sweep_scan_cli_shape(self):
        wiki_root = _make_sweep_fixture(self.root)
        env = _env(self.root)

        result = _run("sweep-scan", "--wiki-root", str(wiki_root), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn("stray-notes.md", payload["strays"])
        self.assertIn(str(Path("raw") / "unmanifested.md"), payload["raw_unmanifested"])
        self.assertNotIn("no_manifest", payload)  # MANIFEST.md is present


class TestBreadcrumbAndSessionCheckCli(unittest.TestCase):
    """CLI surface for the unclosed-session detector: `breadcrumb`
    (SessionEnd write) and `session-check` (SessionStart read), the two
    subcommands the hook wrapper (hooks/run-hook.sh) actually invokes."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def _make_wiki(self) -> Path:
        wiki = self.root / "wiki-project"
        wiki.mkdir()
        (wiki / "CLAUDE.md").write_text("# wiki\n\n## Purpose\n\nTest wiki.\n")
        return wiki

    def test_breadcrumb_cli_silent_for_non_wiki_cwd(self):
        env = _env(self.root)
        non_wiki = self.root / "not-a-wiki"
        non_wiki.mkdir()
        result = _run(
            "breadcrumb", "--cwd", str(non_wiki),
            "--session-id", "sess-1", "--date", "2026-07-11",
            env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse((self.root / "plugin-data" / "session-breadcrumbs.jsonl").exists())

    def test_session_check_cli_prints_unclosed_warning(self):
        env = _env(self.root)
        wiki = self._make_wiki()

        breadcrumb_result = _run(
            "breadcrumb", "--cwd", str(wiki),
            "--session-id", "sess-1", "--date", "2026-07-11",
            env=env)
        self.assertEqual(breadcrumb_result.returncode, 0, breadcrumb_result.stderr)

        result = _run("session-check", "--cwd", str(wiki), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            result.stdout.startswith("llm-wiki: unclosed session work detected"),
            result.stdout)

    def test_breadcrumb_crash_contained_when_breadcrumbs_path_is_a_directory(self):
        # Reviewer repro 1: the breadcrumbs path occupied by a DIRECTORY ->
        # open(path, "a") raises. The hook must not break the session: exit
        # 0, empty stdout (stdout can enter session context), one stderr line.
        env = _env(self.root)
        wiki = self._make_wiki()
        (self.root / "plugin-data" / "session-breadcrumbs.jsonl").mkdir(parents=True)
        result = _run(
            "breadcrumb", "--cwd", str(wiki),
            "--session-id", "sess-1", "--date", "2026-07-11",
            env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("llm-wiki hook:", result.stderr)

    def test_session_check_crash_contained_when_breadcrumbs_unreadable(self):
        # Reviewer repro 2: chmod-000 breadcrumbs file -> the read raises
        # PermissionError. Same containment contract: exit 0, empty stdout.
        env = _env(self.root)
        wiki = self._make_wiki()
        data = self.root / "plugin-data"
        data.mkdir(parents=True)
        crumbs = data / "session-breadcrumbs.jsonl"
        crumbs.write_text('{"cwd": "x", "wiki": "%s", "date": "2026-07-11", '
                          '"session_id": "s"}\n' % wiki.resolve())
        crumbs.chmod(0)
        try:
            result = _run("session-check", "--cwd", str(wiki), env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("llm-wiki hook:", result.stderr)
        finally:
            crumbs.chmod(0o644)  # let TemporaryDirectory cleanup succeed


if __name__ == "__main__":
    unittest.main()
