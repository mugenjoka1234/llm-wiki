---
name: synthesize
description: Cross-page synthesis — combine claims across multiple wiki pages, identify contradictions, produce a new synthesis digest. NEVER modifies existing pages (use overview-refresh to rewrite existing pages). Use when the user says "synthesize findings on Y", "pull together everything on X", "make a summary page for all competitors", "combine what we know about Z", or "thorough synthesis of X" (thorough/exhaustive → --deep for opus). Does NOT answer one-off questions — use query for that. Pass `--update` to rewrite an existing type-summary page in place (e.g. 'update the competitors summary' → --update --type competitor). Shows diff and requires confirmation before writing.
---

# synthesize skill

## Default posture

Before synthesizing, check `wiki/digests/catalog.md` to see which digests already cover this topic. Synthesis should build on existing digests, not re-derive what they already established.

## Preflight

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded via --plugin-dir or installed in a marketplace?}"
```

## Flow

1. Resolve target wiki.

2. Gather candidate pages based on user query or type filter:
   - "what do we know about pricing" → `grep -l "pricing" $wiki_path/wiki/*.md`
   - "synthesize competitors" → all pages with `type: competitor`
   - User may narrow further ("just the active ones", "focus on Q2 experiments")

2b. If `--update` flag is present:
    a. Compute target filename using type pluralization:
       - `competitor` → `competitors-summary.md`
       - `feature` → `features-summary.md`
       - `tool` → `tools-summary.md`
       - `use-case` → `use-cases-summary.md`
       - For any other type: append `s` + `-summary.md` (e.g. `vendor` → `vendors-summary.md`)
    b. Check if `wiki/<type>s-summary.md` exists:
       - EXISTS → load current file content; set `mode = "in-place rewrite"`
       - NOT FOUND → set `mode = "create new"` (no confirmation needed)
    c. Proceed with synthesis (dispatch `wiki-synthesizer` agent as normal — steps 3–6 below)
    d. After synthesis output is received (step 6):
       - `mode = "in-place rewrite"`: show a diff between current content and proposed content,
         then ask: `"Overwrite wiki/<type>s-summary.md? (yes/no)"`
         - `yes` → write in place (use `wiki/<type>s-summary.md` as output path, skip digests/)
         - `no` → print "Discarded. No files changed." and STOP
       - `mode = "create new"` → write directly to `wiki/<type>s-summary.md` (no confirmation)

3. **Model escape hatch:** count the candidate pages.
   - If count > 20 OR user passed `--deep`: include a note in the user message to the agent: "Use opus-level reasoning for this synthesis (large corpus / user requested --deep)."
   - Otherwise: use the agent's default (sonnet).

4. Build agent prompt:
   ```bash
   pages_list=$(echo "$page_paths" | tr '\n' ',' | sed 's/,$//')
   prompt=$("${CLAUDE_PLUGIN_ROOT}/scripts/build_agent_prompt.py" \
       --agent synthesizer --wiki "$wiki_path" --pages "$pages_list")
   ```

5. Dispatch `wiki-synthesizer` via Agent tool with `subagent_type: llm-wiki:wiki-synthesizer`. For the opus override, pass the note in the user message alongside the prompt. Do NOT fall back to general-purpose.

6. Validate output (`--agent synthesizer`). Requires `[[wikilink]]` citations (exit 1 if none).

7. Save output — path depends on mode:

   **Default (no `--update`):** save as new digest:
   ```bash
   slug=$(echo "$topic" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-' | sed 's/^-//;s/-$//;s/--*/-/g')
   today=$(date +%Y-%m-%d)
   out="$wiki_path/wiki/digests/synthesis-${slug}-${today}.md"
   # Extract envelope content + prepend digest frontmatter, write to $out
   ```
   Wrap the extracted content with digest frontmatter (`type: source`, `sources: []`, `related:` pointing to synthesized pages) before writing.

   **`--update` mode:** write to `wiki/<type>s-summary.md` directly. Use this frontmatter schema:
   ```yaml
   ---
   type: synthesis
   status: active
   as-of: YYYY-MM-DD
   last-updated: YYYY-MM-DD
   sources: []
   related: []
   tags: [<type>, summary]
   ---
   ```
   - Do NOT create a digest file in `digests/`.
   - Do NOT update `MANIFEST.md` (summary pages are not raw sources).
   - Log entry verb is `rewrite` (not `ingest`).

   **Graphify Integration**: Always execute `python3 scripts/graphify_wiki.py --wiki-root "$wiki_path"` after saving any new or updated synthesis page to compile and refresh the `_graph.json` semantic graph index.

8. Append log entry to `wiki/log/<current-quarter>.md`.

9. Report:
   - Default: "Synthesis digest written at `<path>`. N source pages synthesized."
   - `--update`: "Summary page updated: `wiki/<type>s-summary.md`. N entity pages synthesized."

## Error handling

- No matching pages: "No pages matched the query. Try broadening or check `<wiki>/wiki/` contents."
- FC-5, FC-6, FC-13: standard handling.

## Natural language triggers for --update

The `wiki` router skill should map these phrases to `synthesize --update`:
- "update the competitors summary" → `--update --type competitor`
- "refresh the features summary" → `--update --type feature`
- "make a [type] summary page" → `--update --type <type>`
- "update the [type] overview" → `--update --type <type>`

## HARD RULE

The synthesizer agent is prompted never to propose modifications to existing pages. If the output for some reason references "update page X", treat it as malformed (exit-code-1 re-dispatch path).

The confirmation gate for `--update` in-place rewrites is HARD — same principle as `overview-refresh`. No write happens without explicit `yes` from the user when the file already exists. The synthesizer agent dispatch, validation, and model-escape-hatch logic are not affected by `--update`.
