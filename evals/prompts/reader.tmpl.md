Read {{PLUGIN_ROOT}}/agents/wiki-researcher.md and follow its role, output schema, and citation rules exactly as if you had been dispatched as that agent — with these overrides for this non-interactive evaluation run:

- Your source snapshots are these files (read them from disk; you have no web access):
{{SNAPSHOT_PATHS}}
- Answer the questions below from those snapshots only, citing each snapshot's original source_url from its YAML front-block.
- Emit the <wiki-output> envelope per the agent contract.
- Treat this prompt as your complete input: the # Domain context, # Type vocabulary, # Your task, and # Per-call requirements blocks are intentionally waived for this evaluation run — do NOT emit a missing_input wiki-error.

Questions:
{{QUESTIONS_BLOCK}}

MANDATORY OUTPUT CONTRACT — this overrides the agent schema's own source-listing format and is machine-parsed; a missing line fails the run:
Structure the body as one section per question. The LAST line of each question's section must be exactly:
Qn SOURCES: <url>[, <url>...]
(where n is the question number and each <url> is the cited snapshot's front-block source_url — e.g. `Q1 SOURCES: https://example.org/paper`). Plain text, no backticks around the line itself.
