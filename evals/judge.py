#!/usr/bin/env python3
"""Cross-family judge for llm-wiki eval outputs. Informational — never gates
unless --min-overall. call_judge() is copied verbatim from ship-to-signal
(ai-content/ship-to-signal/evals/judge.py)."""
import argparse, json, os, re, subprocess, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import grade as G

HERE = Path(__file__).resolve().parent
RUBRIC = (HERE / "judge-rubric.md").read_text()
PAGE_CAP = 6000  # chars per evidence page


def call_judge(judge: str, model: str, prompt: str) -> str:
    if judge == "claude":
        r = subprocess.run(
            ["claude", "-p", prompt, "--model", model, "--max-turns", "3",
             "--output-format", "json"],
            capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"claude judge failed: {r.stderr[-400:]}")
        return str(json.loads(r.stdout).get("result", ""))
    if judge == "gemini":
        env = dict(os.environ, GEMINI_CLI_TRUST_WORKSPACE="true")
        if not env.get("GEMINI_API_KEY"):
            project = env.get("GOOGLE_CLOUD_PROJECT") or subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True, text=True).stdout.strip()
            if not project:
                raise RuntimeError("gemini judge needs GEMINI_API_KEY or a gcloud project")
            env.update(GOOGLE_GENAI_USE_VERTEXAI="true", GOOGLE_CLOUD_PROJECT=project,
                       GOOGLE_CLOUD_LOCATION=env.get("EVAL_GEMINI_LOCATION", "global"))
        r = subprocess.run(["gemini", "-m", model, "-p", prompt],
                           capture_output=True, text=True, env=env, timeout=600, cwd="/tmp")
        if r.returncode != 0:
            raise RuntimeError(f"gemini judge failed: {r.stderr[-400:]}")
        return r.stdout
    if judge == "ollama":
        # Hit the local HTTP API directly rather than the `ollama run` CLI —
        # the CLI has no temperature flag, and temperature is an inference
        # parameter the server must apply, not something a model can honor
        # via being asked in the prompt text. Per the LLM-as-judge reliability
        # research, same-verdict rate drops from 95%+ at temp 0 to ~70% at
        # temp 1, so pin it explicitly.
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=json.dumps({"model": model, "prompt": prompt, "stream": False,
                              "options": {"temperature": 0, "num_ctx": 8192}}).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                return json.loads(resp.read()).get("response", "")
        except Exception as e:
            raise RuntimeError(f"ollama judge failed: {e}")
    raise RuntimeError(f"unknown judge '{judge}'")


def collect_query(parsed, fixture, sandbox_wiki):
    answer = parsed["result_text"]
    parts = [f"===== ANSWER =====\n{answer[:PAGE_CAP]}"]
    for slug in G.parse_sources_footer(answer)[:6]:
        for root in (Path(sandbox_wiki) if sandbox_wiki else None, Path(fixture)):
            if root is None:
                continue
            hits = list((root / "wiki").glob(f"**/{G.strip_link(slug)}.md"))
            if hits:
                parts.append(f"===== EVIDENCE {slug} =====\n{hits[0].read_text()[:PAGE_CAP]}")
                break
    return "\n\n".join(parts)


def collect_ingest(artifacts_dir, gt):
    # Reads from .results/<case>-artifacts/ (run.sh persists digests + entity
    # pages there before the pass-path deletes the sandbox).
    parts = []
    for dig in sorted((Path(artifacts_dir) / "digests").glob("*.md")):
        if gt["digest_slug"] in dig.stem or dig.stem in gt.get("new_digests", []):
            parts.append(f"===== DIGEST =====\n{dig.read_text()[:PAGE_CAP]}")
    for t in gt["backprop_targets"]:
        p = Path(artifacts_dir) / f"{t}.md"
        if p.exists():
            parts.append(f"===== ENTITY {t} (post-ingest) =====\n{p.read_text()[:PAGE_CAP]}")
    return "\n\n".join(parts)


def collect_reader(parsed, fixture, stems):
    # Evidence = the case's labeled snapshot stems, not the first N of 158.
    parts = [f"===== SYNTHESIS =====\n{parsed['result_text'][:2*PAGE_CAP]}"]
    for s in stems:
        p = Path(fixture) / "raw" / "snapshots" / f"{s}.md"
        if p.exists():
            parts.append(f"===== SNAPSHOT {s} =====\n{p.read_text()[:PAGE_CAP]}")
    return "\n\n".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--labels", default=os.environ.get("EVAL_LABELS"))
    ap.add_argument("--executor", default=os.environ.get("EVAL_RUNTIME", "claude"))
    ap.add_argument("--judge", choices=["claude", "gemini", "ollama"])
    ap.add_argument("--model")
    ap.add_argument("--min-overall", type=float)
    a = ap.parse_args()
    judge = a.judge or ("gemini" if a.executor == "claude" else "claude")
    model = a.model or {"gemini": "gemini-2.5-pro", "claude": "sonnet",
                        "ollama": "llama3.1:8b"}[judge]
    labels = json.loads((Path(a.labels) / "ground-truth.json").read_text()) \
        if a.labels else {}
    out = {}
    for gpath in sorted(Path(a.results).glob("*.grade.json")):
        d = json.loads(gpath.read_text())
        parsed = G.parse_stream_json(str(Path(a.results) / f"{d['case']}.transcript.jsonl"))
        if parsed["is_error"]:
            continue  # nothing to judge — executor-level failure, already hard-failed
        base_id = d["case"].split("-rep")[0]
        if d["type"] in ("query", "twin"):
            evidence = collect_query(parsed, a.fixture, None)
        elif d["type"] == "reader":
            gt = labels.get("reader", {}).get(base_id, {})
            stems = gt.get("snapshots") or sorted(set(gt.get("answers", {}).values()))
            evidence = collect_reader(parsed, a.fixture, stems)
        else:
            gt = labels.get("ingest", {}).get(base_id)
            art = Path(a.results) / f"{d['case']}-artifacts"
            if not (gt and art.exists()):
                continue
            evidence = collect_ingest(art, gt)
        prompt = f"{RUBRIC}\n\n{evidence}\n\nReturn the JSON now."
        raw = call_judge(judge, model, prompt)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        out[d["case"]] = json.loads(m.group(0)) if m else {"error": raw[:400]}
        print(d["case"], out[d["case"]].get("overall", "?"))
    Path(a.results, "judge.json").write_text(json.dumps(
        {"judge": judge, "model": model, "cases": out}, indent=2) + "\n")
    if a.min_overall is not None:
        worst = min((c.get("overall", 0) for c in out.values()), default=0)
        return 0 if worst >= a.min_overall else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
