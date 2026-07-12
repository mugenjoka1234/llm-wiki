"""Tests for scripts/resolve_wiki.py. Stdlib only."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "resolve_wiki.py"


class TestCwdDetection(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_wiki(self, path: Path, domain: str = "test") -> None:
        """Create a minimal wiki marker at path."""
        path.mkdir(parents=True, exist_ok=True)
        claude_md = path / "CLAUDE.md"
        claude_md.write_text(
            f"# {domain} Wiki — Schema & Workflows\n\n"
            "## Purpose\n\n"
            f"This wiki is for: {domain}.\n\n"
            "## Entity types\n\ncompetitor, initiative\n"
        )

    def test_cwd_is_wiki_detected(self):
        self._make_wiki(self.root, "research")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--cwd", str(self.root)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        payload = json.loads(result.stdout)
        self.assertEqual(Path(payload["wiki_path"]).resolve(), self.root.resolve())
        self.assertEqual(payload["source"], "cwd")

    def test_cwd_without_wiki_falls_through(self):
        # cwd has no CLAUDE.md; with empty registry, source should be "none"
        registry = self.root / "empty-registry.txt"
        registry.write_text("")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--cwd", str(self.root),
             "--registry", str(registry)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        payload = json.loads(result.stdout)
        self.assertIsNone(payload["wiki_path"])
        self.assertEqual(payload["source"], "none")


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.reg = self.root / "registry.txt"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_wiki(self, path: Path, domain: str = "test") -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "CLAUDE.md").write_text(
            f"# {domain}\n\n## Purpose\n\nTest wiki.\n"
        )

    def test_single_reachable_registry_entry(self):
        wiki = self.root / "research"
        self._make_wiki(wiki, "research")
        self.reg.write_text(f"{wiki}|research|2026-05-06|2026-05-07\n")

        # cwd is NOT the wiki; use a sibling dir
        other = self.root / "other"
        other.mkdir()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--cwd", str(other),
             "--registry", str(self.reg)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        payload = json.loads(result.stdout)
        self.assertEqual(Path(payload["wiki_path"]).resolve(), wiki.resolve())
        self.assertEqual(payload["source"], "registry-unique")

    def test_multiple_reachable_returns_options(self):
        wiki1 = self.root / "research"
        wiki2 = self.root / "notes"
        self._make_wiki(wiki1, "research")
        self._make_wiki(wiki2, "notes")
        self.reg.write_text(
            f"{wiki1}|research|2026-05-06|2026-05-07\n"
            f"{wiki2}|notes|2026-05-06|2026-05-10\n"
        )

        other = self.root / "other"
        other.mkdir()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--cwd", str(other),
             "--registry", str(self.reg)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        payload = json.loads(result.stdout)
        self.assertIsNone(payload["wiki_path"])
        self.assertEqual(payload["source"], "registry-ambiguous")
        self.assertEqual(len(payload["options"]), 2)
        domains = {o["domain"] for o in payload["options"]}
        self.assertEqual(domains, {"research", "notes"})

    def test_unreachable_entry_excluded(self):
        # Registry entry points to a path that doesn't exist
        deleted = self.root / "deleted-wiki"
        self.reg.write_text(f"{deleted}|deleted|2026-05-06|2026-05-07\n")

        other = self.root / "other"
        other.mkdir()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--cwd", str(other),
             "--registry", str(self.reg)],
            capture_output=True, text=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["source"], "none")

    def test_duplicate_entries_latest_wins(self):
        """If registry has multiple lines for same path, latest (last occurrence) is used."""
        wiki = self.root / "research"
        self._make_wiki(wiki, "research")
        self.reg.write_text(
            f"{wiki}|research|2026-05-06|2026-05-06\n"
            f"{wiki}|research|2026-05-06|2026-05-12\n"
        )
        other = self.root / "other"
        other.mkdir()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--cwd", str(other),
             "--registry", str(self.reg)],
            capture_output=True, text=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["source"], "registry-unique")
        # Should have used the latest last-used date
        self.assertEqual(Path(payload["wiki_path"]).resolve(), wiki.resolve())


class TestCompaction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_compaction_keeps_latest_per_path(self):
        reg = self.root / "registry.txt"
        reg.write_text(
            "/a|a|2026-01-01|2026-01-01\n"
            "/b|b|2026-02-01|2026-02-01\n"
            "/a|a|2026-01-01|2026-05-01\n"
            "/b|b|2026-02-01|2026-04-01\n"
            "/a|a|2026-01-01|2026-05-07\n"
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--compact", "--registry", str(reg)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        lines = [l for l in reg.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        self.assertIn("/a|a|2026-01-01|2026-05-07", lines)
        self.assertIn("/b|b|2026-02-01|2026-04-01", lines)

    def test_compaction_preserves_file_on_empty(self):
        reg = self.root / "registry.txt"
        reg.write_text("")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--compact", "--registry", str(reg)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(reg.read_text(), "")


class TestFactoryHomeParsing(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.reg = self.root / "registry.txt"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_wiki(self, path: Path, domain: str = "test") -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "CLAUDE.md").write_text(f"# {domain}\n\n## Purpose\n\nTest wiki.\n")

    def _make_factory_home(self, path: Path) -> None:
        (path / "agents").mkdir(parents=True, exist_ok=True)
        (path / "teams").mkdir(parents=True, exist_ok=True)

    def test_load_registry_skips_factory_home_line(self):
        wiki = self.root / "research"
        self._make_wiki(wiki)
        self.reg.write_text(
            f"!factory_home|{self.root / 'factory'}\n"
            f"{wiki}|research|2026-07-01|2026-07-08\n"
        )
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import resolve_wiki
            entries = resolve_wiki.load_registry(str(self.reg))
        finally:
            sys.path.pop(0)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["domain"], "research")

    def test_load_factory_home_returns_last_line(self):
        self.reg.write_text(
            f"!factory_home|{self.root / 'old-factory'}\n"
            f"!factory_home|{self.root / 'factory'}\n"
        )
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import resolve_wiki
            fh = resolve_wiki.load_factory_home(str(self.reg))
        finally:
            sys.path.pop(0)
        self.assertEqual(fh, str(self.root / "factory"))

    def test_load_factory_home_none_when_absent(self):
        self.reg.write_text("")
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import resolve_wiki
            fh = resolve_wiki.load_factory_home(str(self.reg))
        finally:
            sys.path.pop(0)
        self.assertIsNone(fh)

    def test_is_factory_home(self):
        fh = self.root / "factory"
        self._make_factory_home(fh)
        not_fh = self.root / "plain"
        not_fh.mkdir()
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import resolve_wiki
            self.assertTrue(resolve_wiki.is_factory_home(fh))
            self.assertFalse(resolve_wiki.is_factory_home(not_fh))
        finally:
            sys.path.pop(0)


class TestRegisterFactoryHome(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.reg = self.root / "registry.txt"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_wiki(self, path: Path, domain: str = "test") -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "CLAUDE.md").write_text(f"# {domain}\n\n## Purpose\n\nTest wiki.\n")

    def _make_factory_home(self, path: Path) -> None:
        (path / "agents").mkdir(parents=True, exist_ok=True)
        (path / "teams").mkdir(parents=True, exist_ok=True)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True,
        )

    def test_register_valid_home(self):
        fh = self.root / "factory"
        self._make_factory_home(fh)
        wiki = self.root / "research"
        self._make_wiki(wiki)
        self.reg.write_text(f"{wiki}|research|2026-07-01|2026-07-08\n")

        result = self._run("register-factory-home", str(fh), "--registry", str(self.reg))
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        content = self.reg.read_text()
        self.assertIn(f"!factory_home|{fh.resolve()}", content)
        self.assertIn("research", content)  # wiki entry preserved

    def test_register_replaces_previous_home(self):
        fh1 = self.root / "factory1"
        fh2 = self.root / "factory2"
        self._make_factory_home(fh1)
        self._make_factory_home(fh2)
        self._run("register-factory-home", str(fh1), "--registry", str(self.reg))
        self._run("register-factory-home", str(fh2), "--registry", str(self.reg))
        content = self.reg.read_text()
        self.assertEqual(content.count("!factory_home|"), 1)
        self.assertIn(str(fh2.resolve()), content)

    def test_register_rejects_non_factory_dir(self):
        plain = self.root / "plain"
        plain.mkdir()
        result = self._run("register-factory-home", str(plain), "--registry", str(self.reg))
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a factory home", result.stderr)

    def test_compact_preserves_factory_home_line(self):
        fh = self.root / "factory"
        self._make_factory_home(fh)
        wiki = self.root / "research"
        self._make_wiki(wiki)
        self._run("register-factory-home", str(fh), "--registry", str(self.reg))
        # duplicate wiki entry to give --compact something to do
        with open(self.reg, "a") as f:
            f.write(f"{wiki}|research|2026-07-01|2026-07-07\n")
            f.write(f"{wiki}|research|2026-07-01|2026-07-08\n")
        result = self._run("--compact", "--registry", str(self.reg))
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        content = self.reg.read_text()
        self.assertEqual(content.count("!factory_home|"), 1)
        self.assertEqual(content.count(str(wiki)), 1)

    def test_link_preserves_factory_home_line(self):
        fh = self.root / "factory"
        self._make_factory_home(fh)
        child = self.root / "child"
        parent = self.root / "parent"
        self._make_wiki(child, "child")
        self._make_wiki(parent, "parent")
        self._run("register-factory-home", str(fh), "--registry", str(self.reg))
        result = self._run("link", str(child), str(parent), "--registry", str(self.reg))
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("!factory_home|", self.reg.read_text())


class TestResolveFactoryHome(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.reg = self.root / "registry.txt"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_factory_home(self, path: Path) -> None:
        (path / "agents").mkdir(parents=True, exist_ok=True)
        (path / "teams").mkdir(parents=True, exist_ok=True)

    def _resolve(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "resolve-factory-home",
             "--registry", str(self.reg)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        return json.loads(result.stdout)

    def test_ok_when_registered_and_valid(self):
        fh = self.root / "factory"
        self._make_factory_home(fh)
        self.reg.write_text(f"!factory_home|{fh}\n")
        payload = self._resolve()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(Path(payload["factory_home"]).resolve(), fh.resolve())

    def test_missing_when_registered_but_gone(self):
        gone = self.root / "gone-factory"
        self.reg.write_text(f"!factory_home|{gone}\n")  # never created on disk
        payload = self._resolve()
        self.assertEqual(payload["status"], "missing")
        self.assertIn("register-factory-home", payload["hint"])
        self.assertEqual(payload["factory_home"], str(gone))

    def test_absent_when_never_registered(self):
        self.reg.write_text("")
        payload = self._resolve()
        self.assertEqual(payload["status"], "absent")
        self.assertIsNone(payload["factory_home"])
        self.assertIn("register-factory-home", payload["hint"])


PROJECT_CONFIG_BLOCK = """
## Project config

