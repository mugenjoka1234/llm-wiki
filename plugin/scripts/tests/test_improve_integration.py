"""CLI-level integration tests for the /improve machinery.

/improve itself is a skill (plugin/skills/improve/SKILL.md), not a script —
there is no `improve.py` to invoke. What IS testable at the subprocess-CLI
level is the machinery the skill leans on at each step:

  - session_ops.py jot-append (Step 0, via /session-close): the personas
    field that lets /improve group observations by persona (Step 2), and
    the session-dedup that makes a jot re-run a no-op.
  - team_ops.py anchors-unchanged (Step 5.2): the deterministic guard that
    blocks a write when the fenced Immutable Anchors moved, and the exact
    reason string an unfenced persona gets refused with.
  - team_ops.py validate-persona (Step 5.3): the second gate before a
    scratch edit is allowed to land.
  - The atomic-copy + git add/commit + git revert sequence Step 5.4/5.5
    performs by hand (bash, not a script) — reproduced here mechanically to
    prove the spec's rollback story end-to-end: "the commit is the change
    log; git revert is the rollback."

Env-isolation and subprocess pattern mirror test_team_ops_integration.py /
test_session_ops_integration.py: every subprocess.run call gets an explicit,
isolated `env=` (CLAUDE_PLUGIN_DATA pinned to a temp dir) so these tests
never touch a developer machine's real registry, and fixture git repos are
`git init`-ed with `-c user.email=... -c user.name=...` passed on each
commit-creating invocation rather than relying on any global git config
being present on the machine running the suite.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.tests.team_test_utils import PERSONA_BODY, PERSONA_FENCED

SESSION_OPS = Path(__file__).parent.parent / "session_ops.py"
TEAM_OPS = Path(__file__).parent.parent / "team_ops.py"
TEMPLATE = Path(__file__).parent.parent.parent / "assets" / "factory-templates" / "persona.md"

GIT_IDENTITY = ("-c", "user.email=t@t", "-c", "user.name=t")


def _env(isolation_root: Path) -> dict:
    """Copy of the current environment with CLAUDE_PLUGIN_DATA pinned to an
    isolated temp dir, so subprocess calls never touch the real registry."""
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_DATA"] = str(isolation_root / "plugin-data")
    return env


def _run_session_ops(*args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SESSION_OPS), *args],
        capture_output=True, text=True, env=env,
    )


def _run_team_ops(*args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TEAM_OPS), *args],
        capture_output=True, text=True, env=env,
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"git {' '.join(args)} failed: {result.stderr}")
    return result


class TestJotRoundtripWithPersonas(unittest.TestCase):
    """Pins the personas field /improve's Step 2 groups on, and the
    session-dedup that makes a jot re-run a no-op (spec: "pattern-jot
    appends skip if the session ID is already present")."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_jot_roundtrip_with_personas(self):
        home = self.root / "factory-home"
        home.mkdir()
        env = _env(self.root)
        jsonl = home / "patterns" / "pattern-log.jsonl"

        # Seed via CLI with two --persona flags on one call: both
        # observations in this call get tagged with BOTH personas — the
        # skill's own rule ("a line with personas: [wren, marnie]
        # contributes ... to both wren's and marnie's groups").
        seed = _run_session_ops(
            "jot-append",
            "--home", str(home),
            "--session", "2026-07-12-demo",
            "--date", "2026-07-12",
            "--observation", "wants shorter answers",
            "--observation", "dislikes hedging language",
            "--persona", "wren",
            "--persona", "marnie",
            env=env)
        self.assertEqual(seed.returncode, 0, seed.stderr)
        self.assertEqual(json.loads(seed.stdout), {"appended": 2, "skipped": False})

        # Parse the file the way Step 2 does: one JSON object per line.
        lines = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        for row in lines:
            self.assertEqual(row["personas"], ["wren", "marnie"])
            self.assertEqual(row["session"], "2026-07-12-demo")
            self.assertEqual(row["source"], "user-turn")

        # Reproduce the skill's Step 2 grouping-by-persona-slug: every
        # observation with "wren" in its personas list lands in wren's
        # group, same for marnie — the grouping key ("personas") is present
        # and usable on every line, which is what this test pins.
        groups: dict[str, list[str]] = {}
        for row in lines:
            for slug in row.get("personas", []):
                groups.setdefault(slug, []).append(row["observation"])
        self.assertEqual(sorted(groups.keys()), ["marnie", "wren"])
        self.assertEqual(groups["wren"], ["wants shorter answers", "dislikes hedging language"])
        self.assertEqual(groups["marnie"], groups["wren"])

        before_bytes = jsonl.read_bytes()

        # Re-run the SAME session: dedup by session ID makes the whole call
        # a no-op — file untouched, byte-for-byte.
        rerun = _run_session_ops(
            "jot-append",
            "--home", str(home),
            "--session", "2026-07-12-demo",
            "--date", "2026-07-12",
            "--observation", "wants shorter answers",
            "--observation", "dislikes hedging language",
            "--persona", "wren",
            "--persona", "marnie",
            env=env)
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
        self.assertEqual(json.loads(rerun.stdout), {"appended": 0, "skipped": True})
        self.assertEqual(jsonl.read_bytes(), before_bytes)

        # A later call for a DIFFERENT session, with no --persona at all,
        # lands as an unclassified line — the "personas" key is omitted
        # entirely (Phase 4 backward-compat: not written as an empty list),
        # so it groups into the skill's "general / unassigned" bucket.
        unclassified = _run_session_ops(
            "jot-append",
            "--home", str(home),
            "--session", "2026-07-12-other",
            "--date", "2026-07-12",
            "--observation", "no persona context given",
            env=env)
        self.assertEqual(unclassified.returncode, 0, unclassified.stderr)
        rows = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
        unclassified_row = rows[-1]
        self.assertNotIn("personas", unclassified_row)


class TestAnchorsGuardBlocksFencedEdit(unittest.TestCase):
    """/improve's Step 5.2 branch points on a FENCED original: a one-byte
    change inside the fence is refused (exit 1, with a reason); an edit
    confined to the mutable section passes (exit 0)."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_fenced_edit_inside_anchors_is_blocked(self):
        env = _env(self.root)
        original_text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
        # Mutate exactly one byte INSIDE the fence: "data" -> "datA".
        self.assertIn("Never fabricates data", original_text)
        edited_text = original_text.replace(
            "Never fabricates data", "Never fabricates datA")

        original = self.root / "original.md"
        edited = self.root / "edited.md"
        original.write_text(original_text)
        edited.write_text(edited_text)

        result = _run_team_ops("anchors-unchanged", str(original), str(edited), env=env)
        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["reason"])  # a reason is always given on refusal
        self.assertIn("content changed", payload["reason"])

    def test_mutable_only_edit_passes(self):
        env = _env(self.root)
        original_text = PERSONA_FENCED.format(name="Wren", role="Domain Lead", note="v1")
        # Edit only the mutable "Output format" line — fence untouched.
        edited_text = original_text.replace(
            "Output format: v1", "Output format: v2 — prefer bullet points")

        original = self.root / "original.md"
        edited = self.root / "edited.md"
        original.write_text(original_text)
        edited.write_text(edited_text)

        result = _run_team_ops("anchors-unchanged", str(original), str(edited), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["reason"])


class TestGuardBlocksUnfencedOriginal(unittest.TestCase):
    """An unfenced ORIGINAL (no IMMUTABLE:BEGIN/END markers at all) must be
    refused with the exact reason string "original has no fenced anchors" —
    /improve relies on this literal string, not just the exit code: the
    skill's Step 5 recovery branch matches it verbatim to lazily fence the
    persona via upgrade-persona and re-run the guard chain."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_unfenced_original_exact_reason(self):
        env = _env(self.root)
        # PERSONA_BODY has an "## Immutable Anchors" heading but no
        # IMMUTABLE:BEGIN/END fence markers — the pre-upgrade shape.
        original_text = PERSONA_BODY.format(name="Wren", role="Domain Lead")
        edited_text = original_text.replace("Output format", "Output format, revised")

        original = self.root / "original.md"
        edited = self.root / "edited.md"
        original.write_text(original_text)
        edited.write_text(edited_text)

        result = _run_team_ops("anchors-unchanged", str(original), str(edited), env=env)
        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["reason"], "original has no fenced anchors")


