---
name: analyze
description: Analyze a local document or wiki page — themes, gaps, risks, implications. No web access. Routes small docs (<5K tokens) to Haiku automatically for cost savings. Use when the user says "analyze this file", "read X and tell me the risks", "what's missing in [[page]]", "review this doc", "what are the implications of X", or "summarize this raw file". For web research use the research skill; for wiki questions use the query skill.
---

# analyze skill

## Default posture

Before analyzing a file, check if the wiki already has an entity page for the subject. If `[[entity-slug]]` exists with `confidence: high`, analysis may add less value than a query.

## Preflight

```bash
[ -d "${CLAUDE_PLUGIN_ROOT}/scripts" ] || { echo "llm-wiki plugin scripts not found (is the plugin installed and loaded?)"; exit 1; }
```

## Flow

1. Resolve target wiki (same as research skill).

2. Verify target doc exists. User may provide:
   - A local file path (e.g. `raw/foo.pdf`, `~/Desktop/spec.md`)
   - A wiki page wikilink (e.g. `[[shopify-competitor]]`) → resolve to `<wiki>/wiki/shopify-competitor.md`

3. Build agent prompt:
   ```bash
   prompt=$("${CLAUDE_PLUGIN_ROOT}/scripts/build_agent_prompt.py" \
       --agent analyst --wiki "$wiki_path" --target "$target_path")
   ```

4. Token-count routing — select the right analyst agent before dispatch:
   ```bash
   # Token-count routing: small docs use Haiku for cost efficiency
   file_tokens=$(( $(wc -c < "$target_file") / 4 ))
   if [ "$file_tokens" -lt 5000 ]; then
       agent_type="llm-wiki:wiki-analyst-haiku"
       echo "Small document (~${file_tokens} tokens) — using Haiku fast-path."
   else
       agent_type="llm-wiki:wiki-analyst"
   fi
   ```

5. Dispatch the selected agent via Agent tool with `subagent_type: $agent_type`. Pass the prompt + target document contents in the user message. Do NOT fall back to general-purpose (see FC-13).

6. Validate output (`--agent analyst`). Handle 0/1/2 branches same as research skill.

7. **Offer to file the analysis — filing always goes through ingestion so it
   compounds, exactly like a research output.** Ask the user which:

   - **File into the wiki (compounds).** Write the analysis findings to
     `<wiki>/raw/analysis-<slug>-<today>.md` with the Write tool (include a
     `## Sources` section if the analysis cited anything). Append a MANIFEST
     entry, then invoke `/llm-wiki:wiki-ingest` (via the Skill tool, full name —
     NOT `llm-wiki:ingest`) with
     `--auto --wiki "$wiki_path" "$wiki_path/raw/analysis-<slug>-<today>.md"`.
     Ingestion writes the digest, appends the catalog, **back-propagates to the
     related entity pages**, and logs it — the same compounding path a research
     output takes.
     ```bash
     echo "- [ ] \`analysis-${slug}-${today}.md\` — Analysis output • public • pending-ingest" >> "$wiki_path/raw/MANIFEST.md"
     ```
     **Do NOT hand-write a bare `wiki/digests/analysis-*.md` yourself** — that
     orphaned the analysis (no catalog entry, no entity enrichment, no log).
     Ingestion is the single filing path so analyze and research compound
     identically.
   - **Append to the target page's Open Questions** (only when the target is a
     wiki page) — a lighter action for when you just want the open questions
     surfaced on that one page, not a filed digest.
   - **Both** — file into the wiki and append open questions to the target page.
   - **Save to scratch** — print the analysis, file nothing (the ephemeral case).

## Error handling

- Missing target: "Target `<path>` not found. Check the path."
- FC-4, FC-5, FC-6, FC-13: same handling as research skill.
