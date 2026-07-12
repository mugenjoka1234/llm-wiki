---
name: analyze
description: Analyze a local document or wiki page — themes, gaps, risks, implications. No web access. Routes small docs (<5K tokens) to Haiku automatically for cost savings. Use when the user says "analyze this file", "read X and tell me the risks", "what's missing in [[page]]", "review this doc", "what are the implications of X", or "summarize this raw file". For web research use the research skill; for wiki questions use the query skill.
---

# analyze skill

## Default posture

Before analyzing a file, check if the wiki already has an entity page for the subject. If `[[entity-slug]]` exists with `confidence: high`, analysis may add less value than a query.

## Preflight

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded via --plugin-dir or installed in a marketplace?}"
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

7. Offer to the user:
   - File as a new digest: `<wiki>/wiki/digests/analysis-<slug>-<date>.md`
   - Append findings to the target page's Open Questions (if target is a wiki page)
   - Both
   - Save to scratch (print raw, don't file)

## Error handling

- Missing target: "Target `<path>` not found. Check the path."
- FC-4, FC-5, FC-6, FC-13: same handling as research skill.
