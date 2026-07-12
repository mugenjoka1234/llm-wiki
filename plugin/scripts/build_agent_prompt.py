#!/usr/bin/env python3
"""Assemble agent prompts for llm-wiki skills.

Usage:
  build_agent_prompt.py --agent <name> --wiki <path> [--questions "..."]
                        [--target <doc>] [--pages <list>] [--mode <fidelity|challenge>]

Emits the assembled prompt string on stdout. Exit 0 on success, 1 on error.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


class MissingPurposeError(RuntimeError):
    """Raised when CLAUDE.md lacks a ## Purpose section."""


SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _extract_section(text: str, name: str) -> str | None:
    """Return the body of `## <name>` section, or None."""
    pattern = re.compile(r"^##\s+" + re.escape(name) + r"\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return None
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip()


def extract_purpose(claude_md: Path) -> str:
    """Read `## Purpose` section from CLAUDE.md. Raises MissingPurposeError if absent."""
    text = claude_md.read_text()
    body = _extract_section(text, "Purpose")
    if body is None or not body.strip():
        raise MissingPurposeError(f"{claude_md} lacks a ## Purpose section")
    return body.strip()


def extract_entity_types(claude_md: Path) -> list[str]:
    """Read `## Entity types` section and return list of type names.

    Supports three formats (in priority order, first match wins):
      1. Bullet list: `- competitor\n- initiative\n...` (what wiki-init emits)
      2. Comma-separated inline: `competitor, initiative, jtbd`
      3. Markdown table: `| competitor | _templates/competitor.md |` (legacy format)

    Falls back to empty list if none match.
    """
    text = claude_md.read_text()
    body = _extract_section(text, "Entity types")
    if body is None:
        return []

    # Format 1: bullet list.
    bullet_items: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("- "):
            item = s[2:].strip()
            if item:
                bullet_items.append(item)
    if bullet_items:
        return bullet_items

    # Format 2: comma-separated on the first non-empty line
    first_line = next((l for l in body.splitlines() if l.strip()), "")
    if "," in first_line and "|" not in first_line:
        return [t.strip() for t in first_line.split(",") if t.strip()]

    # Format 3: markdown table — first cell of each data row
    types: list[str] = []
    for line in body.splitlines():
        if line.startswith("|") and "|" in line[1:]:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            first = cells[0] if cells else ""
            if first and first != "type" and not first.startswith("-"):
                types.append(first)
    return types


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build agent prompt.")
    parser.add_argument("--agent", required=True,
                        choices=["researcher", "analyst", "critic", "synthesizer", "planner"])
    parser.add_argument("--wiki", required=True, help="Wiki root path.")
    parser.add_argument("--questions", default="", help="Research questions.")
    parser.add_argument("--target", default="", help="Target doc path.")
    parser.add_argument("--pages", default="", help="Comma-separated page list.")
    parser.add_argument("--mode", default="", choices=["", "fidelity", "challenge"])
    parser.add_argument("--snapshots", default="", help="Comma/newline-separated snapshot paths.")
    args = parser.parse_args(argv)

    wiki = Path(args.wiki)
    claude_md = wiki / "CLAUDE.md"
    if not claude_md.is_file():
        print(f"error: {claude_md} not found", file=sys.stderr)
        return 1
    try:
        purpose = extract_purpose(claude_md)
    except MissingPurposeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    types = extract_entity_types(claude_md)

    out = build_prompt(args.agent, purpose, types, args)
    print(out)
    return 0


def build_prompt(agent: str, purpose: str, types: list[str],
                 args: argparse.Namespace) -> str:
    """Assemble the agent-specific prompt string."""
    parts: list[str] = []

    # Domain context block (shared)
    parts.append("# Domain context\n\nThis wiki is for:\n\n" + purpose + "\n")

    # Type vocabulary block (shared)
    if types:
        parts.append("# Type vocabulary\n\n"
                     "Entity types in this wiki: " + ", ".join(types) + ".\n")

    # Agent-specific task block
    if agent == "researcher":
        parts.append(_researcher_task(args))
    elif agent == "analyst":
        parts.append(_analyst_task(args))
    elif agent == "critic":
        parts.append(_critic_task(args))
    elif agent == "synthesizer":
        parts.append(_synthesizer_task(args))
    elif agent == "planner":
        parts.append(_planner_task(args))

    return "\n".join(parts)


def _planner_task(args: argparse.Namespace) -> str:
    # Envelope contracted in agents/wiki-planner.md.
    return (
        "# Your task (wiki-planner)\n\n"
        "Turn the following research question(s) into a ranked, deduped list of\n"
        "source URLs to fetch. Do NOT fetch page bodies — return URLs only.\n\n"
        f"{args.questions}\n\n"
        "# Per-call requirements\n\n"
        "- Output ONLY a `<wiki-plan>` envelope wrapping a JSON array\n"
        "- Each item: {\"url\": \"...\", \"why\": \"...\", \"recency\": \"h|d|w|m|y|null\"}\n"
        "- Prefer primary sources; prefer recent; 5-12 URLs is typical\n"
    )


def _researcher_task(args: argparse.Namespace) -> str:
    # Note: the <wiki-output> envelope and <wiki-error/> channel are contracted
    # in the agent's system prompt (agents/wiki-researcher.md). This task block
    # only injects per-call requirements tied to this dispatch's questions/scope.
    snaps = args.snapshots.replace(",", "\n")
    return (
        "# Your task (wiki-researcher)\n\n"
        "Answer the following questions:\n\n"
        f"{args.questions}\n\n"
        "Synthesize an answer ONLY from these already-fetched snapshot files.\n"
        "Do not access the web — every source is on disk.\n\n"
        "Snapshot files:\n"
        f"{snaps}\n\n"
        "Also read `fetch-manifest.json` in the same snapshots directory.\n\n"
        "# Per-call requirements\n\n"
        "- Cite each claim using the `source_url` in that snapshot's front-block\n"
        "- Required sections: ## Sources, ## What I could NOT find, ## Confidence note\n"
        "- If key questions remain unanswered by these snapshots, you MAY emit ONE\n"
        "  `<need-more queries=\"[...]\" urls=\"[...]\"/>` AFTER the closing </wiki-output>\n"
    )


def _analyst_task(args: argparse.Namespace) -> str:
    # Envelope + error channel contracted in agents/wiki-analyst.md.
    return (
        "# Your task (wiki-analyst)\n\n"
        f"Analyze the following local document: {args.target}\n\n"
        "Produce sections: Summary, Themes, Gaps, Risks, Open questions (per the agent's output schema).\n\n"
        "# Per-call requirements\n\n"
        "- Read the target exhaustively before concluding\n"
    )


def _critic_task(args: argparse.Namespace) -> str:
    # Mode header is LOAD-BEARING — the agent body checks for this exact text
    # to decide fidelity vs challenge schema. Do not reword.
    # Envelope + error channel contracted in agents/wiki-critic.md.
    mode = args.mode or "fidelity"
    if mode == "fidelity":
        return (
            "# Your task (wiki-critic, fidelity mode)\n\n"
            f"Target page: {args.target}\n\n"
            "Verify each claim in the target page is supported by at least one of\n"
            "its cited sources. Flag unsupported claims, over-reach, stale sources,\n"
            "contradictions across sources.\n\n"
            "# Per-call requirements\n\n"
            "- Each finding prefixed with its severity label: **[unsupported]** | **[over-reach]** | **[stale]** | **[contradiction]**\n"
            "- No new-information generation; this is fidelity, not research\n"
        )
    # challenge mode
    return (
        "# Your task (wiki-critic, challenge mode)\n\n"
        f"Target page: {args.target}\n\n"
        "The target page has no cited sources to verify against. CHALLENGE its claims\n"
        "using external evidence. Use WebSearch and WebFetch to find alternative\n"
        "viewpoints, contrary evidence (with URL citations), and hypothesis questions.\n\n"
        "# Per-call requirements\n\n"
        "- Required sections: ## Alternative viewpoints, ## Contrary evidence, ## Hypothesis questions\n"
        "- Every contrary-evidence claim must cite a URL\n"
    )


def _synthesizer_task(args: argparse.Namespace) -> str:
    # Envelope + error channel contracted in agents/wiki-synthesizer.md.
    return (
        "# Your task (wiki-synthesizer)\n\n"
        f"Pages to synthesize: {args.pages}\n\n"
        "Produce a synthesis digest with required sections:\n"
        "- Overview, Key themes, Contradictions (if any), Gaps, Claims-to-follow-up\n\n"
        "# Per-call requirements\n\n"
        "- At least one `[[wikilink]]` citation to a source wiki page for every non-obvious claim\n"
        "- HARD RULE: do not propose modifications to any existing page — synthesis is always a new digest\n"
    )


if __name__ == "__main__":
    sys.exit(main())
