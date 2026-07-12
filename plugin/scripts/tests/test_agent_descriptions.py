"""Agent description budget guard. Stdlib only.

Claude Code injects every loaded agent's frontmatter `description` into the
system prompt and warns when the combined total crosses ~15k tokens. This
plugin must stay a good citizen: each bundled agent's description is capped,
and the plugin-wide total is capped, so installing llm-wiki never meaningfully
moves a user toward that ceiling. (Rule of thumb: 1 token ≈ 4 chars.)
"""
import re
import unittest
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parents[2] / "agents"

PER_AGENT_CHAR_BUDGET = 600     # ~150 tokens each
PLUGIN_TOTAL_CHAR_BUDGET = 3000  # ~750 tokens for the whole plugin


def _description(path: Path) -> str:
    text = path.read_text(errors="ignore")
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return ""
    dm = re.search(
        r"^description:\s*(.*?)(?=^[a-zA-Z_-]+:|\Z)",
        m.group(1), re.MULTILINE | re.DOTALL,
    )
    return dm.group(1).strip() if dm else ""


class TestAgentDescriptionBudget(unittest.TestCase):
    def test_agents_dir_exists_with_agents(self):
        self.assertTrue(AGENTS_DIR.is_dir(), f"missing {AGENTS_DIR}")
        self.assertGreater(len(list(AGENTS_DIR.glob("*.md"))), 0)

    def test_every_agent_description_within_budget(self):
        over = []
        for md in sorted(AGENTS_DIR.glob("*.md")):
            n = len(_description(md))
            self.assertGreater(n, 0, f"{md.name}: missing description frontmatter")
            if n > PER_AGENT_CHAR_BUDGET:
                over.append(f"{md.name}: {n} chars (budget {PER_AGENT_CHAR_BUDGET})")
        self.assertEqual(over, [], "agent descriptions over budget:\n" + "\n".join(over))

    def test_plugin_total_description_budget(self):
        total = sum(len(_description(md)) for md in AGENTS_DIR.glob("*.md"))
        self.assertLessEqual(
            total, PLUGIN_TOTAL_CHAR_BUDGET,
            f"plugin agent descriptions total {total} chars "
            f"(~{total // 4} tokens) — budget {PLUGIN_TOTAL_CHAR_BUDGET}",
        )


if __name__ == "__main__":
    unittest.main()
