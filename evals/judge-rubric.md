# Judge rubric — llm-wiki evals

Score each dimension 1–5 (5 best). Return STRICT JSON only:
{"scores": {"groundedness": N, "completeness": N, "citation_discipline": N, "style_compliance": N}, "overall": N, "notes": "<2-3 sentences>"}

- **groundedness** — every claim in the output is supported by the supplied evidence (cited pages / digest sources / snapshots). Claims from outside the evidence = low score, however plausible.
- **completeness** — the output actually answers the question(s) asked, at the depth the evidence supports.
- **citation_discipline** — citations are specific (page-level / URL-level), attached to the claims they support, and nothing checkable is left uncited.
- **style_compliance** — (ingest only, else score 3) digest summary is scope-and-purpose, not a content dump; claims are 2-4 high-signal bullets with wikilink destinations.

Judge the output against the evidence, not against your own knowledge.
