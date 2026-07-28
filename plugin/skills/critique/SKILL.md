---
name: critique
description: Critique a wiki page. Fidelity mode (page has cited sources) — verify claims against sources. Challenge mode (page has no sources) — use web to find contrary evidence and alternative viewpoints, with user confirmation. Use when the user says "critique [[page]]", "verify [[page]]", "audit [[page]]", "challenge [[page]]", "red-team [[page]]".
---

# critique skill (dual-mode)

## Preflight

```bash
[ -d "${CLAUDE_PLUGIN_ROOT}/scripts" ] || { echo "llm-wiki plugin scripts not found (is the plugin installed and loaded?)"; exit 1; }
```

## Flow

1. Resolve target wiki.

2. Read the target page. Extract frontmatter. Look for `sources:` list.

3. **Mode detection:**
   - **Fidelity mode**: target has ≥1 source in `sources:` frontmatter. Proceed to step 4a.
   - **Challenge mode**: `sources:` is empty or absent. Inform user: "Page `<target>` has no sources to audit against. I'll do a challenge analysis using the web — find contrary evidence and propose alternative viewpoints. Proceed? [y/n]." If no, abort gracefully (FC-3). If yes, proceed to step 4b.

4a. **Fidelity mode setup:**
   - Read the target page + each cited source's digest (follow wikilinks).
   - Build prompt:
     ```bash
     prompt=$("${CLAUDE_PLUGIN_ROOT}/scripts/build_agent_prompt.py" \
         --agent critic --wiki "$wiki_path" --mode fidelity --target "$target")
     ```

4b. **Challenge mode setup:**
   - Build prompt:
     ```bash
     prompt=$("${CLAUDE_PLUGIN_ROOT}/scripts/build_agent_prompt.py" \
         --agent critic --wiki "$wiki_path" --mode challenge --target "$target")
     ```

5. Dispatch `wiki-critic` agent via Agent tool with `subagent_type: llm-wiki:wiki-critic`. Uses opus model + WebSearch/WebFetch for challenge mode. Do NOT fall back to general-purpose.

6. Validate output (`--agent critic`). Handle 0/1/2 branches.

7. **Offer to file the critique — filing goes through ingestion so it compounds,
   same as analyze and research.** Ask the user which:
   - **File into the wiki (compounds).** Write the critique findings to
     `<wiki>/raw/critique-<slug>-<today>.md`, append a MANIFEST entry, then invoke
     `/llm-wiki:wiki-ingest` (via the Skill tool, full name — NOT `llm-wiki:ingest`)
     with `--auto --wiki "$wiki_path" "$wiki_path/raw/critique-<slug>-<today>.md"`.
     Ingestion writes the digest, **back-propagates to the critiqued page** (so the
     audit is visible on the page it's about), and logs it.
     ```bash
     echo "- [ ] \`critique-${slug}-${today}.md\` — Critique output • public • pending-ingest" >> "$wiki_path/raw/MANIFEST.md"
     ```
     **Do NOT hand-write a bare `wiki/digests/critique-*.md`** — that orphans it
     (no catalog entry, no entity enrichment, no log).
   - **Add findings to the target page's Open Questions** (each finding becomes a
     dated checkbox) — a lighter action for surfacing the issues on that page.
   - **Both** — file into the wiki and add open questions to the target page.
   - **Discard** — print only (the ephemeral case).

## Error handling

- FC-3 (target has no sources, user declined challenge): "OK — aborting critique. Add sources to the page first, or invoke critique again and accept challenge mode."
- FC-5, FC-6, FC-13: standard handling.
- Target page not found: "Page `<target>` not found in wiki."
