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
    if p.is_file() and p.name != "fixture-manifest.json" \
            and p.name != ".DS_Store" and ".obsidian" not in p.parts:
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
OUT="$(cd "$OUT" && pwd)"  # absolutize: run_agent cds into the sandbox, relative EVAL_OUT would miss

run_agent() {  # $1 prompt file, $2 transcript out, $3 stderr out; cwd = sandbox wiki root
  case "$RUNTIME" in
    claude)
      claude -p "$(cat "$1")" --model "$MODEL" --permission-mode bypassPermissions \
        --max-turns "$MAX_TURNS" --output-format stream-json --verbose < /dev/null > "$2" 2> "$3" ;;
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
  rsync -a --exclude '.git' "$REPO/plugin/" "$SB/plugin/"
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
      cp "$SB/wiki-root/raw/MANIFEST.md" "$OUT/$RUN_ID-artifacts/" 2>/dev/null || true
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
