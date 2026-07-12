"""CLI-level integration tests for team_ops.py.

Unlike the function-level tests in test_team_ops_{resolve,persona,context}.py,
these drive the script end-to-end via `subprocess.run([sys.executable,
str(SCRIPT), ...])` — the same layer a real caller (the /team skill) hits.
Stdlib only; no PyYAML, no pytest.

Registry override mechanism: team_ops.py has no --registry flag of its own
(unlike resolve_wiki.py); it always resolves the registry path via
resolve_wiki._default_registry_path(), which reads CLAUDE_PLUGIN_DATA from
the environment. To isolate subprocess runs from the real, developer-machine
registry we set CLAUDE_PLUGIN_DATA to a fresh temp dir and pass it via the
subprocess's own `env=` kwarg (not just os.environ of the test process —
that would work by inheritance today, but pinning env= makes the isolation
explicit and immune to future subprocess call changes). This mirrors the
CLAUDE_PLUGIN_DATA pattern already used in test_team_ops_persona.py's
TestBuildDenylist, just carried across the subprocess boundary.
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
    PERSONA_FENCED,
    make_factory_home,
    make_wiki_with_positions,
)

SCRIPT = Path(__file__).parent.parent / "team_ops.py"
TEMPLATE = Path(__file__).parent.parent.parent / "assets" / "factory-templates" / "persona.md"


def _env_with_registry(plugin_data_dir: Path) -> dict:
    """Copy of the current environment with CLAUDE_PLUGIN_DATA pinned to an
    isolated temp dir, so subprocess calls never touch the real registry."""
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_DATA"] = str(plugin_data_dir)
    return env


def _write_factory_home_registry(plugin_data_dir: Path, home: Path) -> Path:
    """Write <plugin_data_dir>/registry.txt with a !factory_home line pointing
    at `home`, matching the format resolve_wiki.py's register-factory-home
    writes and load_factory_home()/is_factory_home() expect."""
    reg = plugin_data_dir / "registry.txt"
    reg.write_text(f"!factory_home|{home}\n")
    return reg


def _run(*args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )


class TestCliResolveUpgradeAssembleRoundtrip(unittest.TestCase):
    """Full lazy-upgrade lifecycle through the CLI: resolve a team, upgrade an
    unfenced/description-less persona in place, validate it now passes, then
    assemble a context manifest against it."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_cli_resolve_upgrade_assemble_roundtrip(self):
        home = make_factory_home(self.root)  # agents/ada.md: no description, unfenced
        persona_path = home / "agents" / "ada.md"
        _write_factory_home_registry(self.root, home)
        env = _env_with_registry(self.root)

        # 1. resolve-team: ada present, bo missing — still exit 0 (partial is data).
        resolve_result = _run("resolve-team", "demo-team", env=env)
        self.assertEqual(resolve_result.returncode, 0, resolve_result.stderr)
        resolve_payload = json.loads(resolve_result.stdout)
        self.assertEqual([m["agent"] for m in resolve_payload["members"]], ["ada"])
        self.assertEqual(Path(resolve_payload["members"][0]["file"]).resolve(),
                          persona_path.resolve())

        # 2. upgrade-persona: adds the missing description, fences the anchors.
        upgrade_result = _run(
            "upgrade-persona", str(persona_path),
            "--description", "Use when testing.", env=env)
        self.assertEqual(upgrade_result.returncode, 0, upgrade_result.stderr)
        upgrade_payload = json.loads(upgrade_result.stdout)
        self.assertTrue(upgrade_payload["changed"])
        self.assertTrue(upgrade_payload["added_description"])
        self.assertTrue(upgrade_payload["fenced"])

        # 3. validate-persona: now passes (description present, anchors fenced).
        validate_result = _run("validate-persona", str(persona_path), env=env)
        self.assertEqual(validate_result.returncode, 0, validate_result.stderr)
        validate_payload = json.loads(validate_result.stdout)
        self.assertTrue(validate_payload["ok"], validate_payload["errors"])
        self.assertEqual(validate_payload["errors"], [])

        # 4. assemble-context: manifest parses; persona path is correct.
        wiki_root = make_wiki_with_positions(self.root)
        context_result = _run(
            "assemble-context",
            "--wiki-root", str(wiki_root),
            "--persona", str(persona_path), env=env)
        self.assertEqual(context_result.returncode, 0, context_result.stderr)
        context_payload = json.loads(context_result.stdout)
        self.assertEqual(Path(context_payload["persona"]).resolve(),
                          persona_path.resolve())
        self.assertIn("orientation", context_payload)
        self.assertIn("prior_positions", context_payload)
        self.assertGreaterEqual(len(context_payload["orientation"]), 2)  # index + overview


