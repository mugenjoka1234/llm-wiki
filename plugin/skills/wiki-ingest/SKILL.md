---
name: wiki-ingest
description: Ingest a raw source file into the wiki — runs the PII gate, produces a digest, updates entity pages, appends log. Use when the user says "ingest this", "add this file to the wiki", "there's a new doc in raw/", "process this source", or when chained automatically from research/analyze. Supports --auto mode when chained.
---

# wiki-ingest skill

## Preflight

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded via --plugin-dir or installed in a marketplace?}"
```

## Flow

### Resolve or inherit target wiki

1. If called with `--auto` flag (chained from research/analyze): target wiki path is passed in; skip resolution.
2. Otherwise: `resolve_wiki.py --cwd "$(pwd)"`. If source `none` → error. If ambiguous → present options.

### Verify input

If user passed a raw file path, verify it exists under `<wiki>/raw/`. If no path passed, scan `<wiki>/raw/MANIFEST.md` for `pending-ingest` entries and list them for the user to pick.

### PII gate (CRITICAL — must include --wiki-root)

```bash
python3 "$wiki_path/scripts/lint.py" --check-content "$raw_file" --wiki-root "$wiki_path"
gate_exit=$?
```

- `gate_exit == 0` → proceed.
- `gate_exit != 0` → PII detected. Update MANIFEST entry to `blocked: pii — flagged at lines L1,L2,...`. Show flagged spans to user. Offer pre-scrub workflow. DO NOT proceed to wiki write.

### Ingest workflow (from target wiki's CLAUDE.md)

Read `<wiki>/CLAUDE.md` § Ingest workflow. Execute step-by-step:

1. Write ingest plan to `<wiki>/raw/_ingest/<slug>.plan.md`.
2. Discuss takeaways with user (skip in --auto mode).
3. Write digest at `<wiki>/wiki/digests/<slug>.md` from `<wiki>/_templates/source.md` template.
   **CRITICAL — digest Summary guidance:**
   - For **research output files** (`raw/research-*.md`): Summary = 2 sentences describing SCOPE AND PURPOSE only — NOT a content summary. The raw file contains the full findings; the digest is navigation. Example: "Playwright research session covering Square and Lightspeed reporting features, May 2026. Answers 4 open questions on competitive reporting capabilities."
   - For **web clips and articles**: Summary = 2 sentences on what the source says — these are short enough that a brief summary adds value.
   - For **any source**: Key claims section is where the substantive content lives, with `→ [[entity-page]]` destinations. The raw file is the source of truth — the digest connects raw content to the wiki graph.
   - **Do NOT reproduce the full research content in the digest.** If you find yourself writing more than 4-5 bullet points in Key claims, you are over-summarizing. Extract the highest-signal claims that connect to entity pages; leave the rest in the raw file.
5a. **Append digest to `wiki/digests/catalog.md`.**

    Add one line:
    ```
    - [[{digest-slug}]] — {one-line summary of key finding} [{tags}] ({today})
    ```
    If `wiki/digests/catalog.md` does not exist, create it with standard synthesis frontmatter first. lint.py will regenerate the full file on the next lint run.

4. **Capture raw page snapshots** (for research files — do this with Bash, not a loop):

   ```bash
   cd "$wiki_path"
   python3 scripts/capture_snapshots.py "$raw_file" raw/snapshots/ --update-source
   ```

   This fetches every source URL from `## Sources`, saves verbatim page text to
   `raw/snapshots/`, and appends a `## Snapshots` section to the research file with
   relative links to each captured file. Print the JSON summary: e.g. "Captured 11/12 source pages."
   Failures are logged but don't block the ingest. Skip this step for non-research sources
   (web clips, PDFs) — the raw file itself is the verbatim source for those.

4b. **Stub-page offer** — check if any entity page in the plan already exists in a registered parent/sibling wiki:

   For each NEW entity page being created (not an update):
   - Check if a page with the same slug exists in registered parent or sibling wikis
   - If yes: offer the user a choice:
     ```
     A page for [[<slug>]] already exists in the <parent-domain> wiki.
     (a) Create full page here (duplicate)
     (b) Create stub page with external-ref pointer to <parent-domain>
     Default: (b) stub
     ```
   - If stub chosen: create the page from `_templates/stub.md` with:
     - Same frontmatter as the full template for that type
     - `external-ref: "wiki://<parent-domain>/<slug>"`
     - Body: "Full analysis: see [[external-ref: wiki://<parent-domain>/<slug>]]"

   Skip this step in `--auto` mode.

5. **Back-propagate to entity pages (CRITICAL — this is what makes the wiki compound):**

   After writing the digest, parse the `related:` list from the new digest's frontmatter. For each slug listed:

   a. Locate the entity page at `<wiki>/wiki/<slug>.md`.
   b. Add the new digest to the entity page's `sources:` frontmatter list (multi-line YAML form).
   c. Add a dated enrichment section to the entity page body. Use this form:

      ```markdown
      ## From [[<digest-slug>]] (YYYY-MM-DD)
      - <claim 1 from digest most relevant to this entity page>
      - <claim 2> (keep to 2-4 bullets — only the claims directly relevant to this entity)
      ```

   d. Bump the entity page's `last-updated` to today's date.
   e. Run `python3 "$wiki_path/scripts/lint.py" --check-content <entity-page>` before writing — PII gate applies to enrichment content too.

   **No Empty/Thin Pages Rule (Dual-Engine Standard)**:
   To prevent flatland folder pollution and empty, low-signal stub files, do **NOT** create a standalone file under `wiki/<slug>.md` if the entity lacks substantial, standalone content (under 1,500 characters or fewer than 3 robust claims).
   - **Action**: Instead, append the claims to the corresponding **Consolidated Landscape/Index page** (e.g., `wiki/market-landscape.md`, `wiki/regulatory-framework.md`, `wiki/supply-economics.md`) under a new formatted section header: `### [[<slug>]]`.
   - **Traceability Rule**: When writing digests or claims, you **MUST** ensure that every claim is fully traceable:
     - Always include the direct link to the local raw evidence snapshot file inside `raw/snapshots/` (e.g. `[[raw/snapshots/<name>.md]]`).
     - Always include the original, external source URL (e.g. `https://...`).
   - **Graphify Integration**: Always execute `python3 scripts/graphify_wiki.py --wiki-root "$wiki_path"` after an ingestion to automatically map these nested subsections inside the consolidated index files to your `_graph.json` semantic graph index.

   Do this for every slug in `related:` without exception. A digest with 3 related entities means 3 entity updates. Never skip back-propagation.

   After completing all entity updates, run `python3 "$wiki_path/scripts/lint.py"` and then compile the graph with `/llm-wiki:graphify-wiki` to verify no warnings remain.

