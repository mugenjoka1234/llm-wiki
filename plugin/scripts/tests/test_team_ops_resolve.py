import json
import tempfile
import unittest
from pathlib import Path

from scripts import team_ops
from scripts.tests.team_test_utils import make_factory_home, TEAM_YAML


class TestParseTeamYaml(unittest.TestCase):
    def test_parses_meta_and_members(self):
        t = team_ops.parse_team_yaml(TEAM_YAML)
        self.assertEqual(t["id"], "demo-team")
        self.assertEqual(t["name"], "Demo Team")          # quotes stripped
        self.assertEqual(len(t["members"]), 2)
        self.assertEqual(t["members"][0]["agent"], "ada")
        self.assertEqual(t["members"][0]["model"], "claude-sonnet-5")

    def test_quoted_value_with_colon_survives(self):
        t = team_ops.parse_team_yaml(TEAM_YAML)
        self.assertEqual(t["members"][1]["invocation"],
                         "on-demand — only when: needed")
        self.assertEqual(t["purpose"], "Testing: parser handles colons — and dashes")

    def test_unknown_list_block_skipped(self):
        t = team_ops.parse_team_yaml(TEAM_YAML + "\nextras:\n  - x: 1\n")
        self.assertEqual(len(t["members"]), 2)


class TestResolveTeam(unittest.TestCase):
    def test_resolves_present_and_reports_missing(self):
        with tempfile.TemporaryDirectory() as td:
            home = make_factory_home(Path(td))
            out = team_ops.resolve_team(home, "demo-team")
            self.assertEqual([m["agent"] for m in out["members"]], ["ada"])
            self.assertTrue(out["members"][0]["file"].endswith("agents/ada.md"))
            self.assertEqual(out["missing"], [{"agent": "bo", "role": "Missing Member"}])

    def test_unknown_team_raises_with_hint(self):
        with tempfile.TemporaryDirectory() as td:
            home = make_factory_home(Path(td))
            with self.assertRaises(team_ops.TeamError) as cm:
                team_ops.resolve_team(home, "no-such-team")
            self.assertIn("teams/no-such-team.yaml", str(cm.exception))
