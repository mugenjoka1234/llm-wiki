---
name: wiki-forget
description: Remove a wiki from the plugin registry. Does NOT delete any files — only removes the registry entry. Use when the user says "forget this wiki", "remove wiki from registry", "deregister wiki", "wiki was deleted", or when a stale entry appears in the registry. Arg: optional path to the wiki to remove.
---

# wiki-forget skill

## Preflight

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded via --plugin-dir or installed in a marketplace?}"
```

## Flow

1. **Load registry:**
   ```bash
   registry="${CLAUDE_PLUGIN_DATA}/registry.txt"
   ```
   If `registry.txt` does not exist or is empty: respond "Registry is empty. Nothing to forget." — STOP.

2. **Identify target:**
   - If the user passed a path argument: use that as the target path (resolve to absolute).
   - If no path was given: read all lines from `registry.txt`, parse each as `<path>|<domain>|<created>|<last-used>`, then display a numbered list with reachability status:
     ```
     Registered wikis:
     1. /Users/x/llm-wiki/research (research) ✅ found
     2. /Users/x/old-wiki (old-domain) ⚠️ directory not found
     ```
     Reachability rules (same as `is_wiki()` in `resolve_wiki.py`):
     - ✅ found = directory exists AND contains a `CLAUDE.md` with `## Purpose`
     - ⚠️ not found = directory absent OR `CLAUDE.md` missing or lacks `## Purpose`

     Prompt: "Which wiki to remove? Enter a number or an absolute path."
     Wait for user response, then resolve to the matching path.

3. **Validate path is registered:**
   If the resolved path does not appear in `registry.txt`: respond "Path not found in registry: `<path>`. Use `wiki-forget` with no args to see all registered wikis." — STOP.

4. **Confirm with user:**
   Show: "Remove `<path>` (`<domain>`) from registry? This does NOT delete any files. (yes/no)"
   - If the user answers anything other than `yes` / `y`: respond "Cancelled. Registry unchanged." — STOP.

5. **Remove entry and compact:**
   - Read all lines from `registry.txt`.
   - Filter out every line whose first field (`|`-split) matches the target path (handles duplicate entries).
   - Write the filtered lines to a temp file (`registry.txt.tmp`) in the same directory, then atomically rename it to `registry.txt` — the same pattern used by `compact_registry()` in `resolve_wiki.py`.
   - Then run compaction to deduplicate any remaining duplicates:
     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --compact
     ```

6. **Orphan check (federation-aware):**
   After writing the updated registry, re-read `registry.txt` and scan every remaining entry for a 5th pipe-delimited field that matches the removed path (parent reference used by federated/child wikis).
   - If any such entries exist, warn:
     ```
     ⚠️ Warning: the following wikis listed the removed wiki as their parent and may need re-parenting:
     - /path/to/child-wiki (child-domain)
     ```

7. **Report:**
   "`<domain>` removed from registry. Files at `<path>` were NOT deleted."

## Error handling

- FC-13 (CLAUDE_PLUGIN_ROOT not set): abort with remediation message.
- Registry file unreadable or corrupt lines (fewer than 4 pipe-delimited fields): skip those lines silently during parsing; proceed with valid entries.
- Temp-file write failure: report "Could not write registry update — check permissions on `${CLAUDE_PLUGIN_DATA}/`." — do NOT partially modify `registry.txt`.