```yaml
docs_path: ../docs
docs_ignore:
  - node_modules
  - mockups
```
"""


class TestDocsPath(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.project = self.root / "project"
        self.wiki = self.project / "research"
        self.wiki.mkdir(parents=True)
        (self.project / "docs").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write_claude_md(self, extra: str = "") -> None:
        (self.wiki / "CLAUDE.md").write_text(
            "# research\n\n## Purpose\n\nTest wiki.\n" + extra
        )

    def _get_docs_path(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--get-docs-path", str(self.wiki)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        return result.stdout.strip()

    def test_relative_docs_path_resolves_against_wiki_root(self):
        self._write_claude_md(PROJECT_CONFIG_BLOCK)
        out = self._get_docs_path()
        self.assertEqual(Path(out).resolve(), (self.project / "docs").resolve())

    def test_absolute_docs_path_passes_through(self):
        abs_docs = str((self.project / "docs").resolve())
        block = f"\n## Project config\n\n```yaml\ndocs_path: {abs_docs}\n```\n"
        self._write_claude_md(block)
        out = self._get_docs_path()
        self.assertEqual(Path(out).resolve(), (self.project / "docs").resolve())

    def test_empty_when_no_config_block(self):
        self._write_claude_md()
        self.assertEqual(self._get_docs_path(), "")

    def test_parse_project_config_ignore_list(self):
        self._write_claude_md(PROJECT_CONFIG_BLOCK)
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import resolve_wiki
            cfg = resolve_wiki.parse_project_config(self.wiki)
        finally:
            sys.path.pop(0)
        self.assertEqual(cfg["docs_path"], "../docs")
        self.assertEqual(cfg["docs_ignore"], ["node_modules", "mockups"])

    def test_resolve_docs_path_helper(self):
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import resolve_wiki
            # Unset -> None.
            self.assertIsNone(
                resolve_wiki.resolve_docs_path(self.wiki, {"docs_path": None}))
            # Relative -> resolved against wiki_root.
            self.assertEqual(
                resolve_wiki.resolve_docs_path(self.wiki, {"docs_path": "../docs"}),
                (self.project / "docs").resolve())
            # Absolute -> passes through unchanged.
            abs_docs = str((self.project / "docs").resolve())
            self.assertEqual(
                resolve_wiki.resolve_docs_path(self.wiki, {"docs_path": abs_docs}),
                Path(abs_docs))
        finally:
            sys.path.pop(0)


class TestRegistryWriteHelper(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        self.reg = self.root / "registry.txt"

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_wiki(self, path: Path, domain: str = "test") -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "CLAUDE.md").write_text(f"# {domain}\n\n## Purpose\n\nTest wiki.\n")

    def _make_factory_home(self, path: Path) -> None:
        (path / "agents").mkdir(parents=True, exist_ok=True)
        (path / "teams").mkdir(parents=True, exist_ok=True)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--registry", str(self.reg)],
            capture_output=True, text=True,
        )

    def test_register_link_compact_roundtrip(self):
        """All three rewrite paths agree: home first, entries preserved, no dupes."""
        fh = self.root / "factory"
        self._make_factory_home(fh)
        child = self.root / "child"
        parent = self.root / "parent"
        self._make_wiki(child, "child")
        self._make_wiki(parent, "parent")
        self._run("register-factory-home", str(fh))
        self._run("link", str(child), str(parent))
        self._run("--compact")
        lines = [l for l in self.reg.read_text().splitlines() if l.strip()]
        self.assertTrue(lines[0].startswith("!factory_home|"))
        self.assertEqual(sum(1 for l in lines if l.startswith("!factory_home|")), 1)
        self.assertEqual(sum(1 for l in lines if str(child) in l and not l.startswith("!")), 1)

    def test_resolve_empty_value_factory_home_line_is_absent(self):
        self.reg.write_text("!factory_home|\n")
        result = self._run("resolve-factory-home")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "absent")

    def test_register_rejects_partial_factory_home(self):
        partial = self.root / "partial"
        (partial / "agents").mkdir(parents=True)  # no teams/
        result = self._run("register-factory-home", str(partial))
        self.assertEqual(result.returncode, 1)
        self.assertIn("not a factory home", result.stderr)

    def test_resolve_missing_for_partial_factory_home(self):
        partial = self.root / "partial"
        (partial / "agents").mkdir(parents=True)  # no teams/
        self.reg.write_text(f"!factory_home|{partial}\n")
        result = self._run("resolve-factory-home")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "missing")


class TestProjectConfigHardening(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.wiki = Path(self.tmpdir) / "research"
        self.wiki.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _parse(self):
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import resolve_wiki
            return resolve_wiki.parse_project_config(self.wiki)
        finally:
            sys.path.pop(0)

    def test_non_yaml_fence_before_yaml_fence_is_skipped(self):
        (self.wiki / "CLAUDE.md").write_text(
            "# w\n\n## Purpose\n\nx\n\n## Project config\n\n"
            "```bash\ndocs_path: NOT-THIS\n```\n\n"
            "```yaml\ndocs_path: ../docs\n```\n"
        )
        cfg = self._parse()
        self.assertEqual(cfg["docs_path"], "../docs")

    def test_quoted_scalars_are_unquoted(self):
        (self.wiki / "CLAUDE.md").write_text(
            "# w\n\n## Project config\n\n"
            '```yaml\ndocs_path: "../docs"\ndocs_ignore:\n  - "node_modules"\n```\n'
        )
        cfg = self._parse()
        self.assertEqual(cfg["docs_path"], "../docs")
        self.assertEqual(cfg["docs_ignore"], ["node_modules"])


if __name__ == "__main__":
    unittest.main()
