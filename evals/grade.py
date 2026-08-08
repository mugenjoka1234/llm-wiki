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

def _grade_query(gt, sandbox, fixture, parsed):
    graph = load_graph(fixture)
    footer = parse_sources_footer(parsed["result_text"])
    inprose = [strip_link(m) for m in re.findall(r"\[\[[^\]]+\]\]", parsed["result_text"])]
    hard = {
        "answer_nonempty": bool(parsed["result_text"].strip()),
        "footer_present": bool(footer),
        "all_links_resolve": all(resolve_link(s, fixture, sandbox, graph)
                                 for s in set(footer + inprose)),
    }
    metrics = precision_recall_mrr(footer, set(gt["relevant"]), gt["primary"])
    soft = {"reads_within_cap": len([r for r in parsed["reads"] if "/wiki/" in r]) <= 15}
    return hard, soft, metrics

def _grade_ingest(gt, sandbox, fixture, parsed, pristine_raw):
    import shutil, subprocess as sp, tempfile
    digests = Path(sandbox) / "wiki" / "digests"
    dig = next(iter(sorted(digests.glob(f"*{gt['digest_slug']}*.md"))), None)
    hard = {"digest_exists": dig is not None}
    if dig:
        pristine_urls = extract_urls(Path(pristine_raw).read_text())
        hard["no_invented_urls"] = extract_urls(dig.read_text()) <= pristine_urls
        hard["digest_is_source_type"] = "type: source" in dig.read_text()[:400]
    for t in gt["backprop_targets"]:
        page = Path(sandbox) / "wiki" / f"{t}.md"
        ptext = page.read_text() if page.exists() else ""
        # Exact "## From [[<digest>]]" section AND the digest in the frontmatter
        # sources block — live pages carry many pre-existing From-sections.
        fm = ptext.split("---")[1] if ptext.count("---") >= 2 else ""
        hard[f"backprop:{t}"] = bool(dig) and f"## From [[{dig.stem}]]" in ptext \
                                and dig.stem in fm
    # MANIFEST: scoped to the seeded file — the real MANIFEST has pre-existing
    # [x] lines and one pre-existing pending-ingest entry the agent must not touch.
    fix_name = Path(pristine_raw).name
    man = Path(sandbox) / "raw" / "MANIFEST.md"
    man_lines = [l for l in (man.read_text().splitlines() if man.exists() else [])
                 if f"`{fix_name}`" in l]
    hard["manifest_flipped"] = bool(man_lines) and all(
        "- [x]" in l and "ingested" in l and "pending-ingest" not in l
        for l in man_lines)
    # Lint delta: same-day, same-env double run — lint a fresh COPY of the
    # pristine fixture (lint mutates its target; staleness output shifts over
    # time, so the manifest's frozen baseline is documentation, not the reference).
    r = sp.run(["python3", str(Path(sandbox) / "scripts" / "lint.py")],
               cwd=sandbox, capture_output=True, text=True)
    cur = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()]
    with tempfile.TemporaryDirectory() as td:
        ref = Path(td) / "ref"
        shutil.copytree(fixture, ref,
                        ignore=shutil.ignore_patterns("fixture-manifest.json"))
        rb = sp.run(["python3", str(ref / "scripts" / "lint.py")],
                    cwd=ref, capture_output=True, text=True)
    base = [l for l in (rb.stdout + rb.stderr).splitlines() if l.strip()]
    delta = lint_delta(cur, base)
    hard["lint_delta_clean"] = (r.returncode < 2) and not delta
    return hard, {"lint_delta": delta}, {}

def _front_block_urls(path):
    m = re.match(r"(?s)^---\n(.*?)\n---", path.read_text())
    return extract_urls(m.group(1)) if m else set()

def _grade_reader(gt, sandbox, fixture, parsed):
    text = parsed["result_text"]
    # Only the case's labeled snapshot stems, and only their YAML front-block
    # URLs — snapshot bodies are full of incidental URLs a fabricated citation
    # could collide with.
    stems = gt.get("snapshots") or sorted(set(gt["answers"].values()))
    snaps = {}
    for s in stems:
        p = Path(fixture) / "raw" / "snapshots" / f"{s}.md"
        snaps[s] = _front_block_urls(p) if p.exists() else set()
    allowed = set().union(*snaps.values()) if snaps else set()
    cited = extract_urls(text)
    hard = {"urls_from_snapshots": bool(cited) and cited <= allowed}
    for q, stem in gt["answers"].items():
        m = re.search(rf"{q} SOURCES:\s*(.+)", text)
        q_urls = extract_urls(m.group(1)) if m else set()
        hard[f"{q}_cites_right_snapshot"] = bool(q_urls & snaps.get(stem, set()))
    return hard, {}, {}

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    for f in ("case-id", "case-type", "sandbox", "fixture", "labels",
              "transcript", "out"):
        ap.add_argument("--" + f, required=True)
    ap.add_argument("--pristine-raw")
    a = ap.parse_args(argv)

    manifest = json.loads((Path(a.fixture) / "fixture-manifest.json").read_text())
    labels = json.loads((Path(a.labels) / "ground-truth.json").read_text())
    if labels["fixture_hash"] != manifest["content_hash"]:
        print("REFUSED: ground-truth fixture_hash != fixture content_hash (stale labels)")
        return 2

    parsed = parse_stream_json(a.transcript)
    kind = "query" if a.case_type == "twin" else a.case_type
    gt = labels.get(kind, {}).get(a.case_id) or labels.get(kind, {}).get(
        a.case_id.replace("twin", "q").split("-rep")[0])
    if gt is None:
        print(f"REFUSED: no ground truth for {a.case_id}")
        return 2
    if a.case_type in ("query", "twin"):
        hard, soft, metrics = _grade_query(gt, a.sandbox, a.fixture, parsed)
    elif a.case_type == "ingest":
        hard, soft, metrics = _grade_ingest(gt, a.sandbox, a.fixture, parsed,
                                            a.pristine_raw)
    else:
        hard, soft, metrics = _grade_reader(gt, a.sandbox, a.fixture, parsed)

    result = {"case": a.case_id, "type": a.case_type,
              "pass": all(hard.values()), "hard": hard, "soft": soft,
              "metrics": metrics,
              "tokens": {"usage": parsed["usage"],
                         "weighted": weighted_tokens(parsed["usage"]),
                         "cost_usd": parsed["total_cost_usd"],
                         "turns": parsed["num_turns"]}}
    Path(a.out).write_text(json.dumps(result, indent=2) + "\n")
    print(("PASS " if result["pass"] else "FAIL ") + a.case_id)
    return 0 if result["pass"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
