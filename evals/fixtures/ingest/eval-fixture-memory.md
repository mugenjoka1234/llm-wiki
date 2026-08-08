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