6a. **Write `summary:` when creating or updating an entity page.**

    Format rule: answer-preview, not bibliographic.
    - ❌ `"Shopify competitor analysis"` — says what the document is
    - ✅ `"Shopify: 70+ reports all plans; ShopifyQL query language; no Z report capability"` — answers "what does Shopify offer for reporting?"

    Pattern by type:
    | Type | Format |
    |---|---|
    | competitor | `[Name]: what [Name] offers for [domain] — [2-3 differentiating facts]` |
    | feature | `[Feature]: [what it solves] — [status], [strategic signal]` |
    | initiative | `[Initiative]: [scope] — [current status], [key risk or unlock]` |
    | jtbd | `[Job]: [the job to be done] — [current gap or pain]` |
    | question | `[Question abbreviated] — [N] sub-Qs open/resolved, [strategic context]` |

    If the entity page already has a `summary:` field, update it only if this ingest adds significant new information. Keep it under one line.

6b. **Offer to extract new `- [ ]` checkboxes into the questions/ folder.**

    After updating entity pages, scan updated pages for new unchecked `- [ ]` items in `## Open questions` sections. If any exist, offer:

    > "I found N new open questions in the updated pages. Would you like me to cluster them into question pages in `questions/`? (y/n)"

    If yes: group checkboxes by strategic theme (2–5 per parent question), create parent question pages in `wiki/questions/` using the question template. Each parent page needs:
    - A strategic title summarizing the theme
    - The relevant `- [ ]` items as sub-questions
    - `related:` pointing to source entity pages
    - `summary:` in answer-preview format

    Graduation rule (when a sub-question should become its own question page):
    1. Answer annotation would exceed one line (~2 sentences + 1 citation)
    2. Answering it revealed new questions needing tracking
    3. Answer updates 3+ entity pages across types
    4. Another page needs to cite this specific answer (needs a wikilink)

6. Append log entry to `<wiki>/wiki/log/<current-quarter>.md`.
7. Update MANIFEST: change `- [ ]` to `- [x]`, replace `pending-ingest` tail with `ingested YYYY-MM-DD → wiki/digests/<slug>.md`.
8. Delete the plan file.
9. **Auto-lint** (always, even in --auto mode):
   ```bash
   python3 "$wiki_path/scripts/lint.py" 2>&1
   ```
   - Exit 0: report "Wiki healthy — N pages, no issues."
   - Exit 1 (warnings): surface the warnings inline. If UNACKNOWLEDGED DIGESTS appear, that means step 5 was incomplete — go back and finish the back-propagation before proceeding.
   - Exit 2 (schema errors): surface errors and halt.

10. **Fan-out to parent wiki** (best-effort, non-blocking):

    Check the registry for this wiki's parent field:
    ```bash
    parent_path=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --get-parent "$wiki_path")
    ```

    If `parent_path` is non-empty:

    a. Locate or create `<parent_path>/wiki/subdomains/<child-domain>.md`

    b. Write stub with frontmatter (use today's date for `last-updated`, `as-of`, and compute `quarter`):
       ```yaml
       ---
       type: synthesis
       status: active
       last-updated: YYYY-MM-DD
       as-of: YYYY-MM-DD
       quarter: YYYY-QN
       okr: []
       confidence: high
       sources: []
       related: []
       source-wiki: <child-abs-path>
       tags: [subdomain, <child-domain>]
       ---
       ```
       Body:
       ```markdown
       ## Last ingested: YYYY-MM-DD

       <top 3 claims from the new digest>
       ```

    c. Run `python3 "${parent_path}/scripts/lint.py"` from the parent wiki. On failure, log the error to stderr but DO NOT block or undo the child ingest. Fan-out is best-effort.

    If no parent registered (empty string): skip silently.

11. Report summary.

### MANIFEST line editing

When flipping an entry from pending to ingested or to blocked, edit the existing line in place. Do NOT append a new line for the same source.

```bash
# Example: flip pending-ingest to ingested
sed -i '' -e "s|- \[ \] \`${filename}\` — \(.*\) — pending-ingest|- [x] \`${filename}\` — \1 — ingested ${today} → wiki/digests/${slug}.md|" "$wiki_path/raw/MANIFEST.md"
```

## Error handling

- FC-7 (PII gate fail): MANIFEST entry flagged `blocked: pii`, user shown flagged spans, offer pre-scrub workflow.
- FC-11 (lint.py not available): surface error, halt.
- FC-12 (MANIFEST missing): if no --auto and no explicit file, respond "No MANIFEST entries yet — run /llm-wiki:research <topic> first."
- FC-13 (CLAUDE_PLUGIN_ROOT not set): abort.
- Partial completion: ingest plan file remains; on next invocation offer to resume from plan file.
