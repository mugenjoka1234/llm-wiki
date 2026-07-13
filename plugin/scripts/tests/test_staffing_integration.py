"""End-to-end integration tests for the guided-staffing machinery (Tasks 1-5),
driven through the CLI via subprocess — the same layer a real caller (the
future /staff skill) hits. Stdlib only; no PyYAML, no pytest.

Three scenarios, per the plan's Task 6 brief:
  (a) TestFullLayeredRoundtrip — the complete layered-persona lifecycle: a
      base persona in the factory home, a project-copy persona with
      provenance frontmatter mentioning its own project, validate-persona
      --project exempting the copy's own-project mention, resolve-team
      --wiki-root resolving the copy (layer=project, no drift yet), an edit
      to the base persona triggering a drift_notice on the next resolve,
      and ack-fork clearing it.
  (b) TestSearchCandidatesRealCatalog — search-candidates against the REAL
      vendored agency-agents catalog that ships with the repo (read-only,
      no fixtures, no mocking of _catalog_root).
  (c) TestListCopiesCliShape — list-copies' CLI-level JSON shape.

Registry override mechanism (mirrors test_team_ops_integration.py /
test_team_ops_layers.py exactly): team_ops.py has no --registry flag; it
always resolves the registry path via resolve_wiki._default_registry_path(),
which reads CLAUDE_PLUGIN_DATA from the environment. Every subprocess call
below pins CLAUDE_PLUGIN_DATA to a fresh temp dir via the subprocess's own
env= kwarg, so no test here ever touches a developer machine's real
registry.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.tests.team_test_utils import (
    PERSONA_BODY,
    PERSONA_PROJECT_COPY,
    make_factory_home,
    make_project_copy,
    sha256_text,
)

SCRIPT = Path(__file__).parent.parent / "team_ops.py"


def _env_with_registry(plugin_data_dir: Path) -> dict:
    """Copy of the current environment with CLAUDE_PLUGIN_DATA pinned to an
    isolated temp dir, so subprocess calls never touch the real registry."""
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_DATA"] = str(plugin_data_dir)
    return env


def _write_factory_home_registry(plugin_data_dir: Path, home: Path,
                                  extra_lines: list[str] | None = None) -> Path:
    """Write <plugin_data_dir>/registry.txt with a !factory_home line pointing
    at `home` (plus any extra registry lines), matching the format
    resolve_wiki.py's register-factory-home writes."""
    reg = plugin_data_dir / "registry.txt"
    lines = [f"!factory_home|{home}"] + (extra_lines or [])
    reg.write_text("\n".join(lines) + "\n")
    return reg


def _run(*args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )


def _make_registered_wiki(root: Path, name: str) -> Path:
    """A minimal `is_wiki`-passing wiki directory: `<root>/<name>/CLAUDE.md`
    with the `## Purpose` marker section resolve_wiki.is_wiki requires."""
    wiki = root / name
    wiki.mkdir()
    (wiki / "CLAUDE.md").write_text(f"# {name}\n\n## Purpose\n\nTest wiki.\n")
    return wiki


