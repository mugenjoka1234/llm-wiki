"""Tests for scripts/validate_agent_output.py. Stdlib only."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "validate_agent_output.py"


def _write(path: Path, content: str) -> None:
    path.write_text(content)


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_valid_research_exits_zero(self):
        content = self.root / "out.md"
        _write(content,
               "<wiki-output>\n"
               "# Research: Shopify\n\n"
               "## Sources\n- [Shopify](https://shopify.com) — retrieved 2026-05-07\n\n"
               "## What I could NOT find\n- Foo\n\n"
               "## Confidence note\n\nHigh confidence on structural claims.\n"
               "</wiki-output>\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--agent", "researcher", "--content", str(content)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

    def test_missing_envelope_exits_one(self):
        content = self.root / "out.md"
        _write(content, "# Just some markdown, no envelope\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--agent", "researcher", "--content", str(content)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("envelope", result.stdout + result.stderr)

    def test_error_envelope_exits_two(self):
        content = self.root / "out.md"
        _write(content,
               '<wiki-error code="missing_input" message="no target page"/>\n')
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--agent", "researcher", "--content", str(content)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)
        # Should print code and message
        self.assertIn("missing_input", result.stdout + result.stderr)

    def test_research_missing_sources_section_fails(self):
        content = self.root / "out.md"
        _write(content,
               "<wiki-output>\n# Research\n\nSome text.\n</wiki-output>\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--agent", "researcher", "--content", str(content)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Sources", result.stdout + result.stderr)

    def test_synthesizer_requires_wikilink(self):
        content = self.root / "out.md"
        _write(content,
               "<wiki-output>\n# Synthesis\n\nNo wikilinks here.\n</wiki-output>\n")
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--agent", "synthesizer", "--content", str(content)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("wikilink", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
