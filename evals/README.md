# llm-wiki evals

Model-in-the-loop eval suite for the llm-wiki plugin. Deterministic grading against hand-labeled ground truth wherever possible; an informational cross-family LLM judge for prose quality. Design: `docs/superpowers/specs/2026-08-08-llm-wiki-evals-design.md` · Plan: `docs/superpowers/plans/2026-08-08-llm-wiki-evals.md`.

**Privacy (load-bearing):** the fixture wiki and the labels (`cases.json`, `ground-truth.json`) are PRIVATE — they live at `$EVAL_WIKI` / `$EVAL_LABELS`, never in this repo. `evals/.results/` is gitignored: transcripts embed wiki text verbatim. Do not weaken either guard. In-repo prompts are templates; question text is interpolated at runtime.

## Quickstart

```bash
# 1. Freeze a fixture from your live wiki (lint runs first, then the content hash)
bash evals/snapshot.sh ~/path/to/your-wiki ~/wiki-eval-fixtures/your-wiki-YYYY-MM-DD

# 2. Author labels next to it (see shapes below), recording the manifest's content_hash
#    → ~/wiki-eval-fixtures/eval-labels/{cases.json, ground-truth.json}

# 3. Run
EVAL_WIKI=~/wiki-eval-fixtures/your-wiki-YYYY-MM-DD bash evals/run.sh          # full suite
EVAL_WIKI=... bash evals/run.sh q01                                            # one case
EVAL_WIKI=... EVAL_MODEL=haiku bash evals/run.sh q01                           # cheap smoke

# 4. Judge (informational, cross-family: claude executor → gemini judge)
python3 evals/judge.py --results evals/.results/<ts> --fixture $EVAL_WIKI --labels $EVAL_LABELS
```

Deterministic tests (free, run first): `python3 evals/tests/test_grade.py` and `python3 -m unittest discover -s plugin/tests`.

## Env contract

| Var | Default | Meaning |
|---|---|---|
| `EVAL_WIKI` | (required) | Path to a frozen fixture made by `snapshot.sh`. Re-hashed at the start of every run; refuses on drift. |
| `EVAL_LABELS` | `$EVAL_WIKI/../eval-labels` | Dir holding `cases.json` + `ground-truth.json`. |
| `EVAL_RUNTIME` | `claude` | Executor: `claude` \| `gemini` \| `codex`. Token metrics are claude-only. |
| `EVAL_MODEL` | `sonnet` / `gemini-2.5-pro` / — | Executor model. |
| `EVAL_MAX_TURNS` | `60` | claude executor turn cap. |
| `EVAL_OUT` | `evals/.results/<utc-ts>` | Results dir: per-run prompt, stream-json transcript, grade, `summary.txt`. |

Per-case sandbox: fixture + plugin copies, `CLAUDE_PLUGIN_ROOT=<sandbox>/plugin`, `CLAUDE_PLUGIN_DATA=<sandbox>/plugin-data` (empty registry — writes can never route to your real wiki). Failed cases keep their sandbox for inspection.

## Case types & metrics

- **query** — agent follows the query skill; grades P@5 / R@5 (labeled `relevant` set) and MRR (labeled `primary`) over the answer's required `SOURCES (most relevant first):` footer. Hard: answer exists, footer present, every cited wikilink resolves (sandbox file, or `_graph.json` `pages`/`entities` key from the *pristine fixture* — consolidated-page entities are legitimate citations). P@5 denominator is `min(5, |footer|)`.
- **twin** — same question, sandbox minus `_graph.json` (the skill's grep-fallback path). Measures the graph index's token value: weighted tokens `W = input + 1.25·cache_creation + 0.1·cache_read + 5·output` (sonnet ratios) + `total_cost_usd`, ≥3 reps per arm, mean±spread. Claude runtime only.
- **ingest** — agent follows wiki-ingest `--auto` on a designed fixture raw file (URLs on the reserved `.invalid` TLD; snapshot capture legitimately gets 0/N). Hard: new digest exists (new-file-vs-fixture detection), no invented URLs (⊆ pristine fixture file's URLs), back-prop landed (`## From [[<digest>]]` + frontmatter sources on labeled targets), MANIFEST flipped for the seeded file only, lint delta-clean vs a same-day ref lint of the pristine fixture (volatile char counts normalized).
- **reader** — the research pipeline's read stage isolated: frozen snapshots in, synthesis out, per-question `Qn SOURCES:` lines. Hard: every cited URL ∈ the labeled snapshots' front-block URLs; each question cites its labeled snapshot.

Executor-level failures (rate limits, crashes) hard-fail as `executor_ok` with the error text in `soft.executor_error` — they never masquerade as agent answers.

## Label shapes

```json
// cases.json
{"cases": [
  {"id": "q01", "type": "query", "question": "...", "reps": 3},
  {"id": "twin01", "type": "twin", "question": "<same as q01>", "reps": 3},
  {"id": "i01", "type": "ingest", "fixture": "eval-fixture-tokens.md", "manifest_desc": "..."},
  {"id": "r01", "type": "reader", "snapshots": ["<md-stem>"], "questions": ["Q1: ..."]}
]}
// ground-truth.json
{"fixture_hash": "<from fixture-manifest.json>",
 "query": {"q01": {"relevant": ["slug"], "primary": ["slug"]}},
 "ingest": {"i01": {"digest_slug": "<short topic substring>", "backprop_targets": ["entity-slug"]}},
 "reader": {"r01": {"snapshots": ["<md-stem>"], "answers": {"Q1": "<md-stem>"}}}}
```

Authoring rules learned the hard way: twin ids pair as `twinNN` ↔ `qNN` (labels alias automatically, both need `reps`); `digest_slug` must be a short topic word guaranteed in any plausible digest filename (`token`, `memory`) — never the fixture filename; reader stems must be `.md` snapshots *with YAML front-blocks*, and the cases.json `snapshots` list must equal the ground-truth `snapshots` list; case ids stay apostrophe- and space-free.

## Judge

`judge.py` auto-flips family against the executor (claude executor → gemini judge, else claude); `--judge`/`--model` override. Rubric: groundedness, completeness, citation discipline, style compliance (`judge-rubric.md`). Evidence is collected per case type (cited pages' text; ingest digests + entity pages from `.results/<case>-artifacts/`; labeled snapshots). Scores are informational and never gate; `--min-overall N` makes them gate. Ollama judging is wired (`--judge ollama`) for local experiments; prior testing found local 8B judges unreliable on dimension scoring.
