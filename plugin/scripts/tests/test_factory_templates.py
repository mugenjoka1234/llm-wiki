import tempfile
import unittest
from pathlib import Path

from scripts import team_ops

TPL = Path(__file__).resolve().parents[2] / "assets" / "factory-templates"


class TestFactoryTemplates(unittest.TestCase):
    def test_persona_template_passes_validation_when_filled(self):
        text = (TPL / "persona.md").read_text()
        for ph in ("{{NAME}}", "{{ROLE}}", "{{DESCRIPTION}}"):
            self.assertIn(ph, text)
        filled = (text.replace("{{NAME}}", "Test")
                      .replace("{{ROLE}}", "Test Role")
                      .replace("{{DESCRIPTION}}", "Use when testing templates."))
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.md"
            p.write_text(filled)
            result = team_ops.validate_persona(p, denylist=[])
            self.assertEqual(result["errors"], [])

    def test_persona_template_ships_fenced_anchor(self):
        text = (TPL / "persona.md").read_text()
        self.assertIn("<!-- IMMUTABLE:BEGIN -->", text)
        self.assertIn("CITATION_STANDARD", text)

    def test_team_template_parses(self):
        t = team_ops.parse_team_yaml((TPL / "team.yaml").read_text())
        self.assertIn("members", t)
        self.assertEqual(t["members"][0]["agent"], "{{AGENT_SLUG}}")
