# llm-wiki eval suite — design

**Date:** 2026-08-08 · **Status:** approved (expert-reviewed, 14 findings incorporated)
**Pattern source:** ship-to-signal `evals/` harness (`ai-content/ship-to-signal/evals/`)
**Targets (v1):** query/retrieval quality · ingest fidelity · token efficiency · research-reader answering · digest quality

## What this is

Model-in-the-loop evals for the llm-wiki plugin, graded deterministically wherever ground truth permits, with an informational cross-family LLM judge for prose quality. The plugin's existing unit tests cover scripts; this suite covers *agent behavior when following the skills*.

## Architecture

```
evals/
  README.md            # run instructions, env contract, privacy rules
  run.sh               # orchestrator: sandbox → executor → grade → judge
  grade.py             # deterministic grader + retrieval metrics
  judge.py             # cross-family judge (adapted from ship-to-signal)
  judge-rubric.md      # quality dimensions per case type
  prompts/             # per-case executor prompt templates
  fixtures/ingest/     # 2 designed raw research files (synthetic, public-safe)
  snapshot.sh          # freezes a live wiki → private fixture dir
  .results/            # gitignored — transcripts contain private wiki text
```

**Public/private split (privacy is load-bearing):**
- In-repo: harness code, prompts *templates*, the 2 synthetic ingest fixtures, README, rubric.
- Private, at `$EVAL_WIKI/../eval-labels/`: `cases.json` (question text) and `ground-truth.json` (labeled pages). Questions and labels name private-wiki slugs — they never enter the public repo.
- `evals/.results/` is gitignored **before the first run** (transcripts embed wiki page text verbatim).

**Fixture:** `snapshot.sh` copies the live wiki (default: ai-content-wiki), strips `.git`, writes `fixture-manifest.json` (date, source path, content hash). `ground-truth.json` records that hash; `grade.py` **refuses to run** on hash mismatch — stale labels must fail loudly, not silently. The hash target is the pristine `$EVAL_WIKI` fixture, checked once per suite run — never the sandboxes, which are mutated by design.

## Sandbox contract (per case)

`run.sh` builds a temp sandbox and exports, unconditionally:

1. `rsync` fixture → `<sandbox>/wiki-root/`
2. `rsync` the plugin → `<sandbox>/plugin/`; export `CLAUDE_PLUGIN_ROOT=<sandbox>/plugin` — both SKILL.mds preflight on it and abort headless without it (review finding 1).
3. Export `CLAUDE_PLUGIN_DATA=<sandbox>/plugin-data` (empty registry) — otherwise `resolve_wiki.py`'s fallback to `~/.claude/plugins/data/.../registry.txt` can route writes to the user's **real** wiki under bypassPermissions (finding 8).
4. Per-type mutation (below), then run executor with cwd = sandbox.

Failed cases keep their sandbox for inspection. Env: `EVAL_RUNTIME=claude|gemini|codex`, `EVAL_MODEL`, `EVAL_WIKI` (required; exit 2 with message if unset), `EVAL_LABELS` (default `$EVAL_WIKI/../eval-labels`), `EVAL_OUT`.

Executor invocation (claude): `claude -p <prompt> --permission-mode bypassPermissions --output-format stream-json --verbose` — **stream-json, not json**: the aggregate json format has no tool-call records, and the file-read diagnostic needs `tool_use` blocks (finding 4).

## Case types

### query-* (×10)
Prompt: "Read `<CLAUDE_PLUGIN_ROOT>/skills/query/SKILL.md` and follow it for this question. Wiki root: `<sandbox>/wiki-root`. Non-interactive run: decline any offers and continue to completion. End your answer with exactly one line: `SOURCES (most relevant first): [[slug]], [[slug]], ...`"

The SOURCES footer exists because the skill's natural output is an unordered citation set in prose — no ranked list to score (finding 3). Metrics are computed **over the footer**; in-prose citations feed only the hard checks.

Grading:
- **P@5 / R@5** vs the labeled relevant set; **MRR** vs the 1–3 labeled must-hit pages — over the SOURCES footer (primary, runtime-portable). P@5 denominator when the footer is short: precision over the first min(5, |footer|) entries — a dense 3-source answer is not penalized for citing 3.
- Diagnostic only (claude runtime): same metrics over files actually Read, parsed from stream-json `tool_use` blocks.
- Hard: answer non-empty; SOURCES footer present and parseable; every cited wikilink **resolves** — where resolve = matches a file under the sandbox wiki, OR a `_graph.json` `pages` key, OR a `_graph.json` `entities` key, after stripping `[[slug|alias]]` and `[[page#section]]` syntax; `raw/...` links resolve against the sandbox tree (finding 9 — consolidated-page entity sections and snapshot links are legitimate citations, not fabrications). The resolver always reads `_graph.json` from the pristine `$EVAL_WIKI` fixture, never the sandbox — twin sandboxes have it deleted by design, and grading must not lose the entities/pages lookup in the no-graph arm.
- Soft: page-read count ≤ the skill's 15-page cap.

### twin-* (×3 question-pairs, ≥3 reps each, claude runtime only)
Same 3 questions as their query-* twins, sandbox mutation: **delete `wiki/_graph.json`** → the skill falls back to grep + full-file reads. Measures the graph index's token value with content held constant.