class TestCliPartialFailureShape(unittest.TestCase):
    """A team with one present and one missing member still resolves with
    exit 0; the missing member's role is preserved in the `missing` list."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_cli_partial_failure_shape(self):
        home = make_factory_home(self.root)  # demo-team: ada present, bo missing
        _write_factory_home_registry(self.root, home)
        env = _env_with_registry(self.root)

        result = _run("resolve-team", "demo-team", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["missing"], [{"agent": "bo", "role": "Missing Member"}])
        self.assertEqual([m["agent"] for m in payload["members"]], ["ada"])


class TestCliFactoryHomeAbsentExitsTwoWithHint(unittest.TestCase):
    """No factory home registered (empty registry, no !factory_home line):
    resolve-team must exit 2 with a hint mentioning register-factory-home."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_cli_factory_home_absent_exits_2_with_hint(self):
        # No registry.txt written at all under this isolated CLAUDE_PLUGIN_DATA —
        # load_factory_home() returns None for a nonexistent file.
        env = _env_with_registry(self.root)

        result = _run("resolve-team", "x", env=env)
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertIn("register-factory-home", payload["hint"])


class TestCliRecruitRefusals(unittest.TestCase):
    """validate-persona on a filled real template that's missing the
    citation-anchor bullet must refuse (exit 1) and name the anchor."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_cli_recruit_refusals(self):
        filled = TEMPLATE.read_text() \
            .replace("{{NAME}}", "Juno") \
            .replace("{{ROLE}}", "Domain Lead") \
            .replace("{{DESCRIPTION}}", "Use when testing recruit refusal.")
        # Remove the citation-anchor bullet line (the sole CITATION_STANDARD
        # reference in the template) so validate-persona has grounds to refuse.
        lines = [line for line in filled.splitlines()
                 if "CITATION_STANDARD" not in line]
        self.assertNotIn("CITATION_STANDARD", "\n".join(lines))  # sanity on the fixture itself

        persona_path = self.root / "juno.md"
        persona_path.write_text("\n".join(lines) + "\n")

        env = _env_with_registry(self.root)  # isolated: no registry.txt written
        result = _run("validate-persona", str(persona_path), env=env)

        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(
            any("CITATION_STANDARD" in e or "citation" in e.lower()
                for e in payload["errors"]),
            payload["errors"])


class TestCliAnchorsUnchangedExitCodes(unittest.TestCase):
    """/improve's branch points: exit 0 (ok), 1 (not ok), 2 (unreadable path).
    Exercised through the CLI, not the Python function, because the skill
    branches on the process exit code, not the JSON payload."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_exit_0_when_fences_unchanged(self):
        env = _env_with_registry(self.root)
        text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
        original = self.root / "original.md"
        edited = self.root / "edited.md"
        original.write_text(text)
        edited.write_text(text.replace("v1", "v2 — mutable-only edit"))

        result = _run("anchors-unchanged", str(original), str(edited), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_exit_1_when_fence_content_changed(self):
        env = _env_with_registry(self.root)
        original_text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
        edited_text = original_text.replace("Never fabricates data", "Never fabricates dataX")
        original = self.root / "original.md"
        edited = self.root / "edited.md"
        original.write_text(original_text)
        edited.write_text(edited_text)

        result = _run("anchors-unchanged", str(original), str(edited), env=env)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(json.loads(result.stdout)["ok"])

    def test_exit_2_when_path_unreadable(self):
        env = _env_with_registry(self.root)
        original = self.root / "original.md"
        original.write_text(PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1"))
        missing = self.root / "does-not-exist.md"

        result = _run("anchors-unchanged", str(original), str(missing), env=env)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(json.loads(result.stdout)["ok"])

    def test_exit_2_when_file_exists_but_permission_denied(self):
        """A file that EXISTS but cannot be read (chmod 000) must also exit 2
        with a JSON payload — never a traceback. Skipped when the filesystem
        or effective user (e.g. root) doesn't enforce mode 000."""
        env = _env_with_registry(self.root)
        original = self.root / "original.md"
        original.write_text(PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1"))
        locked = self.root / "locked.md"
        locked.write_text(PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1"))
        locked.chmod(0)
        try:
            try:
                locked.read_text()
                enforced = False
            except PermissionError:
                enforced = True
            if not enforced:
                self.skipTest("chmod 000 not enforced on this filesystem/user")

            result = _run("anchors-unchanged", str(original), str(locked), env=env)
            self.assertEqual(result.returncode, 2, result.stderr)
            payload = json.loads(result.stdout)  # JSON, not a traceback
            self.assertFalse(payload["ok"])
        finally:
            locked.chmod(0o644)  # let tearDown's rmtree clean up regardless


if __name__ == "__main__":
    unittest.main()
