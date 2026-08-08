#!/usr/bin/env python3
"""Deterministic grader for llm-wiki evals. Pure functions first; CLI at bottom."""
import json, os, re
from pathlib import Path

WEIGHTS = {"input_tokens": 1.0, "cache_creation_input_tokens": 1.25,
           "cache_read_input_tokens": 0.1, "output_tokens": 5.0}
FOOTER_RE = re.compile(r"SOURCES \(most relevant first\):\s*(.+)", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s)\]>\"']+")

def strip_link(link):
    s = link.strip()
    if s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2]
    return s.split("|")[0].split("#")[0].strip()

def parse_sources_footer(text):
    hits = FOOTER_RE.findall(text or "")
    if not hits:
        return []
    # Only [[wikilinks]] and raw/ paths — bare words on the footer line are prose,
    # not slugs; sweeping them in pollutes P@5 and false-fails resolution.
    return [strip_link(t) for t in re.findall(r"\[\[[^\]]+\]\]|raw/[\w./-]+", hits[-1])]

def load_graph(fixture_root):
    p = Path(fixture_root) / "wiki" / "_graph.json"
    return json.loads(p.read_text()) if p.exists() else {}

def resolve_link(slug, fixture_root, sandbox_wiki, graph):
    slug = strip_link(slug)
    sb = Path(sandbox_wiki)
    if (sb / "wiki" / f"{slug}.md").exists() or (sb / slug).exists() \
       or list((sb / "wiki").glob(f"**/{slug}.md")):
        return True
    return slug in graph.get("pages", {}) or slug in graph.get("entities", {})

def precision_recall_mrr(footer, relevant, primary):
    k = min(5, len(footer))
    top = footer[:k]
    hits = sum(1 for s in top if s in relevant)
    p5 = hits / k if k else 0.0
    r5 = (sum(1 for s in relevant if s in footer[:5]) / len(relevant)) if relevant else 0.0
    mrr = 0.0
    for rank, s in enumerate(footer, 1):
        if s in set(primary):
            mrr = 1.0 / rank
            break
    return {"p_at_5": p5, "r_at_5": r5, "mrr": mrr}

def parse_stream_json(path):
    out = {"result_text": "", "reads": [], "usage": {}, "total_cost_usd": 0.0,
           "num_turns": 0}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "assistant":
            for blk in (obj.get("message") or {}).get("content", []):
                if blk.get("type") == "tool_use" and blk.get("name") == "Read":
                    fp = (blk.get("input") or {}).get("file_path")
                    if fp:
                        out["reads"].append(fp)
        elif obj.get("type") == "result":
            out["result_text"] = str(obj.get("result", ""))
            out["usage"] = obj.get("usage") or {}
            out["total_cost_usd"] = float(obj.get("total_cost_usd") or 0.0)
            out["num_turns"] = int(obj.get("num_turns") or 0)
    return out

def weighted_tokens(usage):
    return sum(WEIGHTS[k] * float(usage.get(k, 0)) for k in WEIGHTS)

def extract_urls(text):
    return {u.rstrip(".,;:)") for u in URL_RE.findall(text or "")}

def lint_delta(current_lines, baseline_lines):
    base = set(baseline_lines)
    return [l for l in current_lines if l not in base]
