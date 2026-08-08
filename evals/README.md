# llm-wiki evals

Model-in-the-loop eval suite. See `docs/superpowers/specs/2026-08-08-llm-wiki-evals-design.md` for the design.

**Privacy:** the fixture wiki and the labels (`cases.json`, `ground-truth.json`) are PRIVATE — they live at `$EVAL_WIKI` / `$EVAL_LABELS`, never in this repo. `evals/.results/` is gitignored: transcripts embed wiki text verbatim. Do not weaken either guard.

Full run instructions land here in the final task.