class TestFullLayeredRoundtrip(unittest.TestCase):
    """The complete layered-persona lifecycle, exercised entirely through
    the CLI in one registry context: base persona -> project copy with
    provenance mentioning its own project -> validate-persona --project
    (exit 0) -> resolve-team --wiki-root (layer=project, no drift yet) ->
    edit the base -> re-resolve shows drift_notice -> ack-fork -> re-resolve
    shows the notice gone. Task 4's report pins these exact JSON shapes
    (member "layer"/"project"/"drift_notice" keys, ack-fork's
    {"acked": true, "base_hash": ...}); this test asserts against them.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_layered_roundtrip_validate_resolve_drift_ack(self):
        team_yaml = (
            "id: demo-team\n"
            "name: \"Demo Team\"\n"
            "members:\n"
            "  - agent: wren\n"
            "    role: Lead Tester\n")
        home = make_factory_home(self.root, personas=(), team_yaml=team_yaml)
        base_text_v1 = PERSONA_BODY.format(name="Wren", role="Domain Lead")
        base_path = home / "agents" / "wren.md"
        base_path.write_text(base_text_v1)

        wiki_root = self.root / "acme-launch"
        wiki_root.mkdir()
        copy_text = PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead",
            description="Use when testing the layered roundtrip.",
            base_slug="wren", forked="2026-07-08",
            base_hash=sha256_text(base_text_v1),
            project="acme-launch")
        copy_path = make_project_copy(wiki_root, "wren", copy_text)
        self.assertIn("the acme-launch project", copy_text)  # sanity on the fixture

        # Registry entry whose basename is "acme-launch" too, so the
        # denylist genuinely contains it — proves --project's exemption is
        # doing real work, not vacuously passing (the round-2 blocker).
        _write_factory_home_registry(
            self.root, home,
            extra_lines=[f"{wiki_root}|acme-launch|2026-01-01|2026-01-01"])
        env = _env_with_registry(self.root)

        # 0. Without --project, the copy's own-project mention refuses —
        #    establishes the exemption is load-bearing, not a no-op.
        bare = _run("validate-persona", str(copy_path), env=env)
        self.assertEqual(bare.returncode, 1, bare.stderr)
        self.assertIn("denylist: acme-launch", json.loads(bare.stdout)["errors"])

        # 1. validate-persona --project acme-launch -> exit 0.
        validate_result = _run(
            "validate-persona", str(copy_path), "--project", "acme-launch", env=env)
        self.assertEqual(validate_result.returncode, 0, validate_result.stderr)
        validate_payload = json.loads(validate_result.stdout)
        self.assertTrue(validate_payload["ok"], validate_payload["errors"])
        self.assertEqual(validate_payload["errors"], [])

        # 2. resolve-team --wiki-root -> the copy, layer=project, no notice.
        resolve_result = _run(
            "resolve-team", "demo-team", "--wiki-root", str(wiki_root), env=env)
        self.assertEqual(resolve_result.returncode, 0, resolve_result.stderr)
        resolve_payload = json.loads(resolve_result.stdout)
        self.assertEqual(len(resolve_payload["members"]), 1)
        member = resolve_payload["members"][0]
        self.assertEqual(member["agent"], "wren")
        self.assertEqual(Path(member["file"]).resolve(), copy_path.resolve())
        self.assertEqual(member["layer"], "project")
        self.assertEqual(member["project"], "acme-launch")
        self.assertNotIn("drift_notice", member)

        # 3. Edit the base persona (different bytes -> different sha256).
        base_text_v2 = base_text_v1.replace(
            "is a test persona.", "is a test persona, freshly edited.")
        self.assertNotEqual(base_text_v1, base_text_v2)  # sanity: edit took
        base_path.write_text(base_text_v2)

        # 4. Re-resolve: drift_notice appears, exact string per Task 4.
        drifted_result = _run(
            "resolve-team", "demo-team", "--wiki-root", str(wiki_root), env=env)
        self.assertEqual(drifted_result.returncode, 0, drifted_result.stderr)
        drifted_member = json.loads(drifted_result.stdout)["members"][0]
        self.assertEqual(
            drifted_member["drift_notice"],
            "base wren has changed since this copy forked — "
            "review the copy or run ack-fork")
        self.assertEqual(drifted_member["layer"], "project")  # still resolves the copy

        # 5. ack-fork -> exit 0, acked True, base_hash matches the NEW base bytes.
        ack_result = _run("ack-fork", str(copy_path), env=env)
        self.assertEqual(ack_result.returncode, 0, ack_result.stderr)
        ack_payload = json.loads(ack_result.stdout)
        self.assertEqual(ack_payload["acked"], True)
        self.assertEqual(ack_payload["base_hash"], sha256_text(base_text_v2))
        self.assertIn(f"base-hash: {sha256_text(base_text_v2)}", copy_path.read_text())

        # 6. Re-resolve: the notice is gone.
        acked_result = _run(
            "resolve-team", "demo-team", "--wiki-root", str(wiki_root), env=env)
        self.assertEqual(acked_result.returncode, 0, acked_result.stderr)
        acked_member = json.loads(acked_result.stdout)["members"][0]
        self.assertNotIn("drift_notice", acked_member)
        self.assertEqual(acked_member["layer"], "project")


class TestSearchCandidatesRealCatalog(unittest.TestCase):
    """search-candidates against the REAL vendored agency-agents catalog
    that ships in this repo (plugin/assets/agency-agents/) — read-only, no
    fixtures, no mocking of _catalog_root/_starter_root. CLAUDE_PLUGIN_DATA
    is still pinned to an isolated empty temp dir (no factory home
    registered) since --source catalog doesn't require one; this proves the
    real catalog is reachable independent of any registry state."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_product_manager_query_returns_real_catalog_hit_with_division(self):
        env = _env_with_registry(self.root)  # no registry.txt written at all

        result = _run(
            "search-candidates", "--query", "product manager", "--source", "catalog",
            env=env)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        results = payload["results"]
        self.assertGreater(len(results), 0, payload)

        catalog_hits = [r for r in results if r["source"] == "catalog"]
        self.assertGreater(len(catalog_hits), 0, "no catalog-sourced hits at all")

        # The top hit is a scoring catalog result — deliberately NOT pinned
        # to a specific persona: today "Product Manager" tops the list only
        # by alphabetical tie-break against "Sprint Prioritizer" (both
        # score 2), so pinning the ordering would false-fail on a future
        # catalog re-sync with zero machinery regression.
        top = results[0]
        self.assertGreaterEqual(top["score"], 1)
        self.assertEqual(top["source"], "catalog")

        # The real, vendored "Product Manager" persona appears SOMEWHERE in
        # the results, under the "product" division — proving the wrapper
        # contract (name/source/division/description/path/score) against
        # the actual shipped file, not a fixture standing in for it.
        pm_hits = [r for r in catalog_hits
                   if r["name"] == "Product Manager" and r["division"] == "product"]
        self.assertEqual(len(pm_hits), 1, catalog_hits)
        pm = pm_hits[0]
        self.assertTrue(pm["description"])
        self.assertTrue(Path(pm["path"]).is_file())
        self.assertGreater(pm["score"], 0)

        # Every catalog hit carries a real, non-null division (the vendored
        # catalog is organized into division subdirectories; only a
        # root-level file like ATTRIBUTION.md would have none, and those
        # are excluded from candidacy by _search_pool's require_division).
        for hit in catalog_hits:
            self.assertIsNotNone(hit["division"])
            self.assertTrue(Path(hit["path"]).is_file())

    def test_zero_match_query_returns_real_catalog_division_suggestions(self):
        env = _env_with_registry(self.root)

        result = _run(
            "search-candidates", "--query", "zzznonexistentqueryterm",
            "--source", "catalog", env=env)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["results"], [])
        self.assertIn("suggestions", payload)
        self.assertGreater(len(payload["suggestions"]), 0)
        self.assertIn("product", payload["suggestions"])  # a real division


