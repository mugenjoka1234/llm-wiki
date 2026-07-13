"""Tests for layered persona resolution: `--wiki-root` precedence, the
`layer` field, `resolve-persona`, the spawn-time drift notice, and
`ack-fork`.

Function-level tests (TestResolveTeamLayers, TestResolvePersona,
TestDriftNotice, TestAckFork, TestAssembleContextLayer) call `team_ops`
directly. CLI-level tests (TestCliResolvePersona, TestCliAckFork,
TestRoundTwoBlockerRegression) drive the script via subprocess with an
isolated CLAUDE_PLUGIN_DATA, mirroring test_team_ops_integration.py's
pattern — the round-2 blocker regression in particular needs the real
registry -> build_denylist -> validate-persona --project path exercised
end-to-end, not just the pure functions.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import team_ops
from scripts.tests.team_test_utils import (
    PERSONA_BODY,
    PERSONA_DENYLIST_HIT,
    PERSONA_PROJECT_COPY,
    make_factory_home,
    make_project_copy,
    make_wiki_with_positions,
    sha256_text,
)

SCRIPT = Path(__file__).parent.parent / "team_ops.py"


def _env_with_registry(plugin_data_dir: Path) -> dict:
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_DATA"] = str(plugin_data_dir)
    return env


def _write_factory_home_registry(plugin_data_dir: Path, home: Path,
                                  extra_lines: list[str] | None = None) -> Path:
    reg = plugin_data_dir / "registry.txt"
    lines = [f"!factory_home|{home}"] + (extra_lines or [])
    reg.write_text("\n".join(lines) + "\n")
    return reg


def _run(*args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )


# --- resolve_team: --wiki-root precedence, layer field ----------------------

class TestResolveTeamLayers(unittest.TestCase):
    def test_no_wiki_root_is_always_factory(self):
        with tempfile.TemporaryDirectory() as td:
            home = make_factory_home(Path(td))
            out = team_ops.resolve_team(home, "demo-team")
            self.assertEqual(out["members"][0]["layer"], "factory")
            self.assertNotIn("project", out["members"][0])

    def test_project_copy_shadows_base(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp)  # agents/ada.md exists (factory/base)
            wiki_root = tmp / "my-project"
            wiki_root.mkdir()
            copy_path = make_project_copy(
                wiki_root, "ada",
                PERSONA_BODY.format(name="Ada Copy", role="Project Flavor"))

            out = team_ops.resolve_team(home, "demo-team", wiki_root=wiki_root)

            member = out["members"][0]
            self.assertEqual(member["agent"], "ada")
            self.assertEqual(Path(member["file"]).resolve(), copy_path.resolve())
            self.assertEqual(member["layer"], "project")
            self.assertEqual(member["project"], "my-project")

    def test_falls_back_to_base_when_no_project_copy(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp)
            wiki_root = tmp / "my-project"
            wiki_root.mkdir()  # no personas/ada.md written

            out = team_ops.resolve_team(home, "demo-team", wiki_root=wiki_root)

            member = out["members"][0]
            self.assertEqual(Path(member["file"]).resolve(),
                              (home / "agents" / "ada.md").resolve())
            self.assertEqual(member["layer"], "factory")
            self.assertNotIn("project", member)

    def test_missing_in_both_layers_still_reported_as_missing(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp, personas=())  # no ada.md at all
            wiki_root = tmp / "my-project"
            wiki_root.mkdir()  # no personas/ada.md either

            out = team_ops.resolve_team(home, "demo-team", wiki_root=wiki_root)

            self.assertEqual(out["members"], [])
            self.assertIn({"agent": "ada", "role": "Lead Tester"}, out["missing"])


# --- resolve_persona (solo-lookup machinery) --------------------------------

class TestResolvePersona(unittest.TestCase):
    def test_factory_layer_no_wiki_root(self):
        with tempfile.TemporaryDirectory() as td:
            home = make_factory_home(Path(td))
            result = team_ops.resolve_persona(home, "ada")
            self.assertEqual(result["layer"], "factory")
            self.assertEqual(Path(result["file"]).resolve(),
                              (home / "agents" / "ada.md").resolve())
            self.assertNotIn("project", result)

    def test_project_layer_shadows_factory(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp)
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()
            copy_path = make_project_copy(
                wiki_root, "ada", PERSONA_BODY.format(name="Ada Copy", role="Flavor"))

            result = team_ops.resolve_persona(home, "ada", wiki_root=wiki_root)

            self.assertEqual(result["layer"], "project")
            self.assertEqual(Path(result["file"]).resolve(), copy_path.resolve())
            self.assertEqual(result["project"], "acme-corp")

    def test_falls_back_to_factory_when_no_copy(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp)
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()

            result = team_ops.resolve_persona(home, "ada", wiki_root=wiki_root)
            self.assertEqual(result["layer"], "factory")
            self.assertNotIn("project", result)

    def test_not_found_in_either_layer_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            home = make_factory_home(Path(td), personas=())
            result = team_ops.resolve_persona(home, "nonexistent")
            self.assertIsNone(result)


class TestCliResolvePersona(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_cli_resolves_factory_layer(self):
        home = make_factory_home(self.root)
        _write_factory_home_registry(self.root, home)
        env = _env_with_registry(self.root)

        result = _run("resolve-persona", "ada", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["layer"], "factory")

    def test_cli_resolves_project_layer_over_factory(self):
        home = make_factory_home(self.root)
        wiki_root = self.root / "acme-corp"
        wiki_root.mkdir()
        make_project_copy(wiki_root, "ada",
                           PERSONA_BODY.format(name="Ada Copy", role="Flavor"))
        _write_factory_home_registry(self.root, home)
        env = _env_with_registry(self.root)

        result = _run("resolve-persona", "ada", "--wiki-root", str(wiki_root), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["layer"], "project")
        self.assertEqual(payload["project"], "acme-corp")

    def test_cli_exit_2_when_not_found(self):
        home = make_factory_home(self.root, personas=())
        _write_factory_home_registry(self.root, home)
        env = _env_with_registry(self.root)

        result = _run("resolve-persona", "nonexistent", env=env)
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")

    def test_cli_exit_2_when_no_factory_home_registered(self):
        env = _env_with_registry(self.root)  # no registry.txt at all

        result = _run("resolve-persona", "ada", env=env)
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertIn("register-factory-home", payload["hint"])


# --- assemble_context: layer field -------------------------------------------

class TestAssembleContextLayer(unittest.TestCase):
    def test_layer_factory_when_no_wiki_root_prefix_match(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp)
            project = make_wiki_with_positions(tmp)
            persona = home / "agents" / "ada.md"

            result = team_ops.assemble_context(tmp, project, persona)
            self.assertEqual(result["layer"], "factory")

    def test_layer_project_when_under_wiki_root_personas(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp)
            project = make_wiki_with_positions(tmp)
            persona = make_project_copy(
                project, "ada", PERSONA_BODY.format(name="Ada Copy", role="Flavor"))

            result = team_ops.assemble_context(home, project, persona)
            self.assertEqual(result["layer"], "project")


# --- Round-2 blocker regression: a project copy mentioning its own project --

class TestRoundTwoBlockerRegression(unittest.TestCase):
    """A project-layer persona copy mentions its OWN project by design (that
    is the entire point of a project copy). It must:
      1. validate cleanly with `validate-persona --project <that project>`
         (task 3's own-name exemption), and
      2. resolve end-to-end via `resolve-team --wiki-root <that project>`
         with `layer: project` (task 4's layered resolution) —
      in the SAME registry/denylist context, where the project's OWN name is
      also a registry-derived denylist entry (so a bare validate-persona
      WITHOUT --project would refuse it — proving the exemption is actually
      doing work, not just vacuously passing).
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_project_copy_validates_and_resolves_end_to_end(self):
        home = make_factory_home(self.root, team_yaml=(
            "id: demo-team\n"
            "name: \"Demo Team\"\n"
            "members:\n"
            "  - agent: wren\n"
            "    role: Lead Tester\n"))
        wiki_root = self.root / "acme-launch"
        wiki_root.mkdir()
        copy_text = PERSONA_DENYLIST_HIT.format(
            name="Wren", role="Domain Lead",
            description="Use when testing the round-2 blocker regression.")
        copy_path = make_project_copy(wiki_root, "wren", copy_text)

        # registry: factory home + a registry entry whose basename is
        # "acme-launch" (same as the project) so build_denylist actually
        # includes it — the exemption must be doing real work here.
        _write_factory_home_registry(
            self.root, home,
            extra_lines=[f"{wiki_root}|acme-launch|2026-01-01|2026-01-01"])
        env = _env_with_registry(self.root)

        # (1) Without --project, the copy's own-project mention refuses.
        bare = _run("validate-persona", str(copy_path), env=env)
        self.assertEqual(bare.returncode, 1, bare.stderr)
        bare_payload = json.loads(bare.stdout)
        self.assertIn("denylist: acme-launch", bare_payload["errors"])

        # (1b) With --project acme-launch, it validates clean.
        validate_result = _run(
            "validate-persona", str(copy_path), "--project", "acme-launch", env=env)
        self.assertEqual(validate_result.returncode, 0, validate_result.stderr)
        validate_payload = json.loads(validate_result.stdout)
        self.assertTrue(validate_payload["ok"], validate_payload["errors"])

        # (2) resolve-team --wiki-root resolves the SAME copy, layer=project.
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


# --- Spawn-time drift notice -------------------------------------------------

class TestDriftNotice(unittest.TestCase):
    def _setup(self, tmp: Path, base_text: str, base_hash: str):
        home = make_factory_home(tmp, personas=())
        (home / "agents" / "wren.md").write_text(base_text)
        wiki_root = tmp / "acme-corp"
        wiki_root.mkdir()
        copy_path = make_project_copy(wiki_root, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead",
            description="Use when testing drift.",
            base_slug="wren", forked="2026-06-01", base_hash=base_hash,
            project="acme-corp"))
        return home, wiki_root, copy_path

    def test_fires_on_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
            stale_hash = sha256_text("totally different content")
            home, wiki_root, copy_path = self._setup(tmp, base_text, stale_hash)
            (home / "agents" / "wren.md").write_text(base_text)  # ensure current text on disk

            result = team_ops.resolve_persona(home, "wren", wiki_root=wiki_root)

            self.assertEqual(
                result["drift_notice"],
                "base wren has changed since this copy forked — "
                "review the copy or run ack-fork")

    def test_silent_when_hash_matches(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
            matching_hash = sha256_text(base_text)
            home, wiki_root, copy_path = self._setup(tmp, base_text, matching_hash)

            result = team_ops.resolve_persona(home, "wren", wiki_root=wiki_root)
            self.assertNotIn("drift_notice", result)

    def test_silent_when_base_slug_missing(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp, personas=("wren",))
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()
            # A project copy with NO base-slug/base-hash frontmatter at all.
            make_project_copy(wiki_root, "wren",
                               PERSONA_BODY.format(name="Wren", role="Domain Lead"))

            result = team_ops.resolve_persona(home, "wren", wiki_root=wiki_root)
            self.assertNotIn("drift_notice", result)

    def test_silent_when_base_file_missing(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp, personas=())  # no wren.md in agents/ at all
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()
            make_project_copy(wiki_root, "wren", PERSONA_PROJECT_COPY.format(
                name="Wren", role="Domain Lead", description="Use when testing.",
                base_slug="wren", forked="2026-06-01",
                base_hash=sha256_text("anything"), project="acme-corp"))

            result = team_ops.resolve_persona(home, "wren", wiki_root=wiki_root)
            self.assertNotIn("drift_notice", result)

    def test_fires_via_resolve_team_member_dict_too(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
            stale_hash = sha256_text("totally different content")
            home, wiki_root, copy_path = self._setup(tmp, base_text, stale_hash)
            team_yaml = ("id: demo-team\nname: \"Demo Team\"\nmembers:\n"
                         "  - agent: wren\n    role: Lead Tester\n")
            (home / "teams" / "demo-team.yaml").write_text(team_yaml)

            out = team_ops.resolve_team(home, "demo-team", wiki_root=wiki_root)
            self.assertIn("drift_notice", out["members"][0])

    def test_drift_checks_against_named_base_not_filename(self):
        """A copy whose `base-slug` differs from its own filename must
        resolve normally AND drift-check against the NAMED base
        (agents/sage.md), not a file matching the copy's own slug (wren —
        which doesn't even exist in agents/ here)."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp, personas=())
            sage_text = PERSONA_BODY.format(name="Sage", role="Domain Lead")
            (home / "agents" / "sage.md").write_text(sage_text)
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()
            copy_path = make_project_copy(wiki_root, "wren", PERSONA_PROJECT_COPY.format(
                name="Wren", role="Domain Lead", description="Use when testing.",
                base_slug="sage", forked="2026-06-01",
                base_hash=sha256_text("stale — not sage's current text"),
                project="acme-corp"))

            result = team_ops.resolve_persona(home, "wren", wiki_root=wiki_root)
            self.assertEqual(result["layer"], "project")
            self.assertIn("base sage has changed", result["drift_notice"])

            # ack-fork recomputes against the NAMED base (sage.md), too.
            ack = team_ops.ack_fork(copy_path, home)
            self.assertEqual(ack["base_hash"], sha256_text(sage_text))
            after = team_ops.resolve_persona(home, "wren", wiki_root=wiki_root)
            self.assertNotIn("drift_notice", after)


# --- Unreadable project copies: degrade, never crash -------------------------

def _make_unreadable(test: unittest.TestCase, path: Path) -> None:
    """chmod-000 `path` and register cleanup; skip the calling test when the
    filesystem/effective user (e.g. root) doesn't enforce mode 000 —
    mirrors test_team_ops_integration.py's permission-denied pattern."""
    path.chmod(0)

    def _restore():
        try:
            path.chmod(0o644)
        except FileNotFoundError:
            pass  # tempdir context manager already removed the tree
    test.addCleanup(_restore)
    try:
        path.read_text()
        test.skipTest("chmod 000 not enforced on this filesystem/user")
    except PermissionError:
        pass


class TestUnreadableProjectCopy(unittest.TestCase):
    """The Important review finding, live-reproduced by the reviewer: an
    unreadable (chmod-000) project copy must never escape as a traceback
    out of resolve_team/resolve_persona — it degrades to the factory layer
    with a `layer_warning`, or to `missing` when the base is also absent."""

    def test_resolve_persona_falls_back_to_factory_with_warning(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp)  # agents/ada.md exists
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()
            copy_path = make_project_copy(
                wiki_root, "ada", PERSONA_BODY.format(name="Ada Copy", role="Flavor"))
            _make_unreadable(self, copy_path)

            result = team_ops.resolve_persona(home, "ada", wiki_root=wiki_root)

            self.assertEqual(result["layer"], "factory")
            self.assertEqual(Path(result["file"]).resolve(),
                              (home / "agents" / "ada.md").resolve())
            self.assertIn("fell back to factory", result["layer_warning"])
            self.assertNotIn("project", result)
            self.assertNotIn("drift_notice", result)

    def test_resolve_team_member_degrades_with_warning(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp)
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()
            copy_path = make_project_copy(
                wiki_root, "ada", PERSONA_BODY.format(name="Ada Copy", role="Flavor"))
            _make_unreadable(self, copy_path)

            out = team_ops.resolve_team(home, "demo-team", wiki_root=wiki_root)

            member = out["members"][0]
            self.assertEqual(member["agent"], "ada")
            self.assertEqual(member["layer"], "factory")
            self.assertIn("fell back to factory", member["layer_warning"])

    def test_unreadable_copy_and_absent_base_reports_missing(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp, personas=())  # no ada.md in agents/
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()
            copy_path = make_project_copy(
                wiki_root, "ada", PERSONA_BODY.format(name="Ada Copy", role="Flavor"))
            _make_unreadable(self, copy_path)

            self.assertIsNone(
                team_ops.resolve_persona(home, "ada", wiki_root=wiki_root))
            out = team_ops.resolve_team(home, "demo-team", wiki_root=wiki_root)
            self.assertIn({"agent": "ada", "role": "Lead Tester"}, out["missing"])

    def test_cli_resolve_team_returns_json_exit_0(self):
        """The reviewer's exact repro: the CLI must return JSON with exit 0
        (degraded member), never a traceback with exit 1."""
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, tmpdir)
        root = Path(tmpdir)
        home = make_factory_home(root)
        wiki_root = root / "acme-corp"
        wiki_root.mkdir()
        copy_path = make_project_copy(
            wiki_root, "ada", PERSONA_BODY.format(name="Ada Copy", role="Flavor"))
        _make_unreadable(self, copy_path)
        _write_factory_home_registry(root, home)
        env = _env_with_registry(root)

        result = _run("resolve-team", "demo-team", "--wiki-root", str(wiki_root), env=env)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        payload = json.loads(result.stdout)  # JSON, not a traceback
        member = payload["members"][0]
        self.assertEqual(member["layer"], "factory")
        self.assertIn("fell back to factory", member["layer_warning"])


# --- ack-fork -----------------------------------------------------------------

class TestAckFork(unittest.TestCase):
    def test_rewrites_hash_and_clears_drift_notice(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp, personas=())
            base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
            (home / "agents" / "wren.md").write_text(base_text)
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()
            stale_hash = sha256_text("stale content, not the real base")
            copy_path = make_project_copy(wiki_root, "wren", PERSONA_PROJECT_COPY.format(
                name="Wren", role="Domain Lead", description="Use when testing.",
                base_slug="wren", forked="2026-06-01", base_hash=stale_hash,
                project="acme-corp"))

            before = team_ops.resolve_persona(home, "wren", wiki_root=wiki_root)
            self.assertIn("drift_notice", before)

            result = team_ops.ack_fork(copy_path, home)
            expected_hash = sha256_text(base_text)
            self.assertEqual(result, {"acked": True, "base_hash": expected_hash})

            after = team_ops.resolve_persona(home, "wren", wiki_root=wiki_root)
            self.assertNotIn("drift_notice", after)
            self.assertIn(f"base-hash: {expected_hash}", copy_path.read_text())

    def test_rewrite_touches_only_the_base_hash_line(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp, personas=())
            base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
            (home / "agents" / "wren.md").write_text(base_text)
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()
            original_text = PERSONA_PROJECT_COPY.format(
                name="Wren", role="Domain Lead", description="Use when testing.",
                base_slug="wren", forked="2026-06-01",
                base_hash=sha256_text("stale"), project="acme-corp")
            copy_path = make_project_copy(wiki_root, "wren", original_text)

            team_ops.ack_fork(copy_path, home)

            new_text = copy_path.read_text()
            original_lines = original_text.splitlines()
            new_lines = new_text.splitlines()
            self.assertEqual(len(original_lines), len(new_lines))
            diffs = [i for i, (o, n) in enumerate(zip(original_lines, new_lines)) if o != n]
            self.assertEqual(len(diffs), 1, diffs)
            self.assertTrue(new_lines[diffs[0]].startswith("base-hash:"))

    def test_is_atomic_no_tmp_leftovers(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp, personas=())
            base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
            (home / "agents" / "wren.md").write_text(base_text)
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()
            copy_path = make_project_copy(wiki_root, "wren", PERSONA_PROJECT_COPY.format(
                name="Wren", role="Domain Lead", description="Use when testing.",
                base_slug="wren", forked="2026-06-01",
                base_hash=sha256_text("stale"), project="acme-corp"))

            team_ops.ack_fork(copy_path, home)

            leftovers = [p for p in (wiki_root / "personas").iterdir() if ".tmp" in p.name]
            self.assertEqual(leftovers, [])

    def test_raises_when_copy_has_no_base_slug(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp)
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()
            copy_path = make_project_copy(
                wiki_root, "wren", PERSONA_BODY.format(name="Wren", role="Domain Lead"))

            with self.assertRaises(team_ops.AckForkError):
                team_ops.ack_fork(copy_path, home)

    def test_raises_when_base_file_missing(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            home = make_factory_home(tmp, personas=())  # no wren.md in agents/
            wiki_root = tmp / "acme-corp"
            wiki_root.mkdir()
            copy_path = make_project_copy(wiki_root, "wren", PERSONA_PROJECT_COPY.format(
                name="Wren", role="Domain Lead", description="Use when testing.",
                base_slug="wren", forked="2026-06-01",
                base_hash=sha256_text("anything"), project="acme-corp"))

            with self.assertRaises(team_ops.AckForkError):
                team_ops.ack_fork(copy_path, home)


class TestCliAckFork(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_cli_success(self):
        home = make_factory_home(self.root, personas=())
        base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
        (home / "agents" / "wren.md").write_text(base_text)
        wiki_root = self.root / "acme-corp"
        wiki_root.mkdir()
        copy_path = make_project_copy(wiki_root, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing.",
            base_slug="wren", forked="2026-06-01",
            base_hash=sha256_text("stale"), project="acme-corp"))
        _write_factory_home_registry(self.root, home)
        env = _env_with_registry(self.root)

        result = _run("ack-fork", str(copy_path), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["acked"])
        self.assertEqual(payload["base_hash"], sha256_text(base_text))

    def test_cli_exit_2_no_base_slug(self):
        home = make_factory_home(self.root)
        copy_path = self.root / "wren.md"
        copy_path.write_text(PERSONA_BODY.format(name="Wren", role="Domain Lead"))
        _write_factory_home_registry(self.root, home)
        env = _env_with_registry(self.root)

        result = _run("ack-fork", str(copy_path), env=env)
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["acked"])

    def test_cli_exit_2_base_missing(self):
        home = make_factory_home(self.root, personas=())
        copy_path = self.root / "wren.md"
        copy_path.write_text(PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing.",
            base_slug="wren", forked="2026-06-01",
            base_hash=sha256_text("anything"), project="acme-corp"))
        _write_factory_home_registry(self.root, home)
        env = _env_with_registry(self.root)

        result = _run("ack-fork", str(copy_path), env=env)
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["acked"])

    def test_cli_exit_2_copy_path_not_found(self):
        env = _env_with_registry(self.root)
        result = _run("ack-fork", str(self.root / "nonexistent.md"), env=env)
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["acked"])

    def test_cli_exit_2_no_factory_home_with_register_hint(self):
        """No registered factory home: the error must be the SAME
        register-factory-home hint style resolve-team uses — not a
        misleading 'base persona not found' against a sentinel path."""
        copy_path = self.root / "wren.md"
        copy_path.write_text(PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing.",
            base_slug="wren", forked="2026-06-01",
            base_hash=sha256_text("anything"), project="acme-corp"))
        env = _env_with_registry(self.root)  # no registry.txt written at all

        result = _run("ack-fork", str(copy_path), env=env)
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertIn("register-factory-home", payload["hint"])
        self.assertNotIn("base persona not found", json.dumps(payload))


