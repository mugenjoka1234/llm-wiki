---
name: research
description: Research a topic using web sources. Runs a three-stage pipeline — a Haiku planner finds URLs, a no-LLM fetcher stores clean markdown snapshots once, and the Sonnet reader synthesizes from the saved files with URL citations — then saves findings to raw/ and offers to ingest into the wiki. Supports --fetcher free|firecrawl. Use when the user says "research X", "look up Y", "find out about Z", "what's the latest on X", "investigate X", "answer the open questions on [[page]]", or "deep dive on X" (deep dive → passes --deep, raising the round cap).
---

# research skill

## When this skill applies

Dispatch when:
- The wiki §Agent Catalog has a `?` gap entry for the topic
- An entity page shows `confidence: low` or has 3+ open sub-questions
- The user says "research X", "find out about Y", or "investigate Z"
- The query skill answered with "the wiki has no coverage of X"

Check the wiki's §Agent Catalog first. If `✓` entries exist for the topic, prefer `/llm-wiki:query` — don't re-research what's already covered.

## Pipeline overview

```
PLAN (wiki-planner, Haiku) → FETCH (fetch_sources.py, no LLM) → READ (wiki-researcher, Sonnet)
```

Fetching happens exactly once, in stage 2, to `raw/snapshots/*.md` files each carrying a
YAML front-block with the complete original `source_url`. The reader never touches the
web — it synthesizes from the saved snapshots and cites each file's `source_url`.

When `--fetcher firecrawl` is active, source discovery and scraping follow Firecrawl's
published CLI skill contract (`firecrawl-search`, `firecrawl-scrape`) — the planner runs
`firecrawl search` and the fetcher runs `firecrawl scrape --only-main-content --format
markdown --redact-pii`.

