---
name: query
description: Answer a question using the wiki's pre-synthesized knowledge. Reads index → finds matching pages → synthesizes answer with [[wikilink]] citations. Use when the user asks "what do we know about X", "tell me about Y", "what's the status of Z", "summarize X", "compare X and Y", "what are our gaps in Z", "what does the wiki say about X", or any question that a wiki reader would ask.
---

# query skill

## Preflight

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded via --plugin-dir or installed in a marketplace?}"
```

## Default posture

Check the wiki **before** answering from training data. If a task involves a named entity, a comparison, or a claim that could be sourced — check first.

False positive (check, find nothing): costs 2 seconds.
False negative (answer from training data when wiki has better research): costs user trust.

## Flow

### 1. Resolve target wiki

Parse `$ARGUMENTS` for an optional `--wiki <path>` flag before the question text.

```bash
# If user passed --wiki /path/to/wiki, use that explicitly
if [[ "$ARGUMENTS" =~ --wiki[[:space:]]+([^[:space:]]+) ]]; then
  explicit_wiki="${BASH_REMATCH[1]}"
  resolution=$("${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --wiki-path "$explicit_wiki")
  question="${ARGUMENTS/--wiki $explicit_wiki/}"  # strip flag from question
else
  resolution=$("${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --cwd "$(pwd)")
  question="$ARGUMENTS"
fi
```

Parse JSON. If `source: none`, respond: "No wiki found here. Research first with 'research X' or set up a wiki with 'create a new wiki'." Do NOT auto-scaffold for query — a query implies the wiki already exists.

**Multi-wiki queries:** To query across multiple wikis, invoke this skill once per wiki with `--wiki <path>`, then synthesize the combined answers. Example: `/llm-wiki:query --wiki ~/pm-hub/reporting-roadmap/wiki "what do we know about Square's reporting?"` queries specifically the reporting wiki regardless of cwd.

### 2. Read index or semantic graph for orientation

1. Check if a semantic knowledge graph exists at `$wiki_path/wiki/_graph.json`.
2. **If `_graph.json` exists**:
   - Open it and lookup the query entity (e.g. `boram`) or search term (e.g. `rates`, `compliance`) under the `"entities"` or `"keywords"` nodes.
   - Extract the `"path"`, `"start_line"`, and `"end_line"` for the matching targets.
   - Use the `read_file` tool passing `start_line` and `end_line` parameters to read **only** those specific line ranges. This completely bypasses the need for full-file reads or greps!
3. **If `_graph.json` does not exist**:
   - Fallback to reading the index file: Read `<wiki>/wiki/index.md`. Use the `## All pages` static fallback section if present (non-Obsidian context); otherwise read the full file.

### 3. Identify candidate pages (Fallback if no `_graph.json` is present)

If no semantic graph index is available, use a grep strategy based on the question:

```bash
# By keyword in body
grep -rl "<keyword>" "$wiki_path/wiki/" --include="*.md" | grep -v "/_" | grep -v "/digests/"

# By type (e.g. "compare competitors" → all competitor pages)
grep -rl "^type: competitor" "$wiki_path/wiki/" --include="*.md" | grep -v "/digests/"

# By tag
grep -rl "<tag>" "$wiki_path/wiki/" --include="*.md" | grep -v "/_"
```

Select the top 5 most relevant pages by keyword density + `last-updated` recency.

### 4. Read candidate pages (cap: 15 total)

Read the selected entity pages. If a page's `related:` or `sources:` fields reference additional pages that seem directly relevant, fan out — **ONE HOP ONLY**. Never recursively expand links.

If more than 15 pages seem necessary: stop and tell the user "This query spans the full wiki (~N pages). I'll answer from the top 15 by relevance — let me know if you need a broader sweep."

### 5. Check digests for deeper evidence

If the question needs more than entity-page depth (e.g. "what's the evidence for X", "where does that number come from"), also read the relevant digest(s) from `wiki/digests/`. Limit to 5 digests max per query.

### 6. Synthesize answer

Write the answer directly — do not dispatch a subagent for query. This skill runs in the main session context for speed.

Format rules:
- Every non-obvious claim cites a `[[wikilink]]` to its source page.
- Lead with the direct answer, not context.
- For comparison questions: use a table.
- For status questions: lead with current status, then history.
- For gap questions: lead with the gap, then evidence.
- Keep to 200–400 words unless the question is complex. Dense is better than comprehensive.

### 7. Offer to file back

After answering, offer: "File this as a new wiki page? (y/n — I'll suggest a slug and type.)"

If yes: propose `type: synthesis`, slug like `query-<topic>-<date>`, save to `wiki/digests/`.

### 8. Offer to research further

If the answer required caveats like "I couldn't find data on X in the wiki" or "this was last updated N months ago", offer: "Research this further? I can dispatch a web research session and ingest the findings."

## Decision rules

| User says | Route to |
|---|---|
| "what do we know about X" | This skill (query) |
| "research X" | `/llm-wiki:research` |
| "analyze this file" | `/llm-wiki:analyze` |
| "is the wiki up to date?" | `/llm-wiki:wiki-lint` |
| "summarize all competitors" | This skill OR `/llm-wiki:synthesize` if user wants a persistent digest |
| "critique [[page]]" | `/llm-wiki:critique` |

## Error handling

- No matching pages: "Nothing in the wiki matches that query yet. Want me to research it?"
- Wiki empty (only index/overview): "The wiki exists but has no entity pages yet. Research first."
