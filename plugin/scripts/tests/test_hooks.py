"""Shape guard for plugin/hooks/hooks.json — the unclosed-session detector's
wiring (SessionEnd -> breadcrumb, SessionStart -> session-check). Mirrors
test_factory_templates.py's style: a static-asset sanity check, not a live
hook-execution test (that lives in test_session_ops_integration.py, which
drives session_ops.py's breadcrumb/session-check subcommands directly)."""
import json
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2] / "hooks" / "hooks.json"
RUN_HOOK = Path(__file__).resolve().parents[2] / "hooks" / "run-hook.sh"


class TestHooksJson(unittest.TestCase):
    def test_parses_as_json(self):
        data = json.loads(HOOKS.read_text())
        self.assertIn("hooks", data)

    def test_references_session_end_and_session_start(self):
        data = json.loads(HOOKS.read_text())["hooks"]
        self.assertIn("SessionEnd", data)
        self.assertIn("SessionStart", data)

    def test_session_start_matches_startup_clear_compact(self):
        data = json.loads(HOOKS.read_text())["hooks"]
        matchers = [entry.get("matcher") for entry in data["SessionStart"]]
        self.assertIn("startup|clear|compact", matchers)

    def test_references_both_subcommands_and_plugin_root(self):
        raw = HOOKS.read_text()
        self.assertIn("breadcrumb", raw)
        self.assertIn("session-check", raw)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", raw)

    def test_commands_invoke_run_hook_sh(self):
        raw = HOOKS.read_text()
        self.assertIn("run-hook.sh", raw)

    def test_run_hook_sh_exists_and_is_executable(self):
        self.assertTrue(RUN_HOOK.is_file())
        import os
        self.assertTrue(os.access(RUN_HOOK, os.X_OK))


if __name__ == "__main__":
    unittest.main()
