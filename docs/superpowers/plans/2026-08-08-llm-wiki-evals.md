# llm-wiki Eval Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the model-in-the-loop eval suite for the llm-wiki plugin per the approved spec (`docs/superpowers/specs/2026-08-08-llm-wiki-evals-design.md`).

**Architecture:** Mirror of the ship-to-signal harness (`~/Documents/GitHub/ai-content/ship-to-signal/evals/`): `cases.json` → per-case temp sandbox (frozen wiki fixture + plugin copy) → one headless executor per run → deterministic `grade.py` vs `ground-truth.json` → informational cross-family `judge.py`. Private fixture and labels live outside the repo, addressed by `EVAL_WIKI` / `EVAL_LABELS`.

**Tech Stack:** bash 3.2-compatible shell (macOS stock), Python 3 stdlib only (no pip deps), `claude` CLI (executor + one judge family), `gemini` CLI (other judge family).

## Global Constraints

- Repo: `/Users/pranayagrawal/Documents/GitHub/llm-wiki-poc-main` — everything below is relative to it unless absolute.
- **Privacy:** `evals/.results/` is gitignored BEFORE any run. `cases.json` and `ground-truth.json` never enter the repo — they live at `$EVAL_LABELS` (default `$EVAL_WIKI/../eval-labels`). In-repo prompts are templates; question text is interpolated at runtime.
- **Sandbox env, exported unconditionally per case:** `CLAUDE_PLUGIN_ROOT=<sandbox>/plugin`, `CLAUDE_PLUGIN_DATA=<sandbox>/plugin-data`.
- Executor (claude): `--output-format stream-json --verbose --permission-mode bypassPermissions` — never plain `json` (no tool records).
- Weighted tokens: `W = input + 1.25*cache_creation + 0.1*cache_read + 5*output` (sonnet ratios).
- P@5 denominator: `min(5, |footer|)`. MRR over labeled `primary` pages. Wikilink resolver reads `_graph.json` from pristine `$EVAL_WIKI`, never the sandbox.
- Ingest lint check is **delta vs the baseline** recorded in `fixture-manifest.json` (live wiki has 7 pre-existing oversize warnings); hard-fail only on new warnings or exit 2.
- Fixture URLs in designed ingest files use `https://eval-fixture.invalid/...` (RFC 2606 reserved TLD).
- macOS bash 3.2: no arrays for optional flags, no `${var,,}`, `set -u`-safe (see s2s run.sh comments).
- Commit after every task; messages end with the standard Co-Authored-By/Claude-Session trailer used in this session.

## File Structure

```
evals/
  README.md            # Task 9
  run.sh               # Task 6
  grade.py             # Tasks 3–4 (pure functions + CLI)
  judge.py             # Task 7 (adapted from s2s)
  judge-rubric.md      # Task 7
  snapshot.sh          # Task 2
  prompts/
    query.tmpl.md      # Task 5 (twins reuse it)
    ingest.tmpl.md     # Task 5
    reader.tmpl.md     # Task 5
  fixtures/ingest/
    eval-fixture-tokens.md   # Task 8
    eval-fixture-memory.md   # Task 8
  tests/
    test_grade.py      # Task 3 (stdlib unittest)
.gitignore             # Task 1 (add evals/.results/)
```

Private (created in Task 9, never committed): `$EVAL_WIKI/` (snapshot), `$EVAL_LABELS/cases.json`, `$EVAL_LABELS/ground-truth.json`.

---

### Task 1: Scaffold + privacy guard

**Files:**
- Create: `evals/README.md` (stub), `evals/prompts/.gitkeep`, `evals/fixtures/ingest/.gitkeep`, `evals/tests/.gitkeep`
- Modify: `.gitignore`

**Interfaces:** Produces the directory layout every later task writes into; the `.gitignore` line is the privacy gate the spec requires before any run.

- [ ] **Step 1: Create layout and gitignore entry**

```bash
cd /Users/pranayagrawal/Documents/GitHub/llm-wiki-poc-main
mkdir -p evals/prompts evals/fixtures/ingest evals/tests
touch evals/prompts/.gitkeep evals/fixtures/ingest/.gitkeep evals/tests/.gitkeep
grep -q '^evals/.results/' .gitignore 2>/dev/null || printf '\n# eval transcripts embed private wiki text\nevals/.results/\n' >> .gitignore
```

- [ ] **Step 2: Write the README stub** — content exactly:

```markdown
# llm-wiki evals

Model-in-the-loop eval suite. See `docs/superpowers/specs/2026-08-08-llm-wiki-evals-design.md` for the design.

**Privacy:** the fixture wiki and the labels (`cases.json`, `ground-truth.json`) are PRIVATE — they live at `$EVAL_WIKI` / `$EVAL_LABELS`, never in this repo. `evals/.results/` is gitignored: transcripts embed wiki text verbatim. Do not weaken either guard.

Full run instructions land here in the final task.
```

- [ ] **Step 3: Verify the guard works**

```bash
mkdir -p evals/.results && touch evals/.results/probe && git status --porcelain | grep -c '.results' # expect 0
rm -r evals/.results
```

- [ ] **Step 4: Commit** — `git add .gitignore evals && git commit -m "feat(evals): scaffold + privacy guard"`

---

### Task 2: snapshot.sh — freeze a wiki into a fixture

**Files:**
- Create: `evals/snapshot.sh`

**Interfaces:**
- Consumes: a live wiki root (arg 1), a destination dir (arg 2).
- Produces: `<dest>/` (wiki copy, no `.git`) + `<dest>/fixture-manifest.json` with keys `{"frozen": "YYYY-MM-DD", "source": "<abs src>", "content_hash": "<sha256>", "lint_baseline": ["<warning line>", ...], "lint_exit": <int>}`. `grade.py` (Task 4) reads `content_hash`, `lint_baseline`, `lint_exit`.

- [ ] **Step 1: Write `evals/snapshot.sh`**

