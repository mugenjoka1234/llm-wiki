# Guided Staffing — Plan 2 of 3: Skills

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> Prose deliverables (SKILL.md files) — review them as operator runbooks: could a fresh session follow each end-to-end?

**Goal:** The `/staff` skill (context-first interview → triage → doctrine-grounded composition → adaptation → gates → team assembly) plus the layered-model amendments to `/team`, `/improve`, `factory-init`, and `session-close`.

**Spec:** `docs/superpowers/specs/2026-07-12-guided-staffing-design.md` — the intake checklist, doctrine (7 principles incl. defer-with-a-view), flow steps 1-7, layer-aware improvement, and Gemini degradation sections are binding text sources; quote their fixed elements verbatim.

**Depends on:** Plan 1 merged (all CLI contracts it created). Baseline suite from Plan 1 (0 errors) must stay green — this plan changes no python.

## Global Constraints

- Work on `main`; leak-sweep before handing back; controller pushes.
- Every CLI quoted in skill text must match the real argparse (implementers read the code first; reviewers verify — this rule caught real bugs in every prior phase).
- House style: existing skills under `plugin/skills/` (numbered workflow, exact commands, decision points as bullets). Frontmatter descriptions ≤600 chars, "Use when…" form, named trigger phrases.
- Commit trailers as on this branch.

---

### Task 1: `/staff` SKILL.md + command toml + README

**Files:** Create `plugin/skills/staff/SKILL.md`, `plugin/commands/llm-wiki/staff.toml` (mirror team.toml's shape); Modify `plugin/README.md` (skills table + one section), `plugin/GEMINI.md` (add staff to the shim list with the spec's degradation notes).

SKILL.md sections (each encodes its spec rule — the spec text governs):
0. **Preflight** — factory home STOP rule (verbatim hint surfacing like /team); `mkdir -p <home>/instructions/`; wiki resolution (staffing wants a project context but must degrade gracefully: no wiki resolvable → staffing proceeds base-only, project-copy offers disabled, say so); expansion-mode detection (existing roster → slate pre-seeded KEEP, dedupe vs existing slugs, variant-name or project-copy proposals instead of overwrites).
1. **Context fetch** — the spec's three scans (project files, wiki overview/questions/catalog, factory home incl. prior intake) BEFORE any question.
2. **Interview** — the 7 fixed checklist items verbatim as the coverage contract; the context-first resolution ladder (infer+confirm → narrow → open) with the "coverage fixed, wording model-composed, answered items never re-asked cold" rule; one item per message, multiple-choice preferred; intake written to `<home>/instructions/staffing-intake.md` with inferred-vs-stated provenance per item.
3. **Resource triage** — three-destination table (guidelines / persona-shaping / wiki-ingest offer), approval before ANY write; never auto-ingest.
4. **Composition** — doctrine section embedded VERBATIM from the spec (all 7 principles incl. defer-with-a-view and the evidence-style composition-table requirement); slate table columns: role, source (starter/catalog/references via `search-candidates`), doctrine principle satisfied, intake answer tied to, evidence style, active vs on-demand; boundary check (no duplicate deep lanes; defers-on targets exist on-team or = the user); single-style slates flagged with a suggested swap; user edits before anything is written.
5. **Adapt & hire** — per selected candidate: copy from local source, MANDATORY transformation to factory format (citation anchor + fenced immutables + ≤600 "Use when…" description + `domain:` from intake + defer-with-a-view baked into instructions); base hires → `<home>/agents/<slug>.md` (refuse-overwrite, atomic, diff-gated — recruit's rules verbatim); client-flavored content → the base-vs-project-copy split offer; project copies → `<wiki-root>/personas/<slug>.md` with `base-slug`/`forked`/`base-hash` provenance, validated with `--project <registry-basename>`.
6. **Assemble** — team YAML per template with the spec's field sourcing; `notes:` links guidelines + intake; closing handoff to `/team <name>` (on Gemini: the spec's degradation closing instead).
7. **Bookkeeping** — hires made (by layer), guidelines/intake paths, triage decisions, anything declined.

- [ ] Step 1: write SKILL.md (read spec + all four existing factory SKILLs first). Step 2: staff.toml + README + GEMINI.md. Step 3: description ≤600 verified; suite run (no code changed). Step 4: Commit — `feat(staff): /staff skill — context-first interview, doctrine composition, layered hiring`.

### Task 2: `/team` amendments (layered spawning)

