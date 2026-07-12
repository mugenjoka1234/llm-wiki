#!/usr/bin/env python3
"""Graphify Wiki Indexer - Lightweight Python stdlib-only AST graph compiler for llm-wiki.
Compiles a structured, searchable _graph.json mapping entities, headers, and keywords to line ranges.
Usage:
  python3 scripts/graphify_wiki.py --wiki-root /path/to/wiki
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

# Match YAML frontmatter
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text)."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_text, body = m.group(1), m.group(2)
    fm: dict = {}
    lines = fm_text.splitlines()
    for line in lines:
        line = line.rstrip()
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # Clean inline list brackets
        if val.startswith("[") and val.endswith("]"):
            items = [item.strip().strip('"').strip("'") for item in val[1:-1].split(",") if item.strip()]
            fm[key] = items
        else:
            fm[key] = val.strip('"').strip("'")
    return fm, body

def build_graph(wiki_root: Path) -> dict:
    """Scan the wiki folder and compile the semantic JSON index."""
    wiki_dir = wiki_root / "wiki"
    if not wiki_dir.is_dir():
        raise Exception(f"wiki directory not found under {wiki_root}")

    graph = {
        "metadata": {
            "generated_at": "",
            "total_pages": 0,
            "total_headings": 0
        },
        "pages": {},      # page_slug -> {type, summary, sources, related, path}
        "headings": [],   # list of {text, slug, path, start_line, end_line, level, parent_headings}
        "entities": {},   # entity_slug -> list of {path, heading, start_line, end_line, summary}
        "keywords": {}    # keyword -> list of {path, heading, start_line, end_line}
    }

    # Standardized list of keywords to index
    keywords_list = [
        "rates", "cost", "pricing", "monetization", "subscription", "lead-fee", "commission", "take-rate",
        "medicaid", "insurance", "coverage", "aca", "bcbs", "anthem", "superbill", "billing", "cpt", "hcpcs",
        "privacy", "compliance", "mhmda", "hbnr", "geofencing", "consent", "sdk", "data-leak", "dobbs",
        "booking", "deposit", "retainer", "roster", "supply", "conflict", "backup", "windows"
    ]

    md_files = sorted(list(wiki_dir.glob("**/*.md")))
    graph["metadata"]["total_pages"] = len(md_files)

    for md_file in md_files:
        if md_file.name.startswith("_") or ".obsidian" in md_file.parts:
            continue
            
        rel_path = md_file.relative_to(wiki_dir)
        slug = str(rel_path.with_suffix("")).replace("\\", "/")
        text = md_file.read_text()
        
        # Parse frontmatter and body
        fm, body = parse_frontmatter(text)
        graph["pages"][slug] = {
            "type": fm.get("type", "stub"),
            "summary": fm.get("summary", ""),
            "sources": fm.get("sources", []),
            "related": fm.get("related", []),
            "path": f"wiki/{rel_path}"
        }

        # Analyze body structure and headers
        lines = text.splitlines()
        headings_stack: list[dict] = []
        
        for idx, line in enumerate(lines):
            line_num = idx + 1
            h_match = HEADER_RE.match(line)
            
            if h_match:
                level = len(h_match.group(1))
                heading_text = h_match.group(2).strip()
                graph["metadata"]["total_headings"] += 1
                
                # Check for wikilinks in heading (e.g. `### [[cleo]]`)
                heading_slugs = WIKILINK_RE.findall(heading_text)
                
                # Pop headers of equal or higher level from stack
                while headings_stack and headings_stack[-1]["level"] >= level:
                    prev_h = headings_stack.pop()
                    prev_h["end_line"] = line_num - 1
                    graph["headings"].append(prev_h)
                    
                    # Update entities mapping
                    for hs in prev_h["heading_slugs"]:
                        graph["entities"].setdefault(hs, []).append({
                            "path": f"wiki/{rel_path}",
                            "heading": prev_h["text"],
                            "start_line": prev_h["start_line"],
                            "end_line": prev_h["end_line"]
                        })
                
                # Push new heading
                headings_stack.append({
                    "text": heading_text,
                    "heading_slugs": heading_slugs,
                    "path": f"wiki/{rel_path}",
                    "start_line": line_num,
                    "end_line": len(lines),  # provisionally end of file
                    "level": level,
                    "parent_headings": [h["text"] for h in headings_stack]
                })

            # Inverted keyword indexing within current heading context
            lower_line = line.lower()
            current_heading_text = headings_stack[-1]["text"] if headings_stack else ""
            current_start = headings_stack[-1]["start_line"] if headings_stack else 1
            
            for kw in keywords_list:
                if kw in lower_line:
                    graph["keywords"].setdefault(kw, []).append({
                        "path": f"wiki/{rel_path}",
                        "heading": current_heading_text,
                        "line": line_num
                    })

        # Close out any remaining headers on stack at end of file
        while headings_stack:
            prev_h = headings_stack.pop()
            prev_h["end_line"] = len(lines)
            graph["headings"].append(prev_h)
            
            for hs in prev_h["heading_slugs"]:
                graph["entities"].setdefault(hs, []).append({
                    "path": f"wiki/{rel_path}",
                    "heading": prev_h["text"],
                    "start_line": prev_h["start_line"],
                    "end_line": prev_h["end_line"]
                })

    return graph

def main():
    parser = argparse.ArgumentParser(description="Graphify Wiki Compiler")
    parser.add_argument("--wiki-root", type=str, required=True, help="Path to the wiki root directory")
    args = parser.parse_args()

    wiki_root = Path(args.wiki_root)
    graph = build_graph(wiki_root)
    
    # Save graph.json
    import datetime
    graph["metadata"]["generated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    output_path = wiki_root / "wiki/_graph.json"
    output_path.write_text(json.dumps(graph, indent=2))
    print(f"Graph compiled successfully! Written {len(graph['pages'])} pages and {len(graph['entities'])} entities to {output_path}")

if __name__ == "__main__":
    main()