# --- list-copies: routing lookup across registered wikis --------------------

def _make_registered_wiki(root: Path, name: str) -> Path:
    """A minimal `is_wiki`-passing wiki directory: `<root>/<name>/CLAUDE.md`
    with the `## Purpose` marker section, no `personas/` dir yet (callers
    add copies with `make_project_copy`)."""
    wiki = root / name
    wiki.mkdir()
    (wiki / "CLAUDE.md").write_text(f"# {name}\n\n## Purpose\n\nTest wiki.\n")
    return wiki


class TestListCopies(unittest.TestCase):
    """`list_copies(slug, home)`: scans every registered (`is_wiki`-passing)
    wiki's `personas/*.md` for a matching `base-slug`, a deterministic
    routing lookup — distinct from `resolve_team`/`resolve_persona`'s
    single-project precedence resolution, this fans OUT across every
    registered wiki at once."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def _env(self):
        return mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": str(self.root)})

    def test_finds_copies_across_two_wikis(self):
        home = make_factory_home(self.root, personas=())
        base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
        (home / "agents" / "wren.md").write_text(base_text)
        wiki_a = _make_registered_wiki(self.root, "wiki-a")
        wiki_b = _make_registered_wiki(self.root, "wiki-b")
        copy_a = make_project_copy(wiki_a, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing a.",
            base_slug="wren", forked="2026-06-01", base_hash=sha256_text(base_text),
            project="wiki-a"))
        copy_b = make_project_copy(wiki_b, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing b.",
            base_slug="wren", forked="2026-06-02", base_hash=sha256_text(base_text),
            project="wiki-b"))
        _write_factory_home_registry(self.root, home, extra_lines=[
            f"{wiki_a.resolve()}|wiki-a|2026-01-01|2026-01-01",
            f"{wiki_b.resolve()}|wiki-b|2026-01-01|2026-01-01",
        ])

        with self._env():
            result = team_ops.list_copies("wren", home)

        self.assertEqual(len(result["copies"]), 2)
        self.assertEqual({c["path"] for c in result["copies"]},
                          {str(copy_a.resolve()), str(copy_b.resolve())})
        self.assertNotIn("skipped", result)
        for c in result["copies"]:
            self.assertEqual(c["drifted"], False)
            self.assertIn(c["forked"], ("2026-06-01", "2026-06-02"))

    def test_skips_non_matching_base_slug(self):
        home = make_factory_home(self.root, personas=())
        (home / "agents" / "wren.md").write_text(
            PERSONA_BODY.format(name="Wren", role="Domain Lead"))
        wiki = _make_registered_wiki(self.root, "wiki-a")
        make_project_copy(wiki, "sage", PERSONA_PROJECT_COPY.format(
            name="Sage", role="Other", description="Use when testing.",
            base_slug="sage", forked="2026-06-01", base_hash=sha256_text("x"),
            project="wiki-a"))
        _write_factory_home_registry(self.root, home, extra_lines=[
            f"{wiki.resolve()}|wiki-a|2026-01-01|2026-01-01"])

        with self._env():
            result = team_ops.list_copies("wren", home)

        self.assertEqual(result, {"copies": []})

    def test_empty_registry_returns_empty_copies(self):
        home = make_factory_home(self.root, personas=())
        # No registry.txt written at all.
        with self._env():
            result = team_ops.list_copies("wren", home)
        self.assertEqual(result, {"copies": []})

    def test_drifted_true_on_hash_mismatch(self):
        home = make_factory_home(self.root, personas=())
        base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
        (home / "agents" / "wren.md").write_text(base_text)
        wiki = _make_registered_wiki(self.root, "wiki-a")
        make_project_copy(wiki, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing.",
            base_slug="wren", forked="2026-06-01",
            base_hash=sha256_text("stale — not the real base"),
            project="wiki-a"))
        _write_factory_home_registry(self.root, home, extra_lines=[
            f"{wiki.resolve()}|wiki-a|2026-01-01|2026-01-01"])

        with self._env():
            result = team_ops.list_copies("wren", home)

        self.assertEqual(result["copies"][0]["drifted"], True)

    def test_drifted_false_on_hash_match(self):
        home = make_factory_home(self.root, personas=())
        base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
        (home / "agents" / "wren.md").write_text(base_text)
        wiki = _make_registered_wiki(self.root, "wiki-a")
        make_project_copy(wiki, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing.",
            base_slug="wren", forked="2026-06-01", base_hash=sha256_text(base_text),
            project="wiki-a"))
        _write_factory_home_registry(self.root, home, extra_lines=[
            f"{wiki.resolve()}|wiki-a|2026-01-01|2026-01-01"])

        with self._env():
            result = team_ops.list_copies("wren", home)

        self.assertEqual(result["copies"][0]["drifted"], False)

    def test_drifted_none_when_base_hash_missing(self):
        home = make_factory_home(self.root, personas=())
        (home / "agents" / "wren.md").write_text(
            PERSONA_BODY.format(name="Wren", role="Domain Lead"))
        wiki = _make_registered_wiki(self.root, "wiki-a")
        # A copy carrying base-slug but no base-hash/forked frontmatter at all.
        no_hash_copy = (
            "---\nname: Wren\nrole: Domain Lead\n"
            "description: Use when testing missing hash.\n"
            "base-slug: wren\nversion: v1.0\n---\n\n"
            "# Wren — Domain Lead\n\n## Identity\nCopy with no base-hash.\n\n"
            "## Immutable Anchors (cannot change)\n\n"
            "<!-- IMMUTABLE:BEGIN -->\n- Never fabricates data\n"
            "<!-- IMMUTABLE:END -->\n\n## Mutable Instructions (can evolve)\n\n"
            "- Output format\n")
        make_project_copy(wiki, "wren", no_hash_copy)
        _write_factory_home_registry(self.root, home, extra_lines=[
            f"{wiki.resolve()}|wiki-a|2026-01-01|2026-01-01"])

        with self._env():
            result = team_ops.list_copies("wren", home)

        self.assertIsNone(result["copies"][0]["drifted"])
        self.assertIsNone(result["copies"][0]["forked"])

    def test_drifted_none_when_base_file_missing(self):
        home = make_factory_home(self.root, personas=())  # no wren.md in agents/
        wiki = _make_registered_wiki(self.root, "wiki-a")
        make_project_copy(wiki, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing.",
            base_slug="wren", forked="2026-06-01", base_hash=sha256_text("anything"),
            project="wiki-a"))
        _write_factory_home_registry(self.root, home, extra_lines=[
            f"{wiki.resolve()}|wiki-a|2026-01-01|2026-01-01"])

        with self._env():
            result = team_ops.list_copies("wren", home)

        self.assertIsNone(result["copies"][0]["drifted"])

    def test_unreadable_persona_file_skipped_and_counted(self):
        home = make_factory_home(self.root, personas=())
        base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
        (home / "agents" / "wren.md").write_text(base_text)
        wiki = _make_registered_wiki(self.root, "wiki-a")
        good_copy = make_project_copy(wiki, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing good.",
            base_slug="wren", forked="2026-06-01", base_hash=sha256_text(base_text),
            project="wiki-a"))
        bad_copy = make_project_copy(wiki, "other", PERSONA_PROJECT_COPY.format(
            name="Other", role="X", description="Use when testing bad.",
            base_slug="wren", forked="2026-06-02", base_hash=sha256_text("y"),
            project="wiki-a"))
        _make_unreadable(self, bad_copy)
        _write_factory_home_registry(self.root, home, extra_lines=[
            f"{wiki.resolve()}|wiki-a|2026-01-01|2026-01-01"])

        with self._env():
            result = team_ops.list_copies("wren", home)

        self.assertEqual({c["path"] for c in result["copies"]},
                          {str(good_copy.resolve())})
        self.assertEqual(result["skipped"], 1)

    def test_non_wiki_registry_entry_excluded(self):
        home = make_factory_home(self.root, personas=())
        not_a_wiki = self.root / "not-a-wiki"
        not_a_wiki.mkdir()
        make_project_copy(not_a_wiki, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing.",
            base_slug="wren", forked="2026-06-01", base_hash=sha256_text("z"),
            project="not-a-wiki"))
        _write_factory_home_registry(self.root, home, extra_lines=[
            f"{not_a_wiki.resolve()}|not-a-wiki|2026-01-01|2026-01-01"])

        with self._env():
            result = team_ops.list_copies("wren", home)

        self.assertEqual(result, {"copies": []})

    def test_registered_wiki_path_gone_excluded(self):
        home = make_factory_home(self.root, personas=())
        gone = self.root / "gone-wiki"  # never created on disk
        _write_factory_home_registry(self.root, home, extra_lines=[
            f"{gone}|gone|2026-01-01|2026-01-01"])

        with self._env():
            result = team_ops.list_copies("wren", home)

        self.assertEqual(result, {"copies": []})


class TestCliListCopies(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_cli_finds_copy_exit_0(self):
        home = make_factory_home(self.root, personas=())
        base_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
        (home / "agents" / "wren.md").write_text(base_text)
        wiki = _make_registered_wiki(self.root, "wiki-a")
        make_project_copy(wiki, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing.",
            base_slug="wren", forked="2026-06-01", base_hash=sha256_text(base_text),
            project="wiki-a"))
        _write_factory_home_registry(self.root, home, extra_lines=[
            f"{wiki.resolve()}|wiki-a|2026-01-01|2026-01-01"])
        env = _env_with_registry(self.root)

        result = _run("list-copies", "wren", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["copies"]), 1)
        self.assertEqual(payload["copies"][0]["drifted"], False)

    def test_cli_no_registry_exit_0_empty(self):
        env = _env_with_registry(self.root)  # no registry.txt at all

        result = _run("list-copies", "wren", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"copies": []})

    def test_cli_no_factory_home_registered_still_exit_0(self):
        """No factory home is NOT an error for list-copies: unlike
        resolve-team/ack-fork, this scans registered wikis, not the factory
        home — drift just degrades to null (fields unavailable)."""
        wiki = _make_registered_wiki(self.root, "wiki-a")
        make_project_copy(wiki, "wren", PERSONA_PROJECT_COPY.format(
            name="Wren", role="Domain Lead", description="Use when testing.",
            base_slug="wren", forked="2026-06-01", base_hash=sha256_text("anything"),
            project="wiki-a"))
        reg = self.root / "registry.txt"
        reg.write_text(f"{wiki.resolve()}|wiki-a|2026-01-01|2026-01-01\n")
        env = _env_with_registry(self.root)

        result = _run("list-copies", "wren", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["copies"]), 1)
        self.assertIsNone(payload["copies"][0]["drifted"])


if __name__ == "__main__":
    unittest.main()
