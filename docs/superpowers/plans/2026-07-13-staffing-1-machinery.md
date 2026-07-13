# Guided Staffing — Plan 1 of 3: Machinery

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** All deterministic machinery for guided staffing and layered personas: vendored agency-agents catalog + sync script, `search-candidates`, `validate-persona --project`, layered resolution with `--wiki-root` (+ `layer` field + spawn-time drift notice + ack), `list-copies`, jot `wiki:` provenance.

**Spec:** `docs/superpowers/specs/2026-07-12-guided-staffing-design.md` — its Machinery + decision-table rows are binding; exact values there govern.

**Tech Stack:** Python 3.14 stdlib only; stdlib unittest from `plugin/` (`python3 -m unittest discover -s scripts/tests` — baseline **209 passing, 0 errors**; keep it that way).

## Global Constraints

- Work on `main` of `/Users/pranayagrawal/Documents/GitHub/llm-wiki-poc-main` (two-repo topology: see `CLAUDE.local.md` — run its leak-sweep before every push; do NOT push mid-plan, the controller pushes).
- All existing CLI contracts are frozen: additions must be optional args/new subcommands; every existing test passes unchanged.
- Atomic writes via the existing tmp+rename helpers. No network anywhere except Task 1's maintainer-only sync script.
- Commit trailers as used on this branch (Co-Authored-By + Claude-Session).

---

### Task 1: vendor sync script + vendored catalog + attribution

**Files:** Create `plugin/scripts/sync_agency_agents.py`, `plugin/assets/agency-agents/` (synced content), `plugin/assets/agency-agents/ATTRIBUTION.md`; Test `plugin/scripts/tests/test_vendored_catalog.py`.

**Interfaces:** `sync_agency_agents.py [--ref main] [--dest <dir>]` — maintainer-only: pulls `msitarzewski/agency-agents` via `gh api` (tree + blobs), writes ONLY division-directory persona `.md` files (top-level dirs containing frontmatter agents; skip `examples/`, `scripts/`, `integrations/`, `strategy/`, `.github/`, root files), preserves relative paths, writes `ATTRIBUTION.md` (source repo, ref, sync date, MIT license text, note preserving in-file credits). Idempotent: re-sync replaces the dest dir atomically (build in tmp, swap).

- [ ] Step 1: Write failing tests — `test_catalog_present_and_large` (≥250 `.md` files under `plugin/assets/agency-agents/`, excluding ATTRIBUTION.md), `test_catalog_files_have_parseable_frontmatter` (every file: `^---\n...\n---` block with `name:` and `description:`; collect failures, assert empty list), `test_attribution_present` (file exists, contains "MIT", source repo URL, a sync date line), `test_division_is_directory` (every agent path has ≥1 directory component under the catalog root).
- [ ] Step 2: RED (catalog absent). Step 3: implement the script; RUN it once for real (network, `gh` authenticated) to populate the catalog. Step 4: GREEN + full suite.
- [ ] Step 5: Commit — `feat(staff): vendor agency-agents catalog (+sync script, attribution)`. NOTE: large add (~270 files); one commit, catalog only.

### Task 2: `search-candidates`

**Files:** Modify `plugin/scripts/team_ops.py`; Test `plugin/scripts/tests/test_team_ops_search.py`.

**Interfaces (spec-exact):** `search_candidates(query: str, home: Path|None, division: str|None, source: str) -> list[dict]`; CLI `search-candidates --query "<terms>" [--division D] [--source starter|catalog|references|all]` → ALWAYS the wrapper object `{"results": [{name, source, division, description, path, score}, ...]}` (plus `"suggestions"` on zero matches — see below); the list is ranked.
- Sources: `starter` = `CLAUDE_PLUGIN_ROOT/assets/starter-roster/` (via `Path(__file__)` — works before the roster exists: empty dir → no candidates, never an error); `catalog` = `assets/agency-agents/` (division = first directory component); `references` = `<home>/references/**` (recursive, frontmatter files only; requires home).
- Scoring: case-insensitive term overlap against name+description(+`domain:` tags where present); ties: starter > references > catalog, then name. Zero matches → `{"results": [], "suggestions": [<division names present in catalog>]}`; nonzero → `{"results": [...]}`. Exit 0 always; exit 2 only for unusable `--source references` without a resolvable home.

- [ ] Step 1: failing tests — ranking respects term overlap; the exact tie-break chain (construct a 3-way tie across sources); division filter; per-source filter; zero-match suggestions list non-empty and division-derived; references requires home (exit 2 CLI-level); starter dir absent → empty results not error.
- [ ] Step 2: RED. Step 3: implement (reuse `_frontmatter` helpers; document that catalog frontmatter is non-factory format — only name/description guaranteed). Step 4: GREEN + full suite. Step 5: Commit — `feat(staff): search-candidates across starter/catalog/references pools`.

### Task 3: `validate-persona --project`

**Files:** Modify `plugin/scripts/team_ops.py`; Test: extend `plugin/scripts/tests/test_team_ops_persona.py`.

**Interfaces:** `validate_persona(path, denylist, project: str|None = None)` — when `project` given, that EXACT name is removed from the effective denylist for this call (nothing else changes). CLI `validate-persona <path> [--project NAME]`. The name semantics: registry-entry basename (`Path(entry["path"]).name`) — assert this in a test by building a registry fixture and passing the basename.