class TestFullImproveApplyPath(unittest.TestCase):
    """End-to-end simulation of /improve's Step 5 (Apply, verify, commit)
    against a git-init'd fixture factory home, followed by a `git revert`
    — the spec's rollback story: "the commit is the change log; git revert
    is the rollback." Mechanically reproduces the skill's bash sequence
    (scratch edit -> guard -> validate -> atomic copy -> commit) since
    there is no improve.py script to invoke directly; only the deterministic
    machinery (anchors-unchanged, validate-persona) is real script calls."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def test_full_improve_apply_and_revert_roundtrip(self):
        env = _env(self.root)
        home = self.root / "factory-home"
        (home / "agents").mkdir(parents=True)

        subprocess.run(["git", "init"], cwd=home, capture_output=True, text=True, check=True)

        # A persona filled from the SHIPPED template — per the brief, this
        # fills to a validating persona (description present, CITATION_
        # STANDARD anchor present, no denylist hits with an empty registry).
        filled = (TEMPLATE.read_text()
                  .replace("{{NAME}}", "Wren")
                  .replace("{{ROLE}}", "Domain Lead")
                  .replace("{{DESCRIPTION}}", "Use when testing the improve apply path."))
        persona_path = home / "agents" / "wren.md"
        persona_path.write_text(filled)
        pre_edit_original_bytes = persona_path.read_bytes()

        _git(home, "add", "agents/wren.md")
        _git(home, *GIT_IDENTITY, "commit", "-m", "seed: wren persona")

        # Step 5.1: scratch edit confined to the mutable section — never
        # the real file directly.
        scratch = Path(tempfile.mkdtemp(dir=self.root)) / "wren.md.scratch"
        edited_text = filled.replace(
            "- [Instruction or guideline 1]",
            "- Keep responses under three sentences unless asked to elaborate.")
        self.assertNotEqual(edited_text, filled)  # sanity: the edit actually changed something
        scratch.write_text(edited_text)

        # Step 5.2: the deterministic guard — must pass (exit 0) since the
        # edit never touched the fenced Immutable Anchors.
        guard = _run_team_ops("anchors-unchanged", str(persona_path), str(scratch), env=env)
        self.assertEqual(guard.returncode, 0, guard.stderr)
        self.assertTrue(json.loads(guard.stdout)["ok"])

        # Step 5.3: validate-persona on the scratch copy — must also pass.
        validate = _run_team_ops("validate-persona", str(scratch), env=env)
        self.assertEqual(validate.returncode, 0, validate.stderr)
        validate_payload = json.loads(validate.stdout)
        self.assertTrue(validate_payload["ok"], validate_payload["errors"])

        # Step 5.4: atomic copy scratch -> real file (tmp+rename, mirroring
        # the skill's `cp ... .tmp && mv .tmp <real>`).
        tmp_path = persona_path.with_suffix(persona_path.suffix + ".tmp")
        tmp_path.write_bytes(scratch.read_bytes())
        tmp_path.replace(persona_path)
        self.assertEqual(persona_path.read_bytes(), scratch.read_bytes())

        # Step 5.5: commit this persona's edit alone.
        _git(home, "add", "agents/wren.md")
        commit = _git(home, *GIT_IDENTITY, "commit", "-m",
                       "improve(wren): tighten mutable-instructions wording")
        self.assertEqual(commit.returncode, 0, commit.stderr)

        log = _git(home, "log", "--oneline")
        log_lines = log.stdout.strip().splitlines()
        self.assertEqual(len(log_lines), 2)  # seed commit + improve commit
        self.assertIn("improve(wren): tighten mutable-instructions wording", log.stdout)

        # The rollback story: git revert HEAD undoes exactly this commit,
        # restoring the file to its pre-edit, byte-identical state.
        revert = _git(home, *GIT_IDENTITY, "revert", "HEAD", "--no-edit")
        self.assertEqual(revert.returncode, 0, revert.stderr)

        post_revert_bytes = persona_path.read_bytes()
        self.assertEqual(post_revert_bytes, pre_edit_original_bytes)

        # And the revert itself is a new commit — the original "improve"
        # commit stays in history (the log is the change log; nothing was
        # rewritten), now 3 commits deep.
        log_after = _git(home, "log", "--oneline")
        self.assertEqual(len(log_after.stdout.strip().splitlines()), 3)

        # Working tree is clean after the revert — nothing left dangling.
        status = _git(home, "status", "--porcelain")
        self.assertEqual(status.stdout, "")


if __name__ == "__main__":
    unittest.main()