class TestListCopiesCliShape(unittest.TestCase):
    """list-copies' CLI-level JSON shape: {"copies": [{"wiki", "path",
    "forked", "drifted"}, ...]}, "skipped" omitted when zero, exit 0
    always (including empty-registry and no-factory-home cases)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_cli_shape_one_matching_copy(self):
        home = make_factory_home(self.root, personas=())
        base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
        (home / "agents" / "wren.md").write_text(base_text)
        wiki = _make_registered_wiki(self.root, "acme-launch")
        copy_path = make_project_copy(wiki, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing.",
            base_slug="wren", forked="2026-07-08", base_hash=sha256_text(base_text),
            project="acme-launch"))
        _write_factory_home_registry(self.root, home, extra_lines=[
            f"{wiki.resolve()}|acme-launch|2026-01-01|2026-01-01"])
        env = _env_with_registry(self.root)

        result = _run("list-copies", "wren", env=env)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(set(payload.keys()), {"copies"})  # "skipped" omitted (0)
        self.assertEqual(len(payload["copies"]), 1)
        entry = payload["copies"][0]
        self.assertEqual(set(entry.keys()), {"wiki", "path", "forked", "drifted"})
        self.assertEqual(entry["wiki"], str(wiki.resolve()))
        self.assertEqual(Path(entry["path"]).resolve(), copy_path.resolve())
        self.assertEqual(entry["forked"], "2026-07-08")
        self.assertEqual(entry["drifted"], False)

    def test_cli_shape_no_registry_empty_copies_exit_0(self):
        env = _env_with_registry(self.root)  # no registry.txt at all

        result = _run("list-copies", "anything", env=env)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"copies": []})

    def test_cli_shape_no_factory_home_still_exit_0(self):
        """No factory home registered is NOT an error for list-copies
        (unlike resolve-team/ack-fork) — drift degrades to null."""
        wiki = _make_registered_wiki(self.root, "acme-launch")
        make_project_copy(wiki, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing.",
            base_slug="wren", forked="2026-07-08", base_hash=sha256_text("anything"),
            project="acme-launch"))
        reg = self.root / "registry.txt"  # no "!factory_home|" line at all
        reg.write_text(f"{wiki.resolve()}|acme-launch|2026-01-01|2026-01-01\n")
        env = _env_with_registry(self.root)

        result = _run("list-copies", "wren", env=env)

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["copies"]), 1)
        self.assertIsNone(payload["copies"][0]["drifted"])  # base unavailable -> None


if __name__ == "__main__":
    unittest.main()