**Files:** Modify `plugin/skills/team/SKILL.md`, `plugin/README.md` (one line if invocation forms change — they don't; verify).

Amendments (surgical — read the file first; do not restructure):
- Step 1: resolve-team gains `--wiki-root "<wiki-root>"` (the Preflight-resolved wiki); missing-member handling unchanged.
- Step 2: members with `layer: project` are validated with `--project <registry-basename>`; factory-layer members unchanged (absolute rule). The "exactly [missing description]" lazy-upgrade branch applies to BOTH layers (upgrade-persona works on any path).
- Step 3: dispatch notes each member's layer; `drift_notice` on any member is surfaced to the user in the panel roster (not a stop), with the ack-fork command quoted.
- Step 6 (solo): resolution routes through `resolve-persona <slug> --wiki-root ...` (Plan 1's subcommand) instead of the hand-rolled path check; same --project validation rule.
- Recruit Step 7 source list: factory-home `references/` first, vendored catalog (`$CLAUDE_PLUGIN_ROOT/assets/agency-agents/`) second — matching search-candidates' documented tie-break; pointer to `/staff` for whole-team hiring.

- [ ] Steps: read → amend → verify every quoted CLI against real argparse → suite run → Commit `feat(staff): /team layered spawning — --wiki-root, --project validation, drift surfacing, solo parity`.

### Task 3: `/improve` amendments (layer-aware routing)

**Files:** Modify `plugin/skills/improve/SKILL.md`.

Amendments per the spec's layer-aware bullet (surgical):
- Step 2 (read jot): note the optional `wiki:` field; group observations by persona AND wiki.
- Step 3 (propose): before drafting, run `list-copies <slug>`; every proposal carries the routing question — base / named project copy / both — defaulting from jot wiki provenance ("this feedback came from sessions where the <wiki> copy ran"). "Both" = two separately drafted diffs (never one patch twice — the copy may have diverged).
- Step 5 (apply): per-file chain unchanged (scratch → anchors-unchanged → validate → atomic → commit) with two additions: project copies validate with `--project <registry-basename>`, and commit destination follows the file — base → factory-home repo; project copy → its project's repo (`git -C <project-root>`; if the project root isn't a git repo, apply the edit but tell the user it's uncommitted). After a base-only edit where copies exist: remind the user the named copies did NOT receive it (they'll see the drift notice at next spawn).
- Bookkeeping: tallies split by layer.

- [ ] Steps: read → amend → verify CLIs → suite run → Commit `feat(staff): /improve layer-aware routing — explicit base/copy/both, two-repo commits`.

### Task 4: `factory-init` + `session-close` touches

**Files:** Modify `plugin/skills/factory-init/SKILL.md` (empty-roster handoff: after home registration, if `agents/` has no personas → offer `/staff` with one sentence on what it does), `plugin/skills/session-close/SKILL.md` (Step 5 jot calls pass `--wiki "<wiki-root-basename or path per jot field spec>"` — read Plan 1's implementation for the exact value shape and quote it), `plugin/assets/factory-templates/team.yaml` (documented optional `notes:` line), `plugin/assets/factory-templates/persona.md` (comment noting project copies add `base-slug`/`forked`/`base-hash`).

- [ ] Steps: read all four → surgical edits → template tests still green (test_factory_templates) → suite run → Commit `feat(staff): factory-init handoff, session-close jot wiki, template notes`.

### Task 5: blind-adopter acceptance

- [ ] Step 1: dispatch a fresh blind agent (zero project context, sandboxed CLAUDE_PLUGIN_DATA + scratch workspace, plugin read-only): "staff a team for an invented product following only shipped docs" — must produce: intake file, ≥3 hires validating clean, a team YAML that `resolve-team` resolves, and (with a fixture wiki) one project copy that resolves layer=project. Friction log required.
- [ ] Step 2: fix content (skills/docs) for any BLOCKER; re-verify with the same agent. Record evidence in `.superpowers/` scratch.
- [ ] Step 3: leak-sweep; Commit any fixes — `fix(staff): blind-adopter findings`.

## Acceptance

Blind adopter completes the staffing journey from shipped docs alone; all quoted CLIs verified real; suite green throughout; leak-sweep clean.

## Out of scope

Starter-roster content (Plan 3 — until it lands, `/staff` slates draw from catalog/references and say the starter roster is "not yet shipped" if its dir is empty); any python changes (bugs found here → fix in a Plan-1-style TDD commit, flagged to controller).