```bash
#!/usr/bin/env bash
# Freeze a live wiki into an eval fixture. Usage: snapshot.sh <wiki-root> <dest-dir>
set -eu
SRC="${1:?usage: snapshot.sh <wiki-root> <dest-dir>}"
DEST="${2:?usage: snapshot.sh <wiki-root> <dest-dir>}"
[ -d "$SRC/wiki" ] || { echo "not a wiki root (no wiki/): $SRC"; exit 2; }
mkdir -p "$DEST"
rsync -a --delete --exclude '.git' --exclude 'fixture-manifest.json' "$SRC/" "$DEST/"

python3 - "$SRC" "$DEST" <<'PYEOF'
import hashlib, json, subprocess, sys, datetime
from pathlib import Path
src, dest = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()

# Lint FIRST — lint.py mutates its target (writes _health.md, regenerates
# catalogs, autofixes trust lines). Hashing before lint would record bytes the
# fixture no longer has the moment it's created.
r = subprocess.run([sys.executable, str(dest / "scripts" / "lint.py")],
                   cwd=dest, capture_output=True, text=True)
baseline = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()]

# Hash SECOND: sorted relative paths + file bytes, post-lint = the stable state
h = hashlib.sha256()
for p in sorted(dest.rglob("*")):
    if p.is_file() and p.name != "fixture-manifest.json":
        h.update(str(p.relative_to(dest)).encode())
        h.update(p.read_bytes())

manifest = {
    "frozen": datetime.date.today().isoformat(),
    "source": str(src),
    "content_hash": h.hexdigest(),
    "lint_baseline": baseline,
    "lint_exit": r.returncode,
}
(dest / "fixture-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({"content_hash": manifest["content_hash"][:12],
                  "lint_exit": r.returncode, "baseline_lines": len(baseline)}))
PYEOF
```

- [ ] **Step 2: Test against the real wiki into a temp dir**

```bash
chmod +x evals/snapshot.sh
bash evals/snapshot.sh ~/Documents/GitHub/ai-content/ai-content-wiki /tmp/wiki-fixture-test
python3 -c "
import json; m=json.load(open('/tmp/wiki-fixture-test/fixture-manifest.json'))
assert set(m) == {'frozen','source','content_hash','lint_baseline','lint_exit'}, m.keys()
assert len(m['content_hash']) == 64
print('manifest OK, lint_exit =', m['lint_exit'], ', baseline lines =', len(m['lint_baseline']))"
ls /tmp/wiki-fixture-test/.git 2>/dev/null && echo "FAIL: .git leaked" || echo "no .git — OK"
```

Expected: `manifest OK`, `no .git — OK`. Re-run snapshot.sh again → `content_hash` must be identical (determinism check): capture the hash from both runs and `diff`.

- [ ] **Step 3: Clean up and commit** — `rm -rf /tmp/wiki-fixture-test; git add evals/snapshot.sh && git commit -m "feat(evals): snapshot.sh fixture freezer with lint baseline"`

---

### Task 3: grade.py pure functions (TDD)

**Files:**
- Create: `evals/grade.py` (functions only; CLI added in Task 4)
- Test: `evals/tests/test_grade.py`

**Interfaces:**
- Produces (Task 4, run.sh, and tests rely on these exact signatures):
  - `strip_link(link: str) -> str` — `"[[a|b]]"`→`"a"`, `"[[p#s]]"`→`"p"`, bare `"a"`→`"a"`
  - `parse_sources_footer(text: str) -> list[str]` — ordered slugs from the LAST line matching `SOURCES (most relevant first):`; `[]` if absent
  - `load_graph(fixture_root: str) -> dict` — parsed `_graph.json` from the PRISTINE fixture (`<fixture>/wiki/_graph.json`), `{}` if missing
  - `resolve_link(slug: str, fixture_root: str, sandbox_wiki: str, graph: dict) -> bool`
  - `precision_recall_mrr(footer: list[str], relevant: set[str], primary: list[str]) -> dict` — keys `p_at_5`, `r_at_5`, `mrr`
  - `parse_stream_json(path: str) -> dict` — keys `result_text` (str), `reads` (list of file paths from Read tool_use blocks), `usage` (dict), `total_cost_usd` (float), `num_turns` (int)
  - `weighted_tokens(usage: dict) -> float`
  - `extract_urls(text: str) -> set[str]` — every `https?://...` token, trailing punctuation stripped
  - `lint_delta(current_lines: list[str], baseline_lines: list[str]) -> list[str]` — lines in current not in baseline

- [ ] **Step 1: Write the failing tests** — `evals/tests/test_grade.py`:

