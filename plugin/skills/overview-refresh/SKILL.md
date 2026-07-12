---
name: overview-refresh
description: Rewrite wiki/overview.md in place after major ingest sessions. Reads recent log entries and top entity pages, drafts new content, shows diff, requires confirmation before writing. Use when the user says "refresh the overview", "update the overview", "overview is stale", "rewrite overview". Optional: --since YYYY-MM-DD to scope the change window.
---

# overview-refresh skill

## Preflight

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded via --plugin-dir or installed in a marketplace?}"
```

## Flow

1. **Resolve wiki:**
   ```bash
   resolution=$("${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --cwd "$(pwd)")
   ```
   Parse JSON. If source is `none` → "No wiki found here. Run `/llm-wiki:wiki-init` first." — STOP. If `registry-ambiguous` → present options and ask user to pick.

2. **Read current overview.md:**
   - Check that `$wiki_path/wiki/overview.md` exists. If not → "No overview.md in wiki/. Run `/llm-wiki:wiki-init` to scaffold one." — STOP.
   - Read the file and extract the `as-of:` date from its YAML frontmatter. This is the default `--since` value.
   - If the user passed `--since YYYY-MM-DD`, use that date instead of the frontmatter value.

3. **Read log since --since date:**
   ```bash
   quarter=$(date +%Y-Q$(( ($(date +%-m)-1)/3+1 )))
   log_file="$wiki_path/wiki/log/${quarter}.md"
   ```
   Read `$log_file`. Extract all entries with timestamps strictly after the `--since` date.
   If no entries are found for that period → "No log entries since [date]. Nothing to refresh." — STOP.

4. **Read top-10 most recently updated entity pages:**
   ```bash
   grep -rl "type:" "$wiki_path/wiki/" "$wiki_path/wiki/digests/" 2>/dev/null \
     | xargs grep -L "type: synthesis" 2>/dev/null \
     | xargs ls -t 2>/dev/null \
     | head -10
   ```
   Read each of these pages in full.

5. **Draft new overview content** (inline — do NOT dispatch the wiki-synthesizer agent):

   Produce content matching this EXACT schema (keep the existing frontmatter, bump `last-updated` and `as-of` to today's date):

   ```markdown
   ## As of YYYY-MM-DD

   ## What changed since last refresh
   - <one bullet per new or updated entity, with [[wikilink]]>

   ## Top 5 insights
   1. <most important cross-cutting finding, with [[citation]]>
   2. ...
   3. ...
   4. ...
   5. ...

   ## Current theses
   - <claim> — confidence: high/med/low — last tested: [[digest-slug]]

   ## Open strategic questions
   - [ ] <question> — filed YYYY-MM-DD
   ```

   Base content on the log entries from step 3 and the entity pages from step 4. Do not invent claims not supported by the source material.

6. **Show the full draft to the user.** Display the entire proposed new content of `wiki/overview.md` (frontmatter + body).

7. **HARD CONFIRMATION GATE — never skip, no --force flag, no auto-approve:**

   Say exactly: "This will replace wiki/overview.md. Confirm? (yes to write / no to discard)"

   - If the user responds with anything other than an affirmative (yes / y / confirm / proceed): output "Discarded. No files were changed." — STOP. Do not write anything.
   - If the user confirms: proceed to step 8.

8. **Write, lint, log:**
   ```bash
   # Write the new content to $wiki_path/wiki/overview.md
   # Run lint
   python3 "$wiki_path/scripts/lint.py"
   # Append log entry
   today=$(date +%Y-%m-%d)
   now=$(date +%Y-%m-%d\ %H:%M)
   echo "## [${now}] rewrite — [[overview]] | touched: [overview] | overview refreshed (as-of: ${today})" \
     >> "$wiki_path/wiki/log/${quarter}.md"
   ```
   If lint exits with errors: surface the lint output. Note: the write already happened — do not attempt rollback. Flag the errors for manual fix.

9. **Report:**
   "overview.md refreshed. as-of updated to YYYY-MM-DD. N entity pages synthesized."

## Error handling

- No wiki found: "No wiki found here. Run `/llm-wiki:wiki-init` first."
- overview.md missing: "No overview.md in wiki/. Run `/llm-wiki:wiki-init` to scaffold one."
- Log file missing for current quarter: treat as empty log — "No log entries since [date]. Nothing to refresh."
- Lint fails after write: surface errors. The write already happened — do not attempt rollback, flag for manual fix.
- FC-13 (CLAUDE_PLUGIN_ROOT not set): abort with remediation message from preflight.

## HARD RULE

Do NOT dispatch the `wiki-synthesizer` agent. All synthesis in this skill runs inline. The confirmation gate in step 7 is non-negotiable: never auto-approve, never add a `--force` bypass, never skip it for any reason.
