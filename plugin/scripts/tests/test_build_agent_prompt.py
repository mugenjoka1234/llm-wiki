"""Tests for scripts/build_agent_prompt.py. Stdlib only."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "build_agent_prompt.py"


def _make_wiki(root: Path, purpose: str = "Test wiki purpose.",
               entity_types: list[str] | None = None) -> None:
    """Create a minimal wiki with a CLAUDE.md at root."""
    root.mkdir(parents=True, exist_ok=True)
    types = entity_types or ["competitor", "initiative", "jtbd"]
    types_str = ", ".join(types)
    (root / "CLAUDE.md").write_text(
        "# Test Wiki — Schema & Workflows\n\n"
        f"## Purpose\n\n{purpose}\n\n"
        "## Entity types\n\n"
        f"{types_str}\n\n"
        "## Naming conventions\n\nkebab-case.\n"
    )


class TestPurposeExtraction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_extracts_purpose(self):
        _make_wiki(self.root, "This wiki is for competitive intel.")
        from scripts.build_agent_prompt import extract_purpose
        purpose = extract_purpose(self.root / "CLAUDE.md")
        self.assertIn("competitive intel", purpose)

    def test_missing_purpose_raises(self):
        (self.root / "CLAUDE.md").write_text("# No purpose here\n\n## Other\n\n...\n")
        from scripts.build_agent_prompt import extract_purpose, MissingPurposeError
        with self.assertRaises(MissingPurposeError):
            extract_purpose(self.root / "CLAUDE.md")

    def test_extracts_entity_types_inline_comma(self):
        _make_wiki(self.root, "Test.", entity_types=["competitor", "initiative"])
        from scripts.build_agent_prompt import extract_entity_types
        types = extract_entity_types(self.root / "CLAUDE.md")
        self.assertIn("competitor", types)
        self.assertIn("initiative", types)

    def test_extracts_entity_types_bullet_list(self):
        """wiki-init scaffold outputs entity types as a bullet list — must parse that shape."""
        (self.root / "CLAUDE.md").write_text(
            "# Test\n\n## Purpose\n\nTest.\n\n"
            "## Entity types\n\n"
            "- competitor\n"
            "- initiative\n"
            "- jtbd\n\n"
            "## Next section\n"
        )
        from scripts.build_agent_prompt import extract_entity_types
        types = extract_entity_types(self.root / "CLAUDE.md")
        self.assertEqual(types, ["competitor", "initiative", "jtbd"])

    def test_extracts_entity_types_markdown_table(self):
        """Legacy wikis used a markdown table — must parse that shape too."""
        (self.root / "CLAUDE.md").write_text(
            "# Test\n\n## Purpose\n\nTest.\n\n"
            "## Entity types\n\n"
            "| type | template |\n"
            "|---|---|\n"
            "| competitor | _templates/competitor.md |\n"
            "| initiative | _templates/initiative.md |\n\n"
            "## Next section\n"
        )
        from scripts.build_agent_prompt import extract_entity_types
        types = extract_entity_types(self.root / "CLAUDE.md")
        self.assertIn("competitor", types)
        self.assertIn("initiative", types)


class TestPromptAssembly(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)
        _make_wiki(self.root, "Research and analysis.",
                   entity_types=["competitor", "initiative", "jtbd"])

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_researcher_prompt_contains_purpose_and_questions(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--agent", "researcher",
             "--wiki", str(self.root),
             "--questions", "What is X? What is Y?"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("Research and analysis", result.stdout)
        self.assertIn("What is X?", result.stdout)
        self.assertIn("Sources", result.stdout)
        self.assertIn("Confidence", result.stdout)

    def test_critic_prompt_includes_mode(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--agent", "critic",
             "--wiki", str(self.root),
             "--mode", "fidelity",
             "--target", "shopify-competitor"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("fidelity", result.stdout.lower())
        self.assertIn("shopify-competitor", result.stdout)

    def test_critic_challenge_mode_mentions_web_research(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--agent", "critic",
             "--wiki", str(self.root),
             "--mode", "challenge",
             "--target", "some-page"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("challenge", result.stdout.lower())
        out_lower = result.stdout.lower()
        self.assertTrue("web" in out_lower or "contrary" in out_lower)

    def test_critic_mode_header_is_load_bearing(self):
        """The agent body parses the exact header '# Your task (wiki-critic, <mode> mode)'
        to decide schema. Verify build_agent_prompt emits this verbatim."""
        for mode in ("fidelity", "challenge"):
            result = subprocess.run(
                [sys.executable, str(SCRIPT),
                 "--agent", "critic",
                 "--wiki", str(self.root),
                 "--mode", mode,
                 "--target", "x"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0)
            expected_header = f"# Your task (wiki-critic, {mode} mode)"
            self.assertIn(expected_header, result.stdout,
                          f"expected exact header for mode={mode}")

    def test_missing_purpose_exits_nonzero(self):
        bad = self.root / "bad"
        bad.mkdir()
        (bad / "CLAUDE.md").write_text("# Bad\n\n## Other\n\nNo purpose.\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--agent", "researcher",
             "--wiki", str(bad),
             "--questions", "X?"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Purpose", result.stderr)


import argparse

from scripts import build_agent_prompt as bap


def _args(**kw):
    base = dict(questions="", target="", pages="", mode="", snapshots="")
    base.update(kw)
    return argparse.Namespace(**base)


class TestPlannerAndReaderTasks(unittest.TestCase):
    def test_planner_task_mentions_wiki_plan_and_questions(self):
        out = bap._planner_task(_args(questions="What is X?"))
        self.assertIn("wiki-planner", out)
        self.assertIn("<wiki-plan>", out)
        self.assertIn("What is X?", out)

    def test_researcher_task_reads_snapshots_not_web(self):
        out = bap._researcher_task(_args(snapshots="raw/snapshots/a.md,raw/snapshots/b.md"))
        self.assertIn("raw/snapshots/a.md", out)
        self.assertIn("source_url", out)
        self.assertIn("fetch-manifest.json", out)
        # must NOT tell the agent to search/fetch the web
        self.assertNotIn("WebSearch", out)
        self.assertNotIn("WebFetch", out)


if __name__ == "__main__":
    unittest.main()