```python
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import grade

class TestLinks(unittest.TestCase):
    def test_strip_alias_anchor(self):
        self.assertEqual(grade.strip_link("[[a-page|nice name]]"), "a-page")
        self.assertEqual(grade.strip_link("[[a-page#section]]"), "a-page")
        self.assertEqual(grade.strip_link("[[a-page]]"), "a-page")
        self.assertEqual(grade.strip_link("a-page"), "a-page")

    def test_footer_parse(self):
        t = "prose [[x]] more\nSOURCES (most relevant first): [[a]], [[b|B]], [[c#s]]\n"
        self.assertEqual(grade.parse_sources_footer(t), ["a", "b", "c"])
        self.assertEqual(grade.parse_sources_footer("no footer here"), [])

    def test_resolver_file_pages_entities(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "wiki"))
            open(os.path.join(d, "wiki", "real-page.md"), "w").write("x")
            graph = {"pages": {"graph-page": {"path": "wiki/graph-page.md"}},
                     "entities": {"embedded-entity": [{"path": "wiki/host.md"}]}}
            os.makedirs(os.path.join(d, "sb", "wiki"))
            sb = os.path.join(d, "sb")
            self.assertTrue(grade.resolve_link("real-page", d, sb, graph) is False)  # file is in fixture? No: resolver checks SANDBOX files
            open(os.path.join(sb, "wiki", "real-page.md"), "w").write("x")
            self.assertTrue(grade.resolve_link("real-page", d, sb, graph))
            self.assertTrue(grade.resolve_link("graph-page", d, sb, graph))
            self.assertTrue(grade.resolve_link("embedded-entity", d, sb, graph))
            self.assertFalse(grade.resolve_link("fabricated", d, sb, graph))

class TestMetrics(unittest.TestCase):
    def test_short_footer_denominator(self):
        m = grade.precision_recall_mrr(["a", "b", "c"], {"a", "b", "z"}, ["z"])
        self.assertAlmostEqual(m["p_at_5"], 2 / 3)      # min(5, 3) denominator
        self.assertAlmostEqual(m["r_at_5"], 2 / 3)      # 2 of 3 relevant found
        self.assertEqual(m["mrr"], 0.0)                  # primary 'z' never cited

    def test_mrr_first_primary(self):
        m = grade.precision_recall_mrr(["x", "p1", "p2"], {"p1"}, ["p1", "p2"])
        self.assertAlmostEqual(m["mrr"], 1 / 2)          # first primary at rank 2

class TestStreamJson(unittest.TestCase):
    def test_parse(self):
        lines = [
            {"type": "system", "subtype": "init"},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": "/sb/wiki/a.md"}}]}},
            {"type": "result", "subtype": "success", "result": "answer text",
             "usage": {"input_tokens": 10, "output_tokens": 20,
                       "cache_creation_input_tokens": 100,
                       "cache_read_input_tokens": 1000},
             "total_cost_usd": 0.05, "num_turns": 3},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write("\n".join(json.dumps(l) for l in lines)); p = f.name
        out = grade.parse_stream_json(p); os.unlink(p)
        self.assertEqual(out["result_text"], "answer text")
        self.assertEqual(out["reads"], ["/sb/wiki/a.md"])
        self.assertAlmostEqual(out["total_cost_usd"], 0.05)
        self.assertAlmostEqual(grade.weighted_tokens(out["usage"]),
                               10 + 1.25 * 100 + 0.1 * 1000 + 5 * 20)

class TestIngestChecks(unittest.TestCase):
    def test_url_extraction_and_lint_delta(self):
        s = "see https://eval-fixture.invalid/a. and (https://x.test/b),"
        self.assertEqual(grade.extract_urls(s),
                         {"https://eval-fixture.invalid/a", "https://x.test/b"})
        self.assertEqual(grade.lint_delta(["w1", "w2"], ["w1"]), ["w2"])

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure** — `cd evals && python3 -m unittest tests.test_grade -v` → FAIL (`No module named 'grade'`... use `python3 tests/test_grade.py`; expect ImportError/AttributeError).

- [ ] **Step 3: Implement the functions in `evals/grade.py`**

```python
#!/usr/bin/env python3
"""Deterministic grader for llm-wiki evals. Pure functions here; CLI at bottom (Task 4)."""
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
```

Note the resolver test's first assertion: a file present only in the *fixture* does NOT resolve — files are checked in the **sandbox** (what the agent actually cited against); only the graph is read from the fixture (spec finding 9).

- [ ] **Step 4: Run tests to verify pass** — `cd evals && python3 tests/test_grade.py -v` → all PASS.

- [ ] **Step 5: Commit** — `git add evals/grade.py evals/tests/test_grade.py && git commit -m "feat(evals): grade.py pure functions with unit tests"`

---

### Task 4: grade.py CLI — per-case grading

**Files:**
- Modify: `evals/grade.py` (append CLI)
- Test: extend `evals/tests/test_grade.py`

**Interfaces:**
- Consumes: Task 3 functions; `fixture-manifest.json` (Task 2); labels `ground-truth.json` shape defined here.
- Produces: CLI `python3 grade.py --case-id X --case-type query|twin|ingest|reader --sandbox DIR --fixture DIR --labels DIR --transcript FILE --out FILE [--pristine-raw FILE]`. Exit 0 pass / 1 fail / 2 config error. Writes `<out>` JSON: `{"case": ..., "pass": bool, "hard": {name: bool}, "soft": {...}, "metrics": {...}, "tokens": {...}}`. run.sh (Task 6) calls exactly this.
- **ground-truth.json shape (documented here, authored in Task 9):**

```json
{
  "fixture_hash": "<64-hex from fixture-manifest.json>",
  "query": {"q01": {"relevant": ["slug", "..."], "primary": ["slug"]}},
  "ingest": {"i01": {"digest_slug": "eval-fixture-tokens",
                      "backprop_targets": ["entity-slug", "..."]}},
  "reader": {"r01": {"snapshots": ["snapshot-file-stem", "..."],
                      "answers": {"Q1": "snapshot-file-stem", "Q2": "..."}}}
}
```

- [ ] **Step 1: Write failing CLI tests** (append to `evals/tests/test_grade.py`):

```python
class TestCLI(unittest.TestCase):
    def _fixture(self, d):
        fx = os.path.join(d, "fx"); os.makedirs(os.path.join(fx, "wiki"))
        open(os.path.join(fx, "wiki", "page-a.md"), "w").write("a")
        json.dump({"pages": {}, "entities": {}},
                  open(os.path.join(fx, "wiki", "_graph.json"), "w"))
        json.dump({"content_hash": "h" * 64, "lint_baseline": [], "lint_exit": 0},
                  open(os.path.join(fx, "fixture-manifest.json"), "w"))
        lb = os.path.join(d, "labels"); os.makedirs(lb)
        json.dump({"fixture_hash": "h" * 64,
                   "query": {"q01": {"relevant": ["page-a"], "primary": ["page-a"]}}},
                  open(os.path.join(lb, "ground-truth.json"), "w"))
        sb = os.path.join(d, "sb"); os.makedirs(os.path.join(sb, "wiki"))
        open(os.path.join(sb, "wiki", "page-a.md"), "w").write("a")
        return fx, lb, sb

    def test_query_pass_and_hash_refusal(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            fx, lb, sb = self._fixture(d)
            tr = os.path.join(d, "t.jsonl")
            with open(tr, "w") as f:
                f.write(json.dumps({"type": "result", "subtype": "success",
                    "result": "Answer.\nSOURCES (most relevant first): [[page-a]]",
                    "usage": {"input_tokens": 1}, "total_cost_usd": 0.01,
                    "num_turns": 1}))
            out = os.path.join(d, "g.json")
            base = [sys.executable, os.path.join(os.path.dirname(__file__), "..", "grade.py"),
                    "--case-id", "q01", "--case-type", "query", "--sandbox", sb,
                    "--fixture", fx, "--labels", lb, "--transcript", tr, "--out", out]
            r = subprocess.run(base, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            g = json.load(open(out))
            self.assertTrue(g["pass"]); self.assertEqual(g["metrics"]["mrr"], 1.0)
            # hash refusal
            json.dump({"fixture_hash": "x" * 64, "query": {}},
                      open(os.path.join(lb, "ground-truth.json"), "w"))
            r2 = subprocess.run(base, capture_output=True, text=True)
            self.assertEqual(r2.returncode, 2)
```

- [ ] **Step 2: Run to verify failure** — `python3 tests/test_grade.py TestCLI -v` → FAIL (no CLI yet).

- [ ] **Step 3: Append the CLI to `evals/grade.py`**

```python
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
        # Real check, not substring luck: the exact "## From [[<digest>]]" section
        # AND the digest in the frontmatter sources block (live pages have many
        # pre-existing From-sections from prior ingests).
        fm = ptext.split("---")[1] if ptext.count("---") >= 2 else ""
        hard[f"backprop:{t}"] = bool(dig) and f"## From [[{dig.stem}]]" in ptext \
                                and dig.stem in fm
    # MANIFEST: scope to the seeded file only — the real MANIFEST has 21
    # pre-existing "- [x]" lines and one pre-existing pending-ingest entry the
    # agent must NOT touch; a global check false-fails every run.
    fix_name = Path(pristine_raw).name
    man = Path(sandbox) / "raw" / "MANIFEST.md"
    man_lines = [l for l in (man.read_text().splitlines() if man.exists() else [])
                 if f"`{fix_name}`" in l]
    hard["manifest_flipped"] = bool(man_lines) and all(
        "- [x]" in l and "ingested" in l and "pending-ingest" not in l
        for l in man_lines)
    # Lint delta: same-day, same-env double run — lint a fresh COPY of the
    # pristine fixture (lint mutates its target: catalogs, _health.md, and
    # 90-day staleness output shift over time, so the frozen baseline in the
    # manifest is documentation, not the reference).
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
    # URLs (source_url/final_url) — the fixture holds 158 snapshots whose
    # crawled bodies are full of incidental URLs a fabricated citation could
    # collide with.
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
```

Twin ground-truth aliasing: a twin case id like `twin01-rep2` falls back to the labels of its paired query case (`q01`) — the mapping convention is `twinNN` ↔ `qNN`, and run.sh passes the twin's own id.

- [ ] **Step 4: Run all tests** — `python3 tests/test_grade.py -v` → all PASS (including TestCLI).

- [ ] **Step 5: Commit** — `git add evals/grade.py evals/tests/test_grade.py && git commit -m "feat(evals): grade.py CLI with per-case-type grading"`

---

### Task 5: Prompt templates

**Files:**
- Create: `evals/prompts/query.tmpl.md`, `evals/prompts/ingest.tmpl.md`, `evals/prompts/reader.tmpl.md`

**Interfaces:** run.sh (Task 6) substitutes `{{QUESTION}}`, `{{WIKI_ROOT}}`, `{{PLUGIN_ROOT}}`, `{{RAW_FILE}}`, `{{SNAPSHOT_PATHS}}`, `{{QUESTIONS_BLOCK}}` via sed. No other placeholders.

- [ ] **Step 1: Write `query.tmpl.md`** (twins reuse it verbatim — the mutation is in the sandbox, not the prompt):

```markdown
Read {{PLUGIN_ROOT}}/skills/query/SKILL.md and follow it to answer the question below.

The resolved wiki root is {{WIKI_ROOT}} — treat it as the target wiki; do not run wiki resolution against any other location.

This is a non-interactive evaluation run: never ask for confirmation; if the skill offers optional choices, decline them and continue to completion.

Question: {{QUESTION}}

After your prose answer (which should cite [[wikilinks]] per the skill), end your output with exactly one final line in this format, most relevant page first:

SOURCES (most relevant first): [[slug-1]], [[slug-2]], [[slug-3]]
```

- [ ] **Step 2: Write `ingest.tmpl.md`**:

```markdown
Read {{PLUGIN_ROOT}}/skills/wiki-ingest/SKILL.md and follow it in --auto mode with these arguments: --auto --wiki {{WIKI_ROOT}} {{RAW_FILE}}

This is a non-interactive evaluation run:
- Decline ALL optional offers — including the step-9 question-page extraction offer ("cluster them into question pages? (y/n)" → no) — and continue through every remaining step to completion (log entry, MANIFEST update, auto-lint).
- Where the skill says to invoke a slash command (e.g. /llm-wiki:graphify-wiki), run the equivalent python script directly instead: python3 {{WIKI_ROOT}}/scripts/graphify_wiki.py --wiki-root {{WIKI_ROOT}}
- Snapshot capture (step 5) will fail to fetch every URL — that is expected here (the URLs are fixture URLs); report the failures and continue. Do not treat 0 captures as an error.
```

- [ ] **Step 3: Write `reader.tmpl.md`**:

```markdown
Read {{PLUGIN_ROOT}}/agents/wiki-researcher.md and follow its role, output schema, and citation rules exactly as if you had been dispatched as that agent — with these overrides for this non-interactive evaluation run:

- Your source snapshots are these files (read them from disk; you have no web access):
{{SNAPSHOT_PATHS}}
- Answer the questions below from those snapshots only, citing each snapshot's original source_url from its YAML front-block.
- Structure your output with one section per question. Each section MUST end with a line of the form: `Q1 SOURCES: <url>, <url>` (matching the question's number).
- Emit the <wiki-output> envelope per the agent contract; the SOURCES lines go inside it.

Questions:
{{QUESTIONS_BLOCK}}
```

- [ ] **Step 4: Verify templates have no unsubstituted placeholder patterns beyond the six documented** — `grep -ho '{{[A-Z_]*}}' evals/prompts/*.md | sort -u` → exactly the six named above.

- [ ] **Step 5: Commit** — `git add evals/prompts && git commit -m "feat(evals): executor prompt templates"`

---

### Task 6: run.sh orchestrator + cheap smoke test

**Files:**
- Create: `evals/run.sh`

**Interfaces:**
- Consumes: `$EVAL_LABELS/cases.json` (shape below), templates (Task 5), `grade.py` CLI (Task 4).
- Produces: `.results/<UTC timestamp>/` containing per-run `<case>.transcript.jsonl`, `<case>.grade.json`, `summary.txt`. Exit 0 iff all hard checks pass.
- **cases.json shape (documented here, authored in Task 9):**

```json
{"cases": [
  {"id": "q01", "type": "query", "question": "..."},
  {"id": "twin01", "type": "twin", "question": "...", "reps": 3},
  {"id": "i01", "type": "ingest", "fixture": "eval-fixture-tokens.md",
   "manifest_desc": "Designed eval fixture"},
  {"id": "r01", "type": "reader", "snapshots": ["<stem>", "..."],
   "questions": ["Q1: ...", "Q2: ..."]}
]}
```

- [ ] **Step 1: Write `evals/run.sh`**

```bash
#!/usr/bin/env bash
# llm-wiki eval runner. Env: EVAL_WIKI (required), EVAL_LABELS, EVAL_RUNTIME=claude|gemini|codex,
# EVAL_MODEL, EVAL_MAX_TURNS, EVAL_OUT. Usage: run.sh [case-id|all]
set -eu
REPO="$(cd "$(dirname "$0")/.." && pwd)"
EVALS="$REPO/evals"
WANT="${1:-all}"
RUNTIME="${EVAL_RUNTIME:-claude}"
MAX_TURNS="${EVAL_MAX_TURNS:-60}"
[ -n "${EVAL_WIKI:-}" ] || { echo "EVAL_WIKI must point at a frozen fixture (see snapshot.sh)"; exit 2; }
FIXTURE="$EVAL_WIKI"
LABELS="${EVAL_LABELS:-$FIXTURE/../eval-labels}"
[ -f "$FIXTURE/fixture-manifest.json" ] || { echo "no fixture-manifest.json in $FIXTURE — run snapshot.sh first"; exit 2; }
[ -f "$LABELS/cases.json" ] || { echo "no cases.json in $LABELS"; exit 2; }

# Re-hash the pristine fixture once per suite run — the manifest hash alone
# only proves labels matched the fixture at snapshot time, not that the
# fixture is still those bytes today.
python3 - "$FIXTURE" <<'PYEOF' || exit 2
import hashlib, json, sys
from pathlib import Path
dest = Path(sys.argv[1])
h = hashlib.sha256()
for p in sorted(dest.rglob("*")):
    if p.is_file() and p.name != "fixture-manifest.json":
        h.update(str(p.relative_to(dest)).encode()); h.update(p.read_bytes())
m = json.loads((dest / "fixture-manifest.json").read_text())
if m["content_hash"] != h.hexdigest():
    sys.exit("REFUSED: fixture content changed since snapshot — re-run snapshot.sh and re-review labels")
PYEOF
case "$RUNTIME" in
  claude) MODEL="${EVAL_MODEL:-sonnet}"; command -v claude >/dev/null || { echo "claude CLI missing"; exit 2; } ;;
  gemini) MODEL="${EVAL_MODEL:-gemini-2.5-pro}"; command -v gemini >/dev/null || { echo "gemini CLI missing"; exit 2; } ;;
  codex)  MODEL="${EVAL_MODEL:-}"; command -v codex >/dev/null || { echo "codex CLI missing"; exit 2; } ;;
  *) echo "unknown EVAL_RUNTIME: $RUNTIME"; exit 2 ;;
esac
OUT="${EVAL_OUT:-$EVALS/.results/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"

run_agent() {  # $1 prompt file, $2 transcript out, $3 stderr out; cwd = sandbox wiki root
  case "$RUNTIME" in
    claude)
      claude -p "$(cat "$1")" --model "$MODEL" --permission-mode bypassPermissions \
        --max-turns "$MAX_TURNS" --output-format stream-json --verbose > "$2" 2> "$3" ;;
    gemini)
      GEMINI_CLI_TRUST_WORKSPACE=true gemini -m "$MODEL" --approval-mode yolo \
        -p "$(cat "$1")" > "$2" 2> "$3" ;;
    codex)
      if [ -n "$MODEL" ]; then
        codex exec -m "$MODEL" --sandbox workspace-write --skip-git-repo-check --json "$(cat "$1")" > "$2" 2> "$3"
      else
        codex exec --sandbox workspace-write --skip-git-repo-check --json "$(cat "$1")" > "$2" 2> "$3"
      fi ;;
  esac
}

build_sandbox() {  # $1 case type; echoes sandbox path
  local SB; SB="$(mktemp -d "${TMPDIR:-/tmp}/llmwiki-eval-XXXXXX")"
  rsync -a --exclude 'fixture-manifest.json' "$FIXTURE/" "$SB/wiki-root/"
  rsync -a --exclude '.git' --exclude 'evals/.results' "$REPO/plugin/" "$SB/plugin/"
  mkdir -p "$SB/plugin-data"
  [ "$1" = "twin" ] && rm -f "$SB/wiki-root/wiki/_graph.json"
  echo "$SB"
}

emit_prompt() {  # $1 template, $2 out — Python substitution, NOT sed: question
  # text containing & re-inserts the match silently, | breaks the expression,
  # newlines are a hard sed error. All realistic in English questions.
  TMPL="$1" OUT_P="$2" SB="$SB" Q_TEXT="${Q_TEXT:-}" RAW_DST="${RAW_DST:-}" python3 - <<'PYEOF'
import os
t = open(os.environ["TMPL"]).read()
sb = os.environ["SB"]
t = t.replace("{{WIKI_ROOT}}", sb + "/wiki-root").replace("{{PLUGIN_ROOT}}", sb + "/plugin")
t = t.replace("{{QUESTION}}", os.environ["Q_TEXT"]).replace("{{RAW_FILE}}", os.environ["RAW_DST"])
open(os.environ["OUT_P"], "w").write(t)
PYEOF
}

overall=0
CASES_PY="import json,sys; cs=json.load(open('$LABELS/cases.json'))['cases']"
for CASE in $(python3 -c "$CASES_PY
print('\n'.join(c['id'] for c in cs))"); do
  [ "$WANT" != "all" ] && [ "$WANT" != "$CASE" ] && continue
  TYPE="$(python3 -c "$CASES_PY
print([c for c in cs if c['id']=='$CASE'][0]['type'])")"
  # reps honored for ALL case types — the twin experiment needs ≥3 reps on BOTH
  # arms (q01–q03 are authored with reps: 3), not just the no-graph arm.
  REPS="$(python3 -c "$CASES_PY
print([c for c in cs if c['id']=='$CASE'][0].get('reps',1))")"

  rep=1
  while [ "$rep" -le "$REPS" ]; do
    RUN_ID="$CASE"; [ "$REPS" -gt 1 ] && RUN_ID="$CASE-rep$rep"
    echo "=== $RUN_ID ($TYPE, runtime: $RUNTIME/$MODEL) ==="
    SB="$(build_sandbox "$TYPE")"
    export CLAUDE_PLUGIN_ROOT="$SB/plugin" CLAUDE_PLUGIN_DATA="$SB/plugin-data"
    PROMPT="$OUT/$RUN_ID.prompt.md"; TRANS="$OUT/$RUN_ID.transcript.jsonl"
    PRISTINE_ARG=""

    case "$TYPE" in
      query|twin)
        Q_TEXT="$(python3 -c "$CASES_PY
print([c for c in cs if c['id']=='$CASE'][0]['question'])")"
        RAW_DST=""; emit_prompt "$EVALS/prompts/query.tmpl.md" "$PROMPT" ;;
      ingest)
        FIX_NAME="$(python3 -c "$CASES_PY
print([c for c in cs if c['id']=='$CASE'][0]['fixture'])")"
        DESC="$(python3 -c "$CASES_PY
print([c for c in cs if c['id']=='$CASE'][0].get('manifest_desc','Designed eval fixture'))")"
        RAW_DST="$SB/wiki-root/raw/$FIX_NAME"
        cp "$EVALS/fixtures/ingest/$FIX_NAME" "$RAW_DST"
        printf -- '- [ ] `%s` — %s — pending-ingest\n' "$FIX_NAME" "$DESC" >> "$SB/wiki-root/raw/MANIFEST.md"
        Q_TEXT=""; emit_prompt "$EVALS/prompts/ingest.tmpl.md" "$PROMPT"
        PRISTINE_ARG="--pristine-raw $EVALS/fixtures/ingest/$FIX_NAME" ;;
      reader)
        python3 - "$CASE" "$LABELS" "$SB" "$EVALS" "$PROMPT" <<'PYEOF'
import json, sys
from pathlib import Path
case_id, labels, sb, evals, prompt_out = sys.argv[1:6]
c = next(x for x in json.load(open(Path(labels)/"cases.json"))["cases"] if x["id"] == case_id)
snaps = "\n".join(f"  - {sb}/wiki-root/raw/snapshots/{s}.md" for s in c["snapshots"])
qs = "\n".join(c["questions"])
t = (Path(evals)/"prompts"/"reader.tmpl.md").read_text()
t = t.replace("{{PLUGIN_ROOT}}", f"{sb}/plugin").replace("{{SNAPSHOT_PATHS}}", snaps)
t = t.replace("{{QUESTIONS_BLOCK}}", qs)
Path(prompt_out).write_text(t)
PYEOF
        ;;
    esac

    ( cd "$SB/wiki-root" && run_agent "$PROMPT" "$TRANS" "$OUT/$RUN_ID.stderr.log" ) || true
    if [ "$TYPE" = "ingest" ]; then
      # Persist the judge's evidence before the pass-path deletes the sandbox:
      # digests + top-level entity pages (the backprop targets live there).
      mkdir -p "$OUT/$RUN_ID-artifacts"
      cp -R "$SB/wiki-root/wiki/digests" "$OUT/$RUN_ID-artifacts/" 2>/dev/null || true
      cp "$SB/wiki-root/wiki/"*.md "$OUT/$RUN_ID-artifacts/" 2>/dev/null || true
    fi
    if python3 "$EVALS/grade.py" --case-id "$RUN_ID" --case-type "$TYPE" \
        --sandbox "$SB/wiki-root" --fixture "$FIXTURE" --labels "$LABELS" \
        --transcript "$TRANS" --out "$OUT/$RUN_ID.grade.json" $PRISTINE_ARG; then
      rm -rf "$SB"
    else
      overall=1; echo "    sandbox kept: $SB"
    fi
    rep=$((rep+1))
  done
done

python3 - "$OUT" <<'PYEOF'
import json, sys
from pathlib import Path
out = Path(sys.argv[1]); rows = []
for g in sorted(out.glob("*.grade.json")):
    d = json.loads(g.read_text())
    m = d.get("metrics") or {}
    rows.append(f"{'PASS' if d['pass'] else 'FAIL':4} {d['case']:16} {d['type']:6} "
                f"P@5={m.get('p_at_5','-')} MRR={m.get('mrr','-')} "
                f"W={d['tokens']['weighted']:.0f} ${d['tokens']['cost_usd']:.3f}")
(out / "summary.txt").write_text("\n".join(rows) + "\n")
print("\n".join(rows))
PYEOF
exit $overall
```

- [ ] **Step 2: Cheap end-to-end smoke — mini-wiki, not the real snapshot.** Build a throwaway 3-page wiki, snapshot it, author 1 trivial query case, run at haiku:

```bash
chmod +x evals/run.sh
MW=/tmp/mini-wiki; rm -rf $MW; mkdir -p $MW/wiki $MW/scripts $MW/raw/snapshots
printf -- '---\ntype: synthesis\nsummary: "espresso: needs 9 bar pressure"\n---\n# Espresso\nNeeds 9 bar pressure.\n' > $MW/wiki/espresso-basics.md
printf -- '---\ntype: synthesis\nsummary: "grinders"\n---\n# Grinders\nBurr beats blade.\n' > $MW/wiki/grinder-guide.md
printf 'import sys; print("ok"); sys.exit(0)\n' > $MW/scripts/lint.py
printf '# index\n' > $MW/wiki/index.md
bash evals/snapshot.sh $MW /tmp/mini-fixture
mkdir -p /tmp/eval-labels
H=$(python3 -c "import json;print(json.load(open('/tmp/mini-fixture/fixture-manifest.json'))['content_hash'])")
cat > /tmp/eval-labels/cases.json <<EOF
{"cases": [{"id": "q01", "type": "query", "question": "What pressure does espresso need?"}]}
EOF
cat > /tmp/eval-labels/ground-truth.json <<EOF
{"fixture_hash": "$H", "query": {"q01": {"relevant": ["espresso-basics"], "primary": ["espresso-basics"]}}}
EOF
EVAL_WIKI=/tmp/mini-fixture EVAL_LABELS=/tmp/eval-labels EVAL_MODEL=haiku bash evals/run.sh q01
```

Expected: one PASS line with MRR=1.0 and a nonzero weighted-token count; `.results/<ts>/q01.grade.json` exists. Debug run.sh (not the design) until this passes. Note the mini-wiki has no `_graph.json` — the query skill's fallback path is exercised; that's fine for plumbing.

- [ ] **Step 3: Verify privacy guard held** — `git status --porcelain | grep -c 'results'` → 0.

- [ ] **Step 4: Commit** — `git add evals/run.sh && git commit -m "feat(evals): run.sh orchestrator, smoke-tested end-to-end at haiku"`

---

### Task 7: judge.py + rubric

**Files:**
- Create: `evals/judge.py`, `evals/judge-rubric.md`
- Reference (copy from, do not import): `~/Documents/GitHub/ai-content/ship-to-signal/evals/judge.py`

**Interfaces:**
- Consumes: a `.results/<ts>/` dir (transcripts + grades from Task 6), sandbox paths for kept failures, `$EVAL_WIKI`.
- Produces: CLI `python3 judge.py --results DIR --fixture DIR [--judge claude|gemini|ollama] [--model NAME] [--min-overall N]` → writes `<results>/judge.json`. Auto-flip: if `$EVAL_RUNTIME` (or `--executor`) is claude → judge gemini (`gemini-2.5-pro`); anything else → judge claude (`sonnet`). Informational: exit 0 always unless `--min-overall` set.

- [ ] **Step 1: Write `evals/judge-rubric.md`**

```markdown
# Judge rubric — llm-wiki evals

Score each dimension 1–5 (5 best). Return STRICT JSON only:
{"scores": {"groundedness": N, "completeness": N, "citation_discipline": N, "style_compliance": N}, "overall": N, "notes": "<2-3 sentences>"}

- **groundedness** — every claim in the output is supported by the supplied evidence (cited pages / digest sources / snapshots). Claims from outside the evidence = low score, however plausible.
- **completeness** — the output actually answers the question(s) asked, at the depth the evidence supports.
- **citation_discipline** — citations are specific (page-level / URL-level), attached to the claims they support, and nothing checkable is left uncited.
- **style_compliance** — (ingest only, else score 3) digest summary is scope-and-purpose, not a content dump; claims are 2-4 high-signal bullets with wikilink destinations.

Judge the output against the evidence, not against your own knowledge.
```

- [ ] **Step 2: Write `evals/judge.py`** — copy `call_judge()` (all three families incl. the Vertex fallback env dance) **verbatim** from `~/Documents/GitHub/ai-content/ship-to-signal/evals/judge.py`, then replace its `collect()` with per-case-type collectors and its `main()` with:

```python
#!/usr/bin/env python3
"""Cross-family judge for llm-wiki eval outputs. Informational — never gates
unless --min-overall. call_judge() is copied verbatim from ship-to-signal."""
import argparse, json, os, re, subprocess, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import grade as G

HERE = Path(__file__).resolve().parent
RUBRIC = (HERE / "judge-rubric.md").read_text()
PAGE_CAP = 6000  # chars per evidence page

# def call_judge(judge, model, prompt): <— PASTE VERBATIM from ship-to-signal judge.py

def collect_query(parsed, fixture, sandbox_wiki):
    answer = parsed["result_text"]
    graph = G.load_graph(fixture)
    parts = [f"===== ANSWER =====\n{answer[:PAGE_CAP]}"]
    for slug in G.parse_sources_footer(answer)[:6]:
        for root in (Path(sandbox_wiki or fixture), Path(fixture)):
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
        if gt["digest_slug"] in dig.stem:
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
```

The judge covers all four case types: run.sh persists ingest evidence (digests + entity pages) into `.results/<case>-artifacts/` before the pass-path deletes the sandbox, so "digest quality" — a v1 target — is actually judged, not skipped.

- [ ] **Step 3: Offline test of collectors** (no API call): reuse the Task 6 mini-fixture results dir (rebuild `/tmp/mini-fixture` via Task 6 Step 2's commands if it was cleaned):

```bash
cd evals && python3 - <<'EOF'
import json, sys
sys.path.insert(0, ".")
import judge, grade
p = judge.collect_reader({"result_text": "synth"}, "/tmp/mini-fixture")
assert "SYNTHESIS" in p
print("collectors OK")
EOF
```

- [ ] **Step 4: One live judge call** against the smoke run's results (`--judge gemini`, falls back per Vertex env; if gemini auth unavailable in this shell, run `--judge claude --model haiku` instead and note it): `python3 judge.py --results .results/<smoke-ts> --fixture /tmp/mini-fixture` → `judge.json` written with a numeric overall.

- [ ] **Step 5: Commit** — `git add evals/judge.py evals/judge-rubric.md && git commit -m "feat(evals): cross-family judge with per-case-type collectors"`

---

### Task 8: Designed ingest fixtures

**Files:**
- Create: `evals/fixtures/ingest/eval-fixture-tokens.md`, `evals/fixtures/ingest/eval-fixture-memory.md`

**Interfaces:** Task 9's labels reference these; their `backprop_targets` must be entity pages that exist in the real snapshot: `ai-cost-economics-uber-equation` + `token-budget-decision-heatmap`-hosting pages for fixture 1; `agent-memory-tool-landscape` for fixture 2 (verify against the snapshot in Task 9 and adjust labels, not fixtures).

- [ ] **Step 1: Write `eval-fixture-tokens.md`** — a synthetic research file in the wiki's research-output shape:

```markdown
# Research: token budgeting practices in AI product teams — 2026-08-08

## Findings

Teams that cap per-feature token spend before development report tighter cost
control than teams that meter after launch. A survey of 40 AI product teams
found pre-committed token budgets correlated with 30% lower cost overruns
([survey](https://eval-fixture.invalid/token-budget-survey-2026)).

Per-request token ceilings interact with model choice: routing simple requests
to smaller models cut blended cost 45% in one documented rollout
([case study](https://eval-fixture.invalid/model-routing-case-study)).

Budget owners differ: finance-owned budgets correlate with under-provisioning;
product-owned budgets with overspend. Split ownership performed best
([analysis](https://eval-fixture.invalid/budget-ownership-analysis)).

## Sources
- https://eval-fixture.invalid/token-budget-survey-2026 — survey, 40 teams, 2026
- https://eval-fixture.invalid/model-routing-case-study — rollout case study
- https://eval-fixture.invalid/budget-ownership-analysis — ownership analysis
```

- [ ] **Step 2: Write `eval-fixture-memory.md`** — same shape, topic overlapping the agent-memory entity page:

```markdown
# Research: agent memory retrieval cost patterns — 2026-08-08

## Findings

File-based agent memory with a light index answered benchmark queries at
roughly one-third the token cost of graph-traversal stores in a controlled
comparison ([benchmark](https://eval-fixture.invalid/memory-retrieval-benchmark)).

Retrieval granularity dominated the cost difference: line-range reads from an
index averaged 400 tokens per lookup vs 2,800 for whole-file loads
([methodology](https://eval-fixture.invalid/retrieval-granularity-study)).

## Sources
- https://eval-fixture.invalid/memory-retrieval-benchmark — controlled comparison, 2026
- https://eval-fixture.invalid/retrieval-granularity-study — granularity methodology
```

- [ ] **Step 3: Verify every URL uses the reserved TLD** — `grep -o 'https\?://[^ )]*' evals/fixtures/ingest/*.md | grep -vc 'eval-fixture.invalid'` → 0.

- [ ] **Step 4: Commit** — `git add evals/fixtures && git commit -m "feat(evals): designed ingest fixtures on reserved .invalid TLD"`

---

### Task 9: Real snapshot, cases, ground truth (PRIVATE) + README

**Files:**
- Create (PRIVATE, outside repo): `~/wiki-eval-fixtures/ai-content-wiki-<date>/` via snapshot.sh; `~/wiki-eval-fixtures/eval-labels/cases.json`, `.../ground-truth.json`
- Modify: `evals/README.md` (full run instructions)

**Interfaces:** Consumes every prior task. Produces the runnable private suite.

- [ ] **Step 1: Freeze the real fixture**

```bash
mkdir -p ~/wiki-eval-fixtures
bash evals/snapshot.sh ~/Documents/GitHub/ai-content/ai-content-wiki ~/wiki-eval-fixtures/ai-content-wiki-2026-08-08
```

- [ ] **Step 2: Author 10 query cases + labels from the snapshot.** Read the snapshot's `wiki/index.md`, `_graph.json` keys, and entity pages; draft questions spanning: 3 single-page lookups (one answerable only via a consolidated-page entity — tests the resolver), 3 cross-page comparisons, 2 evidence-chasing ("what's the evidence for X"), 2 gap questions ("what do we know about Y" where coverage is thin). For each: `relevant` = every page a correct answer could legitimately cite (be generous), `primary` = the 1–3 pages an expert would name first (be strict). Insert the fixture hash. Designate q01–q03 as the twin pairs: author **both** `q01`–`q03` and `twin01`–`twin03` with `reps: 3` (questions copied verbatim) — both arms of the twin experiment need ≥3 reps, and run.sh honors `reps` on every case type.

- [ ] **Step 3: Author ingest + reader labels.** For each ingest fixture, list `backprop_targets` = entity pages actually present in the snapshot whose topics the fixture overlaps (verify with `ls` + grep; adjust the target lists to reality). For reader: pick 4–6 snapshot files from `raw/snapshots/` whose content you can answer-key by reading them; write 3 questions with `answers` mapping `Qn` → snapshot stem.

- [ ] **Step 4: Blind-validate the labels** (per the session's standing instruction): dispatch an independent agent with the snapshot path + cases.json + ground-truth.json and the task "for each query, answer it yourself from the wiki, then judge whether the labeled relevant/primary sets are right — flag missing pages, wrong primaries, ambiguous questions." Fix labels per findings. Then flag the final labels for Pranay's **async** review (the spec's "reviewed once by Pranay" step — do not block on it; note it in the wrap-up report).

- [ ] **Step 5: Complete `evals/README.md`** — env contract table (EVAL_WIKI, EVAL_LABELS, EVAL_RUNTIME, EVAL_MODEL, EVAL_MAX_TURNS, EVAL_OUT), the three-command quickstart (snapshot → author labels → run), the privacy rules (verbatim from Task 1 stub), metric definitions (P@5 denominator, W formula), the twin protocol (Claude-only, ≥3 reps, mean±spread), and the judge's ingest limitation from Task 7.

- [ ] **Step 6: Commit README** — `git add evals/README.md && git commit -m "docs(evals): full run instructions"` (labels/fixture stay private — verify with `git status`).

---

### Task 10: Full suite run + results

- [ ] **Step 1: Deterministic tests first** — `python3 evals/tests/test_grade.py -v` AND the plugin's own suite `python3 -m unittest discover -s plugin/tests` → all PASS (free; the spec's "plugin tests run first" means the plugin's, not just the grader's).
- [ ] **Step 2: 3-case pilot at sonnet** — `EVAL_WIKI=... EVAL_LABELS=... bash evals/run.sh q01` (+ one ingest, + the reader). Inspect grades AND transcripts: are failures real agent failures or harness bugs? Fix harness bugs, rerun. Grade-check disagreements with intuition = suspect the ground truth first.
- [ ] **Step 3: Full run** — `bash evals/run.sh` (28 executor runs). Then `python3 evals/judge.py --results evals/.results/<ts> --fixture $EVAL_WIKI`.
- [ ] **Step 4: Twin analysis** — from the 3×3+3×3 twin/query rep grades, compute per-pair mean±spread of weighted tokens and cost; write `evals/.results/<ts>/twin-analysis.md` (private, gitignored) with the graph-vs-grep table.
- [ ] **Step 5: Blind-validate the run** (standing instruction): dispatch an independent agent with the results dir + spec to answer: do the grades follow the spec's rules? Any hard check that fired for a harness reason rather than an agent reason? Is the twin delta statistically honest as reported?
- [ ] **Step 6: Record outcomes** — baseline numbers into the wiki (session page + scratchpad entry in ai-content, per that repo's conventions), noting suite version (git SHA) + fixture hash. Commit any harness fixes.

## Self-Review (done at plan time)

- **Spec coverage:** privacy split (T1, T9), snapshot+baseline (T2), metrics incl. P@5 denominator + resolver-from-fixture (T3), hash refusal + delta lint + MANIFEST + no-invented-URLs (T4), footer + non-interactive + step-9 decline + python-not-slash + Qn SOURCES (T5), sandbox env exports + twin mutation + stream-json + MANIFEST seeding + pristine copy (T6), auto-flip judge + collectors + rubric (T7), .invalid fixtures (T8), labels process + blind validation (T9), reps + twin analysis + pilot-first (T10). Gap check: spec's "one arm reuses query runs" — implemented as q01–q03 authored with `reps: 3`, serving as the with-graph arm entirely (9+7 query runs + 9 twin + 2 ingest + 1 reader = 28, matching the spec's arithmetic). ✓
- **Placeholders:** none — every code block is complete; judge.py's one paste-from-source is named with exact path and function.
- **Type consistency:** `grade.py` function names/signatures match between T3 tests, T3 impl, T4 CLI, and T7's `import grade as G` usage; cases.json/ground-truth.json shapes match between T4 (reader), T6 (run.sh), T9 (authoring). `twinNN`↔`qNN` aliasing defined T4, used T9. ✓
