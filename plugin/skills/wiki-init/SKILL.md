---
name: wiki-init
description: Scaffold a new llm-wiki in the current directory. For full project setup (wiki + docs_path + factory home) prefer the factory-init skill, which delegates here. Invoke directly when the user says "initialize a wiki", "scaffold a wiki", or on Gemini CLI, where wiki-init is the supported setup path (factory-init surfaces there but is unsupported).
---

# wiki-init skill

Scaffold a new wiki at `<cwd>/<domain>/` with all templates, agents, lint script, git init, and registry registration.

## Preflight

Verify the plugin is loaded:

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded via --plugin-dir or installed in a marketplace?}"
```

## Pre-checks (run BEFORE asking the user any questions)

1. Check if cwd is already a wiki: run `${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py --cwd "$(pwd)"`. If source is `cwd`, abort: "A wiki already exists at the current directory."

2. Walk up parent directories to `$HOME` (or `/`, whichever comes first). If ANY ancestor contains a `CLAUDE.md` with `## Purpose`, abort: "You are inside an existing wiki at `<ancestor>`. Nested wikis are not supported."

```bash
dir="$(pwd)"
while [ "$dir" != "/" ] && [ "$dir" != "$HOME" ]; do
    dir="$(dirname "$dir")"
    if [ -f "$dir/CLAUDE.md" ] && grep -q "^## Purpose" "$dir/CLAUDE.md" 2>/dev/null; then
        echo "Nested wiki detected at $dir"
        exit 1
    fi
done
```

## Pause-and-ask

Prompt the user for four answers:

1. **Domain name** — pre-fill from cwd basename. Example: "research", "notes", "ai-learning".
2. **Purpose** — 1-2 sentences. Example: "Competitive intel and market research for product work."
3. **Entity types** — offer the 9 defaults and ask if they want to customize: `competitor, initiative, jtbd, feature, segment, experiment, metric, decision, source` (plus `synthesis` which is reserved for index/overview/glossary/people/_health). Customization: add or remove entries from this list.
4. **Section-naming conventions** — offer the defaults and ask if they want to customize: `Strengths / Weaknesses` (for competitors), `Trade-offs accepted` (for decisions), `Pain points` (for JTBDs/segments), `Caveats & limitations` (for metrics).

Confirm all answers before proceeding.

## Scaffold

1. Create the new wiki directory tree at `<cwd>/<domain>/`:

```bash
mkdir -p "$domain"/{raw/{assets/screenshots,snapshots,_ingest,_scrubbed},wiki/{log,_pii,_drafts,_archive,digests,questions},_templates,docs,scripts/tests}
touch "$domain"/raw/assets/screenshots/.gitkeep
touch "$domain"/raw/snapshots/.gitkeep
touch "$domain"/raw/{_ingest,_scrubbed}/.gitkeep
touch "$domain"/wiki/{_drafts,_archive,digests}/.gitkeep
```

2. Copy all entity templates (currently 15 files — entity types, `index.md`/`overview.md`, `question.md`/`session.md`, and the stub templates wiki-ingest uses for un-typed pages):

```bash
cp "${CLAUDE_PLUGIN_ROOT}/assets/entity-templates/"*.md "$domain/_templates/"
```

3. Copy the bundled scripts:

```bash
cp "${CLAUDE_PLUGIN_ROOT}/assets/scripts/lint.py" "$domain/scripts/lint.py"
cp "${CLAUDE_PLUGIN_ROOT}/assets/scripts/capture_snapshots.py" "$domain/scripts/capture_snapshots.py"
cp "${CLAUDE_PLUGIN_ROOT}/assets/scripts/graphify_wiki.py" "$domain/scripts/graphify_wiki.py"
```

4. Substitute placeholders using Python (handles multi-line values; sed cannot):

```bash
today=$(date +%Y-%m-%d)
# Format entity_types as bullet list
entity_types_formatted=$(printf -- "- %s\n" "${entity_types[@]}")
# section_names_formatted defaults to proven conventions
section_names_formatted="- **Strengths / Weaknesses** — pros/cons (competitors). Do not use \"Pros/Cons\".
- **Trade-offs accepted** — what was given up (decisions). Do not use \"Costs\".
- **Pain points** — user-side difficulties (JTBDs, segments). Do not use \"Friction points\".
- **Caveats & limitations** — metric definition/data quality issues. Distinct from weaknesses.
- **Status** — lifecycle progress (initiatives, features, experiments)."

export domain purpose entity_types_formatted section_names_formatted today

for tmpl_basename in CLAUDE.md README.md schema-decisions.md; do
    src="${CLAUDE_PLUGIN_ROOT}/assets/${tmpl_basename}.template"
    # schema-decisions.md goes under docs/
    if [ "$tmpl_basename" = "schema-decisions.md" ]; then
        dst="$domain/docs/$tmpl_basename"
    else
        dst="$domain/$tmpl_basename"
    fi
    _SRC="$src" _DST="$dst" python3 -c "
import os
src = os.environ['_SRC']
dst = os.environ['_DST']
subs = {
    '{{DOMAIN}}':         os.environ.get('domain', ''),
    '{{PURPOSE}}':        os.environ.get('purpose', ''),
    '{{ENTITY_TYPES}}':   os.environ.get('entity_types_formatted', ''),
    '{{SECTION_NAMES}}':  os.environ.get('section_names_formatted', ''),
    '{{DATE}}':           os.environ.get('today', ''),
}
text = open(src).read()
for k, v in subs.items():
    text = text.replace(k, v)
with open(dst, 'w') as f:
    f.write(text)
" || { echo "substitution failed for $tmpl_basename"; exit 1; }
done
unset _SRC _DST

cp "${CLAUDE_PLUGIN_ROOT}/assets/gitignore.template" "$domain/.gitignore"

# Write schema.yaml — machine-readable entity type declarations
python3 -c "
import os
domain = os.environ.get('domain', '')
types = os.environ.get('entity_types_formatted', '').strip()
lines = ['domain: ' + domain, 'entity_types:']
for t in types.splitlines():
    t = t.strip().lstrip('- ').strip()
    if t:
        lines.append('  - ' + t)
print('\n'.join(lines))
" > "$domain/schema.yaml" || echo "schema.yaml generation failed, continuing"
```

5. Write initial wiki skeleton files. Follow the patterns from the entity templates for each file's shape.

   Files to create: `wiki/index.md`, `wiki/overview.md`, `wiki/glossary.md`, `wiki/people.md`, `wiki/_health.md`, `wiki/_pii/README.md`, `raw/MANIFEST.md`.

   **`wiki/index.md` and `wiki/overview.md` have real templates — start from
   them, don't author freehand.** Copy `_templates/index.md` and
   `_templates/overview.md` (already present in `$domain/_templates/` from
   step 2) into place, then fill in the placeholder title and replace the
   `TBD` frontmatter fields with real values the same way the log file does
   (`last-updated`/`as-of`: `${today}`; `quarter`: `${quarter}`; `confidence:
   high` — see "Confidence values" below):

   ```bash
   cp "$domain/_templates/index.md"    "$domain/wiki/index.md"
   cp "$domain/_templates/overview.md" "$domain/wiki/overview.md"
   # then edit both: replace the {{...}} title placeholder and the TBD
   # frontmatter fields (last-updated, as-of, quarter, confidence) with real
   # values, and fill overview.md's "## Current theses" with real content.
   # lint only enforces this once the wiki has its first entity page — but
   # fill it in now anyway rather than leaving a placeholder to trip on later.
   ```

   `index.md`'s body already carries the `<!-- AUTO-GENERATED by lint.py -->`
   marker pair — leave it in place; `lint.py` fills the block between the
   markers on its first run (§Start here + §Agent Catalog) and preserves
   everything else in the file.

   **Log file (required frontmatter — lint validates every .md under wiki/):**

   ```bash
   quarter=$(date +%Y-Q$(( ($(date +%-m) - 1) / 3 + 1 )))
   cat > "$domain/wiki/log/${quarter}.md" << EOF
   ---
   type: synthesis
   status: active
   last-updated: ${today}
   as-of: ${today}
   quarter: ${quarter}
   okr: []
   confidence: high
   sources: []
   related: []
   tags: [log]
   ---
   # Log — ${quarter}

   ## [${today} 00:00] scaffold — wiki initialized | touched: [] | ${domain} wiki created via llm-wiki plugin
   EOF
   ```

   **Why the frontmatter is required:** `lint.py` validates every `.md` under `wiki/` that doesn't start with `_`. Log files live at `wiki/log/` (no underscore prefix), so they are linted. Without frontmatter, the first `lint.py` run after scaffold fails with schema errors — requiring a manual fix. Writing it at scaffold time means `lint.py` exits 0 on a fresh wiki.

   **Confidence values:** skeleton synthesis pages (index, overview, glossary,
   people, log) set `confidence: high` explicitly — they are navigational, not
   claims. Entity pages copied from `_templates/` ship `confidence: TBD`, which
   lint rejects until the author declares a real value (same forcing pattern as
   `last-updated: TBD`). Never bulk-replace TBD with a default.

   **These stubs carry the FULL required-fields schema** (the same one
   `lint.py`'s `REQUIRED_FIELDS` enforces on every `.md` under `wiki/`), not
   just the four visible above the fold in the log file — `lint.py`
   regenerates both catalogs' content on every run, but it does not relax the
   schema check for the pre-regenerated stub, so a stub missing `quarter`,
   `okr`, `confidence`, `sources`, `related`, or `tags` fails the *first*
   lint run with SCHEMA ERRORS (exit 2) even though it self-heals on the
   second run. Match this frontmatter shape exactly — it's what `lint.py`
   itself writes when it regenerates these files:

   ```bash
   # Initialize digests/catalog.md stub (lint.py regenerates on first run)
   cat > "$domain/wiki/digests/catalog.md" << EOF
   ---
   type: synthesis
   status: active
   last-updated: ${today}
   as-of: ${today}
   quarter: ${quarter}
   okr: []
   confidence: high
   sources: []
   related: []
   tags: []
   ---
   # Digest Catalog

   Auto-generated by lint.py. Run \`python3 scripts/lint.py\` to populate.
   EOF

   # Initialize questions/catalog.md stub
   cat > "$domain/wiki/questions/catalog.md" << EOF
   ---
   type: synthesis
   status: active
   last-updated: ${today}
   as-of: ${today}
   quarter: ${quarter}
   okr: []
   confidence: high
   sources: []
   related: []
   tags: []
   ---
   # Questions Catalog

   Auto-generated by lint.py. Run \`python3 scripts/lint.py\` to populate.
   EOF
   ```

5b. **Set up Obsidian automatically** (zero manual configuration).

First, check if Obsidian is installed:

```bash
if ls /Applications/Obsidian.app &>/dev/null; then
    obsidian_installed=true
else
    obsidian_installed=false
fi
```

If installed, ask the user: "Obsidian is installed. Set up the vault automatically? (y/n) — I'll configure settings, install Dataview, and open it for you."

On yes, run the full setup:

```bash
abs_path="$(cd "$domain" && pwd)"

# Step 1: Copy Obsidian settings files
mkdir -p "$domain/.obsidian/plugins/dataview"
cp "${CLAUDE_PLUGIN_ROOT}/assets/obsidian-config/app.json"               "$domain/.obsidian/app.json"
cp "${CLAUDE_PLUGIN_ROOT}/assets/obsidian-config/community-plugins.json" "$domain/.obsidian/community-plugins.json"
cp "${CLAUDE_PLUGIN_ROOT}/assets/obsidian-config/core-plugins.json"      "$domain/.obsidian/core-plugins.json"
cp "${CLAUDE_PLUGIN_ROOT}/assets/obsidian-config/hotkeys.json"           "$domain/.obsidian/hotkeys.json"

# Step 2: Download and install Dataview plugin directly (so it's ready, no install button needed)
echo "Downloading Dataview plugin..."
curl -sL "https://github.com/blacksmithgu/obsidian-dataview/releases/latest/download/main.js" \
     -o "$domain/.obsidian/plugins/dataview/main.js"
curl -sL "https://github.com/blacksmithgu/obsidian-dataview/releases/latest/download/manifest.json" \
     -o "$domain/.obsidian/plugins/dataview/manifest.json"

# Step 3: Open the vault in Obsidian
# macOS: triggers "Open as vault?" dialog if new — user clicks one button and it's done
open -a Obsidian "$abs_path"
echo "Obsidian opening — click 'Open' if prompted to confirm the new vault."
```

If Obsidian is NOT installed, tell the user:
"Obsidian not found. Install it with `brew install --cask obsidian`, then open Obsidian → 'Open folder as vault' → select `$abs_path`."

6. **Verify the fresh scaffold lints clean (belt and braces).** Run lint once,
   before committing anything, so a schema mistake never enters the wiki's
   history:

   ```bash
   python3 "$domain/scripts/lint.py" --wiki-root "$domain"
   ```

   Expected: `OK: N pages, no issues.` and exit 0. If it exits non-zero, this
   is a scaffold bug (a stub is missing a required field) — fix the stub in
   this SKILL and re-scaffold; do not paper over it by just re-running lint a
   second time.

7. Initialize git and commit:

```bash
cd "$domain"
git init -b main
git add .
git commit -m "scaffold: $domain wiki (via llm-wiki plugin)"
cd ..
```

8. Register in registry:

```bash
abs_path="$(cd "$domain" && pwd)"
registry="${CLAUDE_PLUGIN_DATA:-.}/registry.txt"
mkdir -p "$(dirname "$registry")"
echo "${abs_path}|${domain}|${today}|${today}" >> "$registry"
```

## Optional: Register as child of a parent wiki

If called with `--parent <parent-path>` flag:

1. Validate parent path is a registered wiki (run `resolve_wiki.py --wiki-path "<parent-path>"`; abort if source is `none`).

2. Run the link subcommand:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" link "$(pwd)/$domain" "<parent-path>"
   ```

3. Create the subdomains directory in the child wiki:
   ```bash
   mkdir -p "$domain/wiki/subdomains"
   touch "$domain/wiki/subdomains/.gitkeep"
   ```

4. Add a `## Sub-domains` section to `<domain>/wiki/index.md`:
   ```markdown
   ## Sub-domains
   | Sub-wiki | Domain | Last ingested | Top entities |
   |---|---|---|---|
   | *(no child wikis yet)* | | | |
   ```

5. Report: "Linked as child of <parent-domain>."

## Report

After successful scaffold, tell the user:

- Wiki created at `<abs-path>`
- Next steps: `cd <domain>` then start using `/llm-wiki:research <topic>`, `/llm-wiki:analyze <file>`, etc.

## Error handling

- FC-1 (no wiki + registry empty) via another skill: offer to scaffold.
- FC-10 (nested wiki): abort with remediation.
- FC-13 (CLAUDE_PLUGIN_ROOT not set): abort.
- If any scaffold step fails, report the error with specific remediation.