- Token metric defined (finding 5): report **both** `total_cost_usd` and weighted tokens `W = input + 1.25·cache_creation + 0.1·cache_read + 5·output` (sonnet price ratios). Never a bare "total tokens" — cache reads dominate the raw counts at ~10× lower cost.
- **≥3 reps per arm**, report mean ± spread; single paired runs of a nondeterministic agent are noise.
- Claude-only and stated as such: gemini/codex headless output carries no usage JSON.
- Judge scores both arms' answers — quality should hold when the graph is removed; a quality *drop* in the no-graph arm is itself a finding.

### ingest-* (×2)
Fixture raw files are synthetic (public-safe) and their `## Sources` URLs use `https://eval-fixture.invalid/...` — `capture_snapshots.py` live-fetches every URL and rewrites the raw file, so real URLs mean network flake and fake-but-resolving domains mean nondeterminism (finding 7). Grade tolerates "Captured 0/N".

Sandbox mutation: copy the fixture raw file into `wiki-root/raw/` **and append the exact-format MANIFEST line** `- [ ] \`<file>\` — <desc> — pending-ingest` (the skill's flip is a sed on that exact shape — finding 14). Keep a pristine copy of the raw file outside the sandbox for grading.

Prompt: follow wiki-ingest SKILL.md with `--auto --wiki <sandbox>/wiki-root <raw-file>`, plus: "Non-interactive run: decline all optional offers (including question-page extraction) and continue through every remaining step; where the skill says to invoke a slash command, run the equivalent python script directly."
That clause exists because `--auto` does **not** skip step 9's y/n prompt, which sits before the MANIFEST flip — a compliant agent would hang/terminate and false-fail the case (finding 6). *Filed as a real skill bug: step 9 should be skipped in `--auto`.*

Hard checks (all deterministic):
- digest file exists under `wiki/digests/` and lint is **delta-clean**: `snapshot.sh` records the pristine fixture's lint output in `fixture-manifest.json` (the live wiki lints at exit 1 today — 7 pre-existing oversize-page warnings that would otherwise fail every ingest run for pages the agent never touched); grading hard-fails only on *new* warnings vs that baseline, or any exit 2. This matches the skill's own contract, which tolerates exit 1 and halts only on exit 2.
- **no invented URLs:** set of URLs in the digest ⊆ set of URLs in the *pristine pre-mutation* fixture copy (the ingest mutates the sandbox copy)
- back-propagation landed: each labeled target entity page gained a `## From [[<digest-slug>]]` section and the digest in its `sources:`
- MANIFEST line flipped to `- [x] ... ingested <date> → wiki/digests/<slug>.md`

Dropped from earlier draft: "catalog line appended" — `lint.py` regenerates the catalog wholesale, so the check is vacuous (finding 11). Digest frontmatter schema is asserted instead.

### reader-* (×1)
No SKILL.md exists for the read stage (finding 13) — the executor prompt **inlines the wiki-researcher agent contract** (from `plugin/agents/wiki-researcher.md`) verbatim, plus paths to a frozen subset of `raw/snapshots/` from the fixture. The prompt requires the output be segmented per question, each section ending with a `Qn SOURCES: <url>, ...` line — without that, per-question grading isn't deterministic. Hard: every cited URL ∈ the snapshots' `source_url` front-blocks; each labeled question's `Qn SOURCES` line cites the snapshot that contains it. Judge: synthesis quality.

## Judge

Adapted from ship-to-signal `judge.py` (claude|gemini|ollama call plumbing and Vertex fallback carry over unchanged). Two changes:

1. **Auto-flip family** (finding 12): executor claude → judge gemini (`gemini-2.5-pro`); executor gemini → judge claude. `--judge` overrides.
2. **Per-case-type collectors** replace ship-to-signal's fixed-filename `collect()` (finding 10) — the judge must see the evidence, not just the output:
   - query/twin: the answer + full text of its cited pages (char-capped per page)
   - ingest: the digest + diffs of the touched entity pages
   - reader: the synthesis + cited snapshot excerpts

Dimensions (judge-rubric.md): groundedness (no claims beyond supplied evidence), completeness vs the question, citation discipline, digest summary-style compliance (scope-and-purpose, not content dump). Scores are informational and never gate; `--min-overall` exists for opt-in gating — ship-to-signal semantics exactly.

## Ground-truth process

Labels drafted from the frozen snapshot by the harness author, reviewed once by Pranay, then frozen against the fixture-manifest hash. Re-snapshot ⇒ re-review the label diff. Lives with the fixture (private), never in the repo.

## Cost & runtime

10 query + 15 additional twin runs (3 pairs × 2 arms × 3 reps = 18, minus 3 with-graph reps reused from the matching query cases) + 2 ingest + 1 reader = 28 executor runs at sonnet, each a light single-skill session. Estimate: under $10 and ~45–60 min a full run; judge rides existing Vertex/Gemini auth. Deterministic plugin tests run first — free, catches harness regressions without spending a token.

## Out of scope (v1)

Adversarial PII/citation gating cases (user deselected); scoring the research *plan/fetch* stages (live web, nondeterministic); CI wiring; scrubbed public fixture.
