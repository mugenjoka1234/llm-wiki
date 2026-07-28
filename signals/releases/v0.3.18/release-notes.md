# Release notes — llm-wiki v0.3.18

**Window:** `v0.3.0` → `ffe18690` · 2026-07-13 → 2026-07-27
**Changes:** 11 (22 commits; 2 low-signal commits excluded)

> Note: llm-wiki is a CLI/markdown plugin with no analytics instrumentation, so there are no tracked events in this release — `events_touched` is empty throughout by nature, not tracking-plan drift.

---

## For the team

**chg-1 · Wiki reframed as institutional memory** — *feature* — `df70b731`
Templates now present the wiki as a project's decision/process/external memory, not a generic doc dump. Surface: wiki templates.

**chg-2 · Scaffolding UX overhaul** — *feature* — `ff764066`, `a4a562fa`, `1919f677`
The wiki now scaffolds into a clean `<project>-wiki/` container (no more nested `wiki/wiki/`), opens directly in Obsidian, and offers opt-in ingest of existing docs. Surfaces: wiki-init scaffold, factory-init, Obsidian setup.
> ⚠️ needs human review: mixes feat (new container UX) and fix (removing `wiki/wiki` nesting, container-path refs) commits; classified `feature` by net user impact.

**chg-3 · Inline citation-anchor offer in /team** — *feature* — `797965a1`
`/team` offers to add the standard citation anchor inline instead of hard-refusing to spawn a persona that lacks one. Surface: /team recruit.

**chg-4 · /staff cold-start vs. expand posture** — *fix* — `dd17fa23`
`/staff` distinguishes a new-project cold start from expanding an existing project's team, so it no longer treats the factory-home roster as the team. Surface: /staff.

**chg-5 · Obsidian first-open vault registration** — *fix* — `1813038d`
Scaffolding registers the vault in `obsidian.json` before opening it, fixing the first-open "Vault not found" error. Surface: wiki-init Obsidian setup.

**chg-6 · /team front-door fork** — *feature* — `c1b9f060`
`/team` presents an explicit fork (run existing team / build a whole team via `/staff` / hire one individual / custom) instead of funneling everything into a single-persona recruit. Surface: /team routing.

**chg-7 · /staff slate legibility** — *fix* — `322eda64`
`/staff` profiles every proposed member before asking for approval, so the user sees who each hire is rather than a bare list of names. Surface: /staff slate.

**chg-8 · Team-reporting overhaul** — *feature* — `ec7b8115`, `3ff2c846`, `4b178323`, `adfb3364`, `b6f1aaee`
Personas report on a fixed five-part contract; the orchestrator synthesizes answer-first and concrete (a recommendation with specifics, not a wall of takes); a schema-enforced `validate-report` gate and per-question effort scaling right-size and validate each run. Surfaces: /team reporting, /team synthesis, `team_ops.py` (validate-report).
> ⚠️ needs human review: the feature iterated across five releases (v0.3.5–v0.3.10), including a `bottom_line` budget calibration fix (v0.3.8) folded in as part of the same feature.

**chg-9 · Preflight uses the resolved plugin path** — *fix* — `dd45b4da`
Skill preflight checks the resolved plugin path instead of a phantom `CLAUDE_PLUGIN_ROOT` env var (it's a text placeholder, not a shell variable), fixing a spurious "not set" hard-fail across all 17 skills. Surface: all skills (preflight).

**chg-10 · Skill-chaining audit** — *fix* — `fd42b632`, `d77dbf1d`, `eb43bdc5`, `1262de56`, `44d32921`, `30732a94`
Every skill that files into the wiki now uses one uniform `--auto --wiki` ingest contract; `analyze` and `critique` now compound (they were writing orphaned digests); the wiki router covers all 17 skills; wiki-lint's Obsidian setup registers the vault. Surfaces: research, analyze, critique, wiki-ingest, factory-init, wiki-init, staff, session-close, wiki router, wiki-lint.
> ⚠️ needs human review: surfaces derived largely from the detailed commit subjects plus partial diffs; several `SKILL.md` diffs exceeded the collector's diff budget (12 skipped paths across the range), so per-file evidence is incomplete.

**chg-11 · Corrected the plugin listing** — *fix* — `ffe18690`
README and marketplace listing now say **17 skills** (was mislabeled 16) and document `/staff` in the factory subsystem. Surfaces: README, marketplace listing.
> ⚠️ needs human review: docs-only, no runtime behavior change (the type enum has no "docs" value; classified `fix` as the closest match).

**Excluded as low-signal:** `2771846a` (chore: tighten synthesize/improve descriptions), `ea964b51` (chore: bump 0.3.1).

---

## For stakeholders

This release makes llm-wiki noticeably smoother to adopt and more trustworthy to run.

**Getting started just works.** Setting up a project now produces a clean, well-named wiki that opens straight into Obsidian without the old "Vault not found" stumble, and offers to pull in your existing docs — so the first five minutes feel finished rather than fiddly (chg-1, chg-2, chg-5).

**The agent team is easier to build and its output is actually usable.** You now get a clear choice up front — run a team, build a whole one, or hire one specialist — and when you staff a team you see who each proposed member is before approving them (chg-3, chg-4, chg-6, chg-7). The biggest change: when a team reviews your work, it now leads with a concrete recommendation and specifics instead of a long wall of individual opinions, and each contributor's report is validated for completeness before you see it (chg-8).

**It's more reliable under the hood.** A class of setup failures is gone (chg-9), and a full audit means the skills now hand off to each other consistently — anything you file into the wiki, whether from research, analysis, or a critique, now enriches your existing pages the same way instead of being dropped in as an orphan (chg-10). The plugin's own listing was also corrected to reflect all 17 skills (chg-11).

> ⚠️ needs human review: a few of the technical entries above (chg-2, chg-8, chg-10, chg-11) carry classification/evidence caveats — see the "For the team" section before publishing externally.