- [ ] Step 1: failing tests — own name allowed with `--project`; a DIFFERENT project name still errors in the same call; no `--project` → behavior byte-identical to today (regression: reuse an existing denylist test's fixture and assert equal outputs with `project=None`); CLI flag plumbed.
- [ ] Step 2: RED. Step 3: implement (filter the injected denylist; do not touch `build_denylist`). Step 4: GREEN + full suite. Step 5: Commit — `feat(staff): validate-persona --project (own-name exemption for project copies)`.

### Task 4: layered resolution (`--wiki-root`, `layer`, drift notice, ack)

**Files:** Modify `plugin/scripts/team_ops.py`; Test `plugin/scripts/tests/test_team_ops_layers.py`.

**Interfaces (spec-exact):**
- `resolve_team(home, team_name, wiki_root: Path|None = None)`: when `wiki_root` given, each member resolves `<wiki_root>/personas/<agent>.md` first, else `<home>/agents/<agent>.md`. Every resolved member dict gains `"layer": "project"|"factory"`. CLI: `resolve-team <name> [--wiki-root W]`.
- Solo path parity: whatever function/branch the solo lookup uses gains the same precedence (read the current `/team` SKILL Step 6 + code to find it — if solo resolution happens purely in the SKILL (ls + path check), then the machinery contract is just `resolve-persona <slug> [--wiki-root W]` — ADD that small subcommand returning `{file, layer}` so the skill stops hand-rolling it).
- `assemble_context(...)`: manifest gains `"layer"` derived from the persona path prefix (under `wiki_root/personas/` → project). No signature change needed if the caller passes the resolved path — verify and document.
- **Drift notice:** project-copy frontmatter fields `base-slug:`, `forked:`, `base-hash:`. During `resolve_team`/`resolve-persona` with a project-layer hit: if `base-hash` present AND `<home>/agents/<base-slug>.md` exists AND its current sha256 ≠ recorded → member dict gains `"drift_notice": "base <base-slug> has changed since this copy forked — review the copy or run ack-fork"`. Missing fields → no notice (never an error).
- `ack-fork <copy-path>` CLI: recompute base hash from the copy's `base-slug` (resolved against the registered factory home), rewrite `base-hash:` atomically, print `{"acked": true, "base_hash": ...}`; exit 2 if copy lacks `base-slug` or base file missing.

- [ ] Step 1: failing tests — precedence (copy shadows base; base when no copy; no wiki-root → factory always); `layer` values both paths; validate+resolve END-TO-END for a copy mentioning its own project (the round-2 blocker regression: fixture registry + wiki, copy contains project name, `validate-persona --project` exit 0 AND `resolve-team --wiki-root` resolves it with layer project); drift notice fires on hash mismatch, silent on match/missing-fields; ack-fork rewrites hash (re-resolve → no notice) and is atomic; ack-fork exit 2 cases.
- [ ] Step 2: RED. Step 3: implement. Step 4: GREEN + full suite. Step 5: Commit — `feat(staff): layered persona resolution with drift notice and ack-fork`.

### Task 5: `list-copies` + jot `wiki:` provenance

**Files:** Modify `plugin/scripts/team_ops.py`, `plugin/scripts/session_ops.py`; Tests: extend `test_team_ops_layers.py`, `test_session_ops.py`.

**Interfaces:**
- `list-copies <slug>` CLI (team_ops): scan every registered wiki (registry entries that `is_wiki`) for `<wiki>/personas/*.md` whose `base-slug` == slug → `{"copies": [{wiki, path, forked, drifted: bool|null}]}` (drifted = hash comparison when fields available, else null). Empty list valid. Exit 0 always; never touches file contents.
- `jot_append(..., wiki: str|None = None)` / CLI `--wiki`: additive optional field on written lines, omitted when absent (mirror the `personas` field pattern exactly, incl. backward-compat test).

- [ ] Step 1: failing tests — list-copies finds copies across 2 fixture wikis, skips non-matching base-slug, empty-registry → empty, drifted tri-state; jot wiki field written/omitted/backward-compat.
- [ ] Step 2: RED. Step 3: implement. Step 4: GREEN + full suite (report total). Step 5: Commit — `feat(staff): list-copies routing lookup; jot wiki provenance`.

### Task 6: integration + live read-only checks

**Files:** Test `plugin/scripts/tests/test_staffing_integration.py`.

- [ ] Step 1: subprocess-level tests (explicit env, mirror test_team_ops_integration.py): (a) full layered roundtrip — fixture home+wiki+registry: write base persona → create project copy w/ provenance mentioning the project → `validate-persona --project` 0 → `resolve-team --wiki-root` resolves copy layer=project no notice → edit base → re-resolve shows drift_notice → `ack-fork` → notice gone; (b) `search-candidates` against the REAL vendored catalog (read-only, ships with repo): query "product manager" returns results incl. a catalog hit with division; (c) `list-copies` CLI shape.
- [ ] Step 2: run — failures are real bugs (fix machinery, never weaken). Full suite; report the new total (expect ~240+, 0 errors).
- [ ] Step 3: leak-sweep (`CLAUDE.local.md` command) — vendored catalog is third-party content: sweep must still return LICENSE only; if catalog files trip the sweep terms, report to controller (do not scrub third-party files silently).
- [ ] Step 4: Commit — `test(staff): layered roundtrip, catalog search, list-copies integration`.

## Acceptance

Suite green (0 errors) with the round-2 blocker regression test present; the live layered roundtrip proves a project copy validates, resolves, drifts, and acks end-to-end; leak-sweep clean.

## Out of scope (this plan)

The `/staff` skill and all SKILL.md amendments (Plan 2); starter-roster content (Plan 3 — Task 2's `starter` source must work with the dir absent/empty); any Gemini shim wiring.
