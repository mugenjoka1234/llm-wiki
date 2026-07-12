#!/usr/bin/env python3
"""Validate agent output envelope + per-agent schema.

Exit codes:
  0 = valid
  1 = malformed (envelope missing / required sections missing)
  2 = error envelope present (agent cleanly reported failure)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


OUTPUT_RE = re.compile(r"<wiki-output>(.*?)</wiki-output>", re.DOTALL)
PLAN_RE = re.compile(r"<wiki-plan>(.*?)</wiki-plan>", re.DOTALL)
ERROR_RE = re.compile(
    r'<wiki-error\s+code="([^"]+)"\s+message="([^"]*)"\s*/>'
)
URL_RE = re.compile(r"\]\(https?://", re.MULTILINE)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def validate(agent: str, content: str) -> tuple[int, str]:
    """Return (exit_code, message)."""
    if agent == "planner":
        m = PLAN_RE.search(content)
        if not m:
            return 1, "planner output missing <wiki-plan>...</wiki-plan> envelope"
        try:
            items = json.loads(m.group(1))
        except (ValueError, TypeError):
            return 1, "planner <wiki-plan> body is not valid JSON"
        if not isinstance(items, list) or not items:
            return 1, "planner plan must be a non-empty JSON array"
        if not all(isinstance(it, dict) and "url" in it for it in items):
            return 1, "planner plan items must be objects with a url"
        return 0, "valid"

    # Error envelope takes priority
    err = ERROR_RE.search(content)
    if err:
        code, msg = err.group(1), err.group(2)
        return 2, f"agent error: code={code} message={msg}"

    # Output envelope required
    m = OUTPUT_RE.search(content)
    if not m:
        return 1, "missing <wiki-output>...</wiki-output> envelope"

    body = m.group(1)

    # Per-agent checks
    if agent == "researcher":
        if "## Sources" not in body:
            return 1, "researcher output missing ## Sources section"
        if "## What I could NOT find" not in body and "could NOT find" not in body:
            return 1, "researcher output missing 'What I could NOT find' section"
        if "## Confidence note" not in body:
            return 1, "researcher output missing ## Confidence note section"
        if not URL_RE.search(body):
            return 1, "researcher output has no URL citations"
    elif agent == "synthesizer":
        if not WIKILINK_RE.search(body):
            return 1, "synthesizer output has no [[wikilink]] citations"
    elif agent == "critic":
        # Either fidelity (severity labels in the **[label]** form) or challenge (section headers).
        # Require the EXACT labeled form rather than keyword presence — the word "unsupported"
        # could appear in unrelated body content ("unsupported browsers") and spoof validation.
        has_severity = bool(re.search(
            r"\*\*\[(unsupported|over-reach|stale|contradiction)\]\*\*", body
        ))
        has_challenge = (
            "## Alternative viewpoints" in body
            and "## Contrary evidence" in body
        )
        if not (has_severity or has_challenge):
            return 1, ("critic output has neither **[severity]** labels (fidelity mode) "
                       "nor ## Alternative viewpoints + ## Contrary evidence (challenge mode)")
    elif agent == "analyst":
        # Minimal check: H1 heading present
        if not re.search(r"^#\s+", body, re.MULTILINE):
            return 1, "analyst output missing H1 heading"

    return 0, "valid"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate agent output.")
    parser.add_argument("--agent", required=True,
                        choices=["researcher", "analyst", "critic", "synthesizer", "planner"])
    parser.add_argument("--content", required=True, help="Path to file OR '-' for stdin.")
    args = parser.parse_args(argv)

    if args.content == "-":
        text = sys.stdin.read()
    else:
        p = Path(args.content)
        if not p.is_file():
            print(f"error: {p} not found", file=sys.stderr)
            return 1
        text = p.read_text()

    code, msg = validate(args.agent, text)
    if code == 0:
        print(f"OK: {msg}")
    else:
        print(msg)
    return code


if __name__ == "__main__":
    sys.exit(main())