## Preflight

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded via --plugin-dir or installed in a marketplace?}"
```

## Flow

1. **Resolve target wiki.**

   Parse `$ARGUMENTS` for an optional `--wiki <path>` flag before the topic.

   ```bash
   # Explicit wiki path override (e.g. from factory's wiki-integration skill)
   if [[ "$ARGUMENTS" =~ --wiki[[:space:]]+([^[:space:]]+) ]]; then
     explicit_wiki="${BASH_REMATCH[1]}"
     resolution=$("${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --wiki-path "$explicit_wiki")
     topic="${ARGUMENTS/--wiki $explicit_wiki/}"
   else
     resolution=$("${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --cwd "$(pwd)")
     topic="$ARGUMENTS"
   fi
   ```

   Parse JSON. If `none`, offer to scaffold via `/llm-wiki:wiki-init` (inline chain — see below). If `registry-ambiguous`, prompt user to pick.

2. **Confirm scope with the user.**
   - If the user said "answer the open questions on [[page]]", read that page's Open Questions section and enumerate the questions verbatim. Confirm with user before dispatching.
   - If the user gave a topic, ask 1-2 narrowing questions if the topic is very broad. Narrow is better.

3. **Parse the fetcher flag.** Default `free`.
   ```bash
   fetcher=free
   if [[ "$ARGUMENTS" =~ --fetcher[[:space:]]+([a-z]+) ]]; then
     fetcher="${BASH_REMATCH[1]}"
   fi
   deep=false; [[ "$ARGUMENTS" == *--deep* ]] && deep=true
   ```

4. **Plan (Haiku).** Build the planner prompt and dispatch `llm-wiki:wiki-planner`.
   ```bash
   prompt=$("${CLAUDE_PLUGIN_ROOT}/scripts/build_agent_prompt.py" \
       --agent planner --wiki "$wiki_path" --questions "$questions")
   ```
   Handle exit code 1 (likely missing ## Purpose) per FC-4. Pass the
   `--fetcher $fetcher` intent in the task text so the planner knows which backend to
   use. Dispatch via the Agent tool with `subagent_type: llm-wiki:wiki-planner` (do NOT
   fall back to general-purpose — FC-13). Validate with `--agent planner`; re-dispatch
   once if malformed. Extract the JSON array from `<wiki-plan>` and write it to a temp
   `plan.json` (shape: `[{"url","why","recency"}]`). If the plan is empty → **FC-14
   (no_sources_planned):** tell the user, offer to accept URLs manually.

5. **Fetch once (no LLM).**
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/fetch_sources.py" \
       --plan "$plan_json" \
       --snapshots-dir "$wiki_path/raw/snapshots" \
       --fetcher "$fetcher"
   fetch_rc=$?
   ```
   - `fetch_rc == 3` → **FC-16 (firecrawl_unavailable):** STOP and ask the user:
     "Firecrawl isn't working (see reason above). (a) retry, (b) switch this run to
     `--fetcher free`, (c) abort. Which?" Do NOT auto-fall back.
   - `fetch_rc == 1` → **FC-15 (all_fetch_failed):** every URL failed; do NOT dispatch
     the reader. Report and offer to retry / supply URLs.
   - `fetch_rc == 0` → proceed. Read `raw/snapshots/fetch-manifest.json` for the file list.

   Free-path note: URLs whose plain fetch comes back thin (< 500 chars) can be
   escalated — load the page with the Playwright MCP tools (`browser_navigate` then
   `browser_snapshot`), save the rendered HTML to a temp file, and re-run
   `fetch_sources.py` with a plan of just those URLs pointed at the rendered HTML.
   This is best-effort; a still-thin source stays `failed:thin` in the manifest.

6. **Read (Sonnet).** Build the reader prompt with the snapshot file paths from the
   manifest:
   ```bash
   prompt=$("${CLAUDE_PLUGIN_ROOT}/scripts/build_agent_prompt.py" \
       --agent researcher --wiki "$wiki_path" \
       --questions "$questions" --snapshots "$snapshot_paths")
   ```
   Dispatch via the Agent tool with `subagent_type: llm-wiki:wiki-researcher`. **Do NOT
   fall back to general-purpose** (FC-13). Validate:
   ```bash
   output_file=$(mktemp)
   echo "$agent_output" > "$output_file"
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_agent_output.py" \
       --agent researcher --content "$output_file"
   validate_exit=$?
   ```
   - Exit 0 → proceed.
   - Exit 1 (malformed) → re-dispatch once with a stricter prompt. If still malformed, surface raw content to user, don't save (FC-6).
   - Exit 2 (agent emitted `<wiki-error/>`) → surface the error code + message to the user (FC-5); do not save.

7. **Round-2 (capped).** If the reader emitted `<need-more queries=... urls=.../>`
   after `</wiki-output>` and `rounds_done < cap` (cap = 3 if `--deep` else 2):
   feed the new queries back to step 4 (plan) and/or the direct urls straight to
   step 5 (fetch), accumulate snapshots, then re-dispatch the reader over the
   combined set. Otherwise proceed with what you have — the reader's "What I could
   NOT find" section records the remaining gaps.

8. **Save research file, MANIFEST, registry, offer-to-ingest.**
   - Extract `<wiki-output>` content and write it to
     `<wiki>/raw/research-<slug>-<today>.md` with the Write tool. The snapshots
     already exist on disk from step 5 — do NOT re-fetch anything.
   - Append MANIFEST entry IMMEDIATELY (state self-describing on partial failure):
     ```bash
     echo "- [ ] \`research-${slug}-${today}.md\` — Research output • public • pending-ingest" >> "$wiki_path/raw/MANIFEST.md"
     ```
     If MANIFEST doesn't exist yet, create it with the standard header first.
   - Update registry last-used:
     ```bash
     echo "${wiki_path}|${domain}|${created}|${today}" >> "${CLAUDE_PLUGIN_DATA}/registry.txt"
     ```
   - Present a summary of the research and ask: "Ingest now, or hold for review?" If yes, invoke the `/llm-wiki:wiki-ingest` skill (full name — NOT `llm-wiki:ingest`) with the raw file path and `--auto` flag.

## Error handling

- FC-1 (no wiki + registry empty): offer to scaffold inline.
- FC-4 (missing ## Purpose): surface remediation.
- FC-5 (agent error envelope): surface code + message.
- FC-6 (malformed after retry): surface raw content.
- FC-13 (plugin subagent unavailable): "Plugin bundled agent not available. Is the plugin loaded via `claude --plugin-dir` or a marketplace install? See plugin README."
- FC-14 (no_sources_planned): planner returned no usable URLs. Tell the user and offer to accept URLs manually (write them into `plan.json` and continue at step 5).
- FC-15 (all_fetch_failed): every planned URL failed to fetch on the free path. Do not dispatch the reader; offer to retry or accept replacement URLs.
- FC-16 (firecrawl_unavailable): the user asked for Firecrawl and it is not working (missing `FIRECRAWL_API_KEY`, CLI absent, credits exhausted, API error). HALT and ask: retry / switch to free for this run / abort. Never silently fall back.

## Chaining inline to wiki-init

If `resolve_wiki.py` returns `source: none`, prompt: "No wiki found here. Scaffold one in this folder? [y/n]". On `y`, invoke `/llm-wiki:wiki-init` inline. After scaffold completes, resume the research flow.
