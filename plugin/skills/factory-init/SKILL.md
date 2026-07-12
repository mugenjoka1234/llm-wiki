---
name: factory-init
description: Scaffold or adopt a project for factory-backed product work — wiki, deliverables tree (docs_path), factory home registration, and team selection. Supersedes wiki-init for new projects. Use when the user says "initialize a project", "factory init", "set up this project for the factory", or "adopt this wiki" (adopt → pass --adopt).
---

# factory-init skill

Sets up a project so wiki skills, and later `/team` and session-close, know where
everything lives: the wiki, the deliverables tree (`docs_path`), and the factory home.

Two modes:
- **Scaffold** (default) — new project: create the wiki + docs tree + config.
- **Adopt** (`--adopt`) — existing wiki: add what's missing without touching content.

## Preflight

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded?}"
```

## Step 1 — Resolve the factory home

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" resolve-factory-home
```

Branch on `status`:
- `ok` → note the path; continue.
- `absent` or `missing` → tell the user, show the `hint`, and ask for the
  factory home path (a local directory where their personas and teams live
  across projects). If none exists yet, offer to scaffold one: create an
  `agents/` and `teams/` directory at a path the user chooses. Then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" register-factory-home "<path-user-gave>"
```

Copy the citation standard into the new factory home (skip if it already
exists — never overwrite a home's copy, which may have local edits):

```bash
[ -f "<factory-home>/CITATION_STANDARD.md" ] || \
    cp "${CLAUDE_PLUGIN_ROOT}/assets/CITATION_STANDARD.md" "<factory-home>/CITATION_STANDARD.md"
```

Every persona template's immutable anchor cites `CITATION_STANDARD.md` by
name; this step is what makes that reference resolve to a real file.

If the user declines to register one, continue WITHOUT a factory home — the wiki
still works; warn that `/team` and `/improve` will be unavailable until registered.

## Step 2 — Scaffold the wiki (delegate to wiki-init)

If `--adopt` was passed, skip to the Adopt section below.

Activate the `wiki-init` skill and follow its full workflow (pre-checks,
pause-and-ask, scaffold, Obsidian setup, git init, registration). Return here
when it completes with `<domain>` known.

## Step 3 — Declare docs_path

Ask the user where project deliverables (mockups, briefs, client docs) should
live. Default: a `docs/` directory **next to** the wiki (`<cwd>/docs`). Create
it if needed:

```bash
mkdir -p "<docs-path>"
```

Compute the value to store relative to the wiki root when the docs tree is
inside the same project (e.g. `../docs`); store absolute only if the user picks
somewhere outside the project.

## Step 4 — Write the Project config block

Append to `<domain>/CLAUDE.md` (skip if a `## Project config` section already exists):

```bash
cat >> "<domain>/CLAUDE.md" << 'EOF'

## Project config

```yaml
docs_path: ../docs
docs_ignore:
  - node_modules
```
EOF
```

Adjust `docs_path:` to the value from Step 3. Ask the user for additional
`docs_ignore` entries (directories under the project that must never be treated
as stray markdown — e.g. `mockups`, app source dirs).

Verify:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --get-docs-path "$(pwd)/<domain>"
```

Expected: the absolute docs path prints.

## Step 5 — Offer team selection (record only)

If a factory home resolved in Step 1, list its teams:

```bash
ls "<factory-home>/teams/"*.yaml 2>/dev/null
```

Ask which team (if any) is this project's default. Record it in the Project
config block as an extra line inside the yaml fence:

```yaml
default_team: my-product-team
```

Do NOT spawn anything — team spawning is the `/team` skill (Phase 3). This is
a recorded preference only.

## Step 6 — Confirm

Report to the user: wiki path, docs_path (absolute), factory home status,
default team (or none). Remind: drop any source file into `raw/` anytime with
zero ceremony — ingestion is offered later by the sweep.

## Adopt mode (`--adopt`)

For an existing wiki (e.g. `research-wiki/`). Run from the wiki's parent
directory or pass the wiki path as an argument.

1. **Resolve the wiki.** Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --cwd "$(pwd)"
```

If `source` is `none`, ask the user for the wiki path and verify it with
`--wiki-path <path>`. Abort if it is not a wiki.

2. **Register if unregistered.** If the wiki was found via cwd but is not in the
registry, append a registry entry the same way wiki-init does (path|domain|created|last-used).

3. **Factory home** — same as Step 1 of scaffold mode.

4. **docs_path** — check first:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --get-docs-path "<wiki-root>"
```

If empty, follow Steps 3–4 of scaffold mode to declare and write it. For a wiki
nested in a project repo (wiki root is a subdirectory), the default suggestion
is the repo root's `docs/` (e.g. `../docs` relative to the wiki root). Confirm
the `docs_ignore` list with the user — for a typical web project that is at
least `node_modules`, build output dirs, and any app source trees.

5. **Refresh bundled scripts** (never touches content):

```bash
cp "${CLAUDE_PLUGIN_ROOT}/assets/scripts/lint.py" "<wiki-root>/scripts/lint.py"
cp "${CLAUDE_PLUGIN_ROOT}/assets/scripts/graphify_wiki.py" "<wiki-root>/scripts/graphify_wiki.py"
```

6. **Run lint and report** (do not auto-fix):

```bash
python3 "<wiki-root>/scripts/lint.py" --wiki-root "<wiki-root>" --migration || true
```

Summarize failures for the user — in adopt mode lint findings are a report, not
a gate. `--migration` grandfathers the merge-Phase-2 checks (author
attribution, confidence-vs-sources, the numeric-claim citation gate) into
warnings instead of errors, so adopting a pre-existing wiki doesn't get
buried in new errors it was never written against. Schema errors (missing
required fields, invalid `type`/`status`/`confidence` values) are never
grandfathered — those are exit-2 regardless.

7. **Confirm** — same report as scaffold Step 6, plus the lint summary.
