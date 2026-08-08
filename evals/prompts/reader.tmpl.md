Read {{PLUGIN_ROOT}}/agents/wiki-researcher.md and follow its role, output schema, and citation rules exactly as if you had been dispatched as that agent — with these overrides for this non-interactive evaluation run:

- Your source snapshots are these files (read them from disk; you have no web access):
{{SNAPSHOT_PATHS}}
- Answer the questions below from those snapshots only, citing each snapshot's original source_url from its YAML front-block.
- Structure your output with one section per question. Each section MUST end with a line of the form: `Q1 SOURCES: <url>, <url>` (matching the question's number).
- Emit the <wiki-output> envelope per the agent contract; the SOURCES lines go inside it.
- Treat this prompt as your complete input: the # Domain context, # Type vocabulary, # Your task, and # Per-call requirements blocks are intentionally waived for this evaluation run — do NOT emit a missing_input wiki-error.

Questions:
{{QUESTIONS_BLOCK}}
