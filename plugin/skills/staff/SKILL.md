---
name: staff
description: Guide a user through staffing an AI Factory team: context-first interview against a fixed 7-item checklist (confirm-or-correct from context, one question at a time), corpus triage into guidelines/persona-shaping/wiki-ingest offers, doctrine-driven slate composition (decision coverage, tension by design, evidence-style diversity), and layered hiring — base personas to the factory home, client-flavored copies to the project wiki — each validated and diff-gated. Use when the user says "/staff", "staff my team", "help me hire", or "build my agent team".
---

# staff skill

Takes a user from an empty (or partially staffed) factory home to a staffed,
validated team: a working-guidelines file, a durable intake record, and a
`teams/<name>.yaml` ready for `/team <name>`. Candidates are sourced from the
bundled starter roster, the vendored `agency-agents` catalog (~270 personas,
`plugin/assets/agency-agents/`), and the factory home's own `references/**`
pool — never fetched from the network.

The skill embeds a **fixed, versioned intake checklist** (below) and a
**staffing doctrine** the model applies when it composes questions and
proposes a slate — coverage is standard, wording is situational, and every
slate line has to justify itself against the doctrine. `/team recruit`
remains the single-hire shortcut; `/staff` is the guided, whole-team session.
`factory-init` hands off here when a roster is empty.

This skill runs no subagents — Q&A, deterministic `team_ops.py`/`resolve_wiki.py`
calls, and gated file writes only — so it also ships in the Gemini CLI shim
(degradation notes are called out inline at the three steps they affect:
Interview, Resource triage / Adapt & hire, and Assemble).

## Preflight

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded?}"
```

## Step 0 — Resolve factory home, resolve wiki (degrades), detect project state

**Factory home — hard requirement, same rule as `/team`:**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" resolve-factory-home
```

Branch on `status`:
- `ok` → note `factory_home`; continue.
- `missing` or `absent` → **STOP.** Surface the JSON `hint` field to the user
  verbatim and do not continue — `/staff` never proceeds without a factory
  home to write into. Tell the user to run
  `resolve_wiki.py register-factory-home <path>` and retry.

Once resolved, ensure the intake/guidelines directory exists — `factory-init`
only scaffolds `agents/` and `teams/`, so this is not guaranteed yet:

```bash
mkdir -p "<factory-home>/instructions/"
```

Run this `mkdir -p` once, before any write to `instructions/staffing-intake.md`
or `instructions/working-guidelines.md` later in the flow.

**Wiki — soft requirement, degrades gracefully (unlike `/team`):**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --cwd "$(pwd)"
```

- `source: cwd` or `registry-unique` → note `wiki_root`; project-copy offers
  (Step 5) and the wiki-ingest triage destination (Step 3) are available.
- `source: registry-ambiguous` → ask the user which registry entry, the same
  way `research`/`analyze`/`team` do; resolve to a single `wiki_root` before
  continuing, or fall through to the no-wiki case if they decline to pick one.
- `source: none` → **do not STOP.** Staffing proceeds **base-only**: every
  hire lands as a factory-home persona (Step 5's project-copy split is
  simply never offered), and Step 6's team YAML omits `project`. State this
  plainly to the user once, up front: *"No project wiki resolved — staffing
  will proceed base-only; client-flavored personas can't be split into a
  project copy until one resolves."*

**Project-state detection — a NEW project, or expanding THIS project's team?**

A populated factory home does **not** mean this project wants those personas.
The maternity team is not the ai-grid team. Decide by looking for a team that
already belongs to **this project** — not merely for personas that exist
somewhere in the home:

```bash
# A team scoped to THIS project? (project name = wiki_root basename, else cwd basename)
proj="$(basename "${wiki_root:-$(pwd)}")"
ls "<factory-home>/teams/${proj}"*.yaml 2>/dev/null
# Project copies already living in this wiki?
[ -n "$wiki_root" ] && ls "$wiki_root/personas/"*.md 2>/dev/null
```

- **Expansion — this project already has a team** (`teams/<project>*.yaml`
  exists, or this wiki already holds project copies): Step 4's slate opens
  **pre-seeded with THIS PROJECT's current members**, each marked **KEEP** —
  you're adding to a team already chosen for this project. The boundary check
  (doctrine principle 5, Step 4) runs across **old + new together**; the
  collision check (Step 5) still guards slugs — an existing slug is never
  overwritten (propose a variant or a project copy).

- **New project — cold start, even when the factory home is full:** no team
  belongs to this project yet. **Do NOT pre-seed the home roster, and never
  auto-KEEP a home persona.** The home's existing personas are **candidates,
  not the team** — surface them in Step 4 only where they fit the interviewed
  needs (via `search-candidates --source references`), exactly like
  starter/catalog candidates. A home persona whose `domain:` tags or role are
  foreign to this project's domain (Step 1 context + Step 2 intake) is
  **flagged as a likely poor fit and left off the slate** unless the user
  pulls it on deliberately. If the user signals the existing roster does not
  fit, that settles it — compose fresh; never carry a persona the user has
  said does not belong. On a cold start with a resolved wiki, hires default to
  **project copies in the wiki** (Step 5's split), keeping the base home from
  accreting project-specific personas.

## Step 1 — Context fetch (before asking anything)

Three scans, all before the first question of Step 2:

1. **The current project** — `README*`, a `docs/` tree if present, `git log
   --oneline -20`, and any package/app manifest (`package.json`,
   `pyproject.toml`, etc.) that names the product and its stack.
2. **The project wiki**, if `wiki_root` resolved in Step 0 — `Read`
   `wiki/overview.md` (theses, current state), any `wiki/questions/*.md`
   (open questions), and the entity catalog (index) for what's already
   documented about the product and its users.
3. **The factory home** — existing personas (`agents/*.md`, roles +
   `domain:` tags), existing teams (`teams/*.yaml`), and any prior
   `instructions/staffing-intake.md` sections (a re-staffing run should not
   re-derive answers a previous session already recorded).

Draft a candidate answer to each of the seven checklist items from what these
three scans turned up, before moving to Step 2. An item with no supporting
context at all is simply left undrafted — that is what routes it to the
open-ended branch below.

## Step 2 — Interview: the standard intake checklist (v1)

The checklist below is the **fixed coverage contract** — copied verbatim from
the spec. It does not change between runs; only the *wording* of each
question and the *order of resolution* are situational, composed fresh each
time from Step 1's context.

1. What are you building? One paragraph — and what stage is it at (idea / prototype / live)?
2. Who is it for, and what is the hardest part of serving them well?
3. What decisions are coming in the next month that you want a team's help with?
4. What expertise do you bring yourself — and what do you know is missing?
5. What does a great outcome look like 90 days from now?
6. Do you have documents to share — strategy docs, process norms, research? (optional; paths/folders — triggers the triage step)
7. Team size: focused (3–5 members) or full bench (up to 9, extras on-demand)?

**Context-first resolution ladder** — resolve each item in this order of
preference, one item per message, always:

1. **Inferred and confirmed** — when Step 1 drafted a specific answer, present
   it as a confirm-or-correct question, e.g. *"From your README and wiki
   theses, you're building <X> at prototype stage, for <audience> — right?"*
2. **Asked narrowly** — when context gave a partial picture, ask only for the
   missing part.
3. **Asked open-ended** — only when nothing was inferable for that item.

Multiple-choice is preferred wherever the answer space is enumerable (stage,
team size); free text otherwise. **On Gemini:** there is no structured
option-picker widget — render the choices as a lettered plain-text list in
the message body (e.g. `(a) idea  (b) prototype  (c) live`) and accept the
user's reply in kind; the one-question-at-a-time and context-first rules are
unchanged.

The checklist fixes **coverage**, not wording: an item Step 1 already
answered in full and Step 2 confirmed once is **never re-asked cold** — that
is the whole point of scanning context first.

Write the final answers to `<factory-home>/instructions/staffing-intake.md`
(create-or-update; one section per questionnaire version, headed by today's
date and the version, e.g. `## Intake v1 — 2026-07-13`). Record, per item,
whether it was **inferred** (and from what) or **user-stated** — this
provenance is what lets a later re-staffing or `/improve` session tell drafted
answers from ones the user actually said. This file is a plain create-or-update
write, not gated behind Step 4's approval — it is the durable record of the
interview itself, disclosed to the user as it's written (state the path once
it's saved).

## Step 3 — Resource triage (only if Q6 named documents)

If Q6 pointed at real paths/folders, `Read` them, then present a
**three-destination table** — approval required **before any write**, and
**never auto-ingest**:

| Destination | What lands here | Where |
|---|---|---|
| Process norms | style/workflow rules the team should follow | `<factory-home>/instructions/working-guidelines.md` |
| Domain expertise | shapes the persona drafts Step 5 writes | folded into Step 5's Identity/Expertise sections — not written to a separate file itself |
| Project facts | product/company-specific facts, currently undocumented | **offered** to the project wiki via `/llm-wiki:wiki-ingest` — never run automatically |

Show the proposed triage (which passage goes to which destination) and get
one approval before writing `working-guidelines.md` or drafting anything from
the domain-expertise passages. A declined row is simply dropped — note it in
Step 7's bookkeeping as declined, and move on.

**On Gemini:** there is no native diff view for the `working-guidelines.md`
write — print the full proposed file content (or the appended section, on an
update) inline as a unified diff in the message body and get the same
approval before writing.

## Step 4 — Composition proposal

### The staffing doctrine (verbatim — the basis for every slate line)

1. **Cover the decision surface, not the org chart.** A team is good if every hard decision the user faces (intake item 3) has at least one lens that will interrogate it. Staff to decisions, not to job titles.
2. **Complement the human.** The user's own expertise (item 4) is already on the team — never duplicate it; staff the declared and inferred gaps.
3. **Tension by design.** Include at least one member whose job is to say no (reality-checker / skeptic archetype). A slate where every lens would agree is an echo chamber — split verdicts are a feature (they surface the real cruxes to the user, who holds the tie-break).
4. **A domain conscience.** One member owns keeping the product honest about what its domain actually allows — regulations, real-world constraints, how the served population actually behaves (items 1–2). In field use this archetype changed more decisions than any other.
5. **Sharp boundaries, but defer-with-a-view.** Every persona declares deep expertise, working knowledge, and explicit "defers on" — overlapping ownership produces mush. Composition must check that no two members claim the same deep lane and that every "defers on" points at someone actually on the team (or at the user). Deferring is never silence: a member who defers still states their recommendation from their own lens ("I defer to <owner> on this; from where I sit it looks like <view>, because <reason>") — the owning lens decides, but the panel never loses a viewpoint to a boundary, and stalemates resolve through the owner rather than through omission. Persona adaptation (flow step 5) bakes this into each hire's instructions.
6. **Small active bench, on-demand extras.** Active bench 3–5 members per session (full roster up to 9, the rest `invocation: on-demand` — matching intake item 7's focused/full-bench choice); specialists (copy QA, privacy, visual) join as `invocation: on-demand`. Context budgets are real — every member must earn their dispatch: if you cannot name a decision a member would change, cut them.
7. **Diversity of evidence style.** Mix at least two of: numbers-first (economics/metrics lens), user-first (behavior/experience lens), and precedent-first (what happened when others tried this). Single-style teams miss whole failure classes. Composition-table requirement (a skill instruction, not code enforcement): the table carries an evidence-style column; a single-style slate must be flagged to the user with a suggested swap before proceeding.

The intake checklist maps onto the doctrine (1–2 → domain conscience; 3 →
decision coverage; 4 → complement; 7 → bench size) — this is what grounds the
model's questions and the slate it proposes; it knows *why* it is asking.

### Finding candidates

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" search-candidates --query "<terms>" [--division "<division>"] [--source starter|catalog|references|all]
```

Returns `{"results": [{name, source, division, description, path, score}, ...]}`,
plus `"suggestions": [<catalog division names>]` when `results` is empty — use
the suggestions to widen the query or division rather than fabricating a
candidate. Search terms shorter than 3 characters are dropped (stopword
floor) — keep queries to substantive words. Query words are matched
independently (OR), and `score` is just the count of matched words, so a
multi-word query where no candidate matches two or more words returns a
flat same-`score` list sorted by name — signal, not ranking. When results
look undifferentiated, re-query with a single distinctive word rather than
a natural-language phrase. `--source starter` searches
`plugin/assets/starter-roster/`, which **may not exist yet** (Plan 3 ships
it separately) — an empty/absent starter pool is not an error; when it
contributes nothing, say so plainly (*"the starter pool ships in a future
release"*) and lean on `--source catalog` (the vendored ~270-persona
`agency-agents` set) and `--source references` (the factory home's own
curated pool, when one exists — requires the factory home resolved in Step 0
and is otherwise silently empty). Ties break starter > references > catalog,
so a name overlapping the user's own curated references always outranks the
generic catalog.

### The slate table

Propose a slate as a table with these columns:

| Role | Source | Doctrine principle | Intake answer | Evidence style | Active / on-demand |
|---|---|---|---|---|---|

- **Source** — `starter` / `catalog` / `references`, plus the candidate's
  `path` from `search-candidates`.
- **Doctrine principle** — which of the 7 principles above this hire
  satisfies (name it, e.g. "3 — tension by design").
- **Intake answer** — which checklist item this hire ties back to.
- **Evidence style** — numbers-first / user-first / precedent-first.
- **Active / on-demand** — per doctrine 6 and intake item 7's team-size answer.

**Boundary check**, before showing the table to the user: no two members
(old + new, in expansion mode) claim the same deep lane; every "defers on"
target is either on the slate or is the user themself. **Single-style
check**: if the Evidence-style column shows only one style across the whole
slate, flag it explicitly and propose a swap before asking for approval.

The user edits the slate (add, remove, swap roles) before anything is
fetched or written — this table is the gate for Step 5, not a preview of a
done deal.

## Step 5 — Source & adapt, then hire

For each approved slate row:

1. **Copy from the local source** named in the slate (`starter`, `catalog`,
   or `references` — the `path` from `search-candidates`). Vendored/reference
   files are **not** in factory format (no citation anchor, no fenced
   Immutable Anchors, different frontmatter shape entirely) — treat every
   hire as a mandatory transformation, never a touch-up.

2. **Collision check** — before drafting anything, confirm the slug is free
   in whichever layer(s) this hire could land in:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" resolve-persona "<slug>" [--wiki-root "<wiki-root>"]
   ```

   Exit 0 (a hit) means the slug is **already taken** — branch on the
   returned JSON's **`layer`** field to tell base from copy:
   - `"layer": "factory"` → the collision is with the **base** persona at
     `<factory-home>/agents/<slug>.md` — propose a variant slug (e.g.
     `<slug>-2`) or, when this hire carries client flavor and a wiki
     resolved, a project-level copy of that existing base instead of a new
     base.
   - `"layer": "project"` → an existing **project copy** already occupies
     the slug at `<wiki-root>/personas/<slug>.md` — offer to update that
     copy (shown as a diff, same gate as any other write this run) or
     rename the new hire; never overwrite it silently.

   A project copy at the same slug in a *different* wiki is not a collision
   here — `resolve-persona` checks only the `--wiki-root` you pass plus the
   factory home. Exit 2 (given Step 0 already confirmed the factory home
   resolves) means the slug is free in every layer checked — proceed.

3. **Transform into factory format**, using
   `${CLAUDE_PLUGIN_ROOT}/assets/factory-templates/persona.md` as the shape:
   - Citation anchor and the fenced `<!-- IMMUTABLE:BEGIN -->` /
     `<!-- IMMUTABLE:END -->` Immutable Anchors block come from the
     **template**, verbatim — the source file has neither.
   - `description:` ≤ 600 characters, "Use when…" form (same budget and form
     as `/team`'s lazy-upgrade and recruit drafts).
   - `domain:` — 2-5 lowercase tags drawn from the intake answers (items 1-2
     especially), not copied from the source's own tagging (the vendored
     catalog doesn't carry `domain:` at all).
   - Identity / Expertise / "Champions" / "Pushes back on" sections informed
     by the source material plus any triaged domain-expertise passages from
     Step 3.
   - **Bake defer-with-a-view into `## Mutable Instructions`** (doctrine 5):
     add an explicit instruction naming who this member defers to and on
     what, plus the one-line rule — *"When deferring to `<owner>` on
     `<domain>`, still state your own recommendation and the reason before
     deferring — never go silent on your lens just because it's someone
     else's deep lane."*

4. **Validate before saving:**

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" validate-persona "<scratch-path>" [--project "<registry-basename>"]
   ```

   For a **base** hire, omit `--project` — the factory-home denylist is
   absolute, no exceptions. For a **project-copy** hire (Step 5's split,
   below), pass `--project` with the resolved wiki path's own **basename**
   (`Path(wiki_root).name`) exactly — this is the registry-entry basename
   `validate-persona` derives internally (`Path(entry["path"]).name`), **not**
   the wiki's `domain:` label, and the match is case-sensitive. Only a
   persona that validates clean (`ok: true`) proceeds to step 5 below — never
   save one that doesn't; show the `errors` and re-draft.

5. **Base-vs-project-copy split offer.** If Step 3 or the interview surfaced
   client-flavored content for this hire (anything naming the user's own
   product/company), and a wiki resolved in Step 0, offer the split
   explicitly: generic material stays in the **base** persona; the
   client-flavored material becomes a **project copy**. If no wiki resolved,
   there is no copy destination — say so and keep everything in the base
   draft (Step 0's base-only degradation).

6. **Human gate, then atomic write** — show the full drafted file as a diff
   (new file, so the whole draft is "the diff") before writing anywhere real.
   On Gemini, print the unified diff inline in the message body — same
   content, no native diff viewer.

   - **Base hires** → `<factory-home>/agents/<slug>.md`, refuse-to-overwrite
     (same rule as `/team recruit`'s Step 3 — `test -f` first, stop and ask
     for a different slug if it exists), atomic write:
     ```bash
     cp "<scratch-path>" "<factory-home>/agents/<slug>.md.tmp" && mv "<factory-home>/agents/<slug>.md.tmp" "<factory-home>/agents/<slug>.md"
     ```
   - **Project copies** → `<wiki-root>/personas/<slug>.md`, same
     refuse-to-overwrite + atomic-write discipline, plus provenance
     frontmatter:
     ```yaml
     base-slug: <slug>
     forked: <YYYY-MM-DD>
     base-hash: <sha256 of the base file's bytes at fork time>
     ```
     **Convention, quoted exactly because a downstream tool depends on it:**
     `base-slug:`, `forked:`, and `base-hash:` must each be a single physical
     frontmatter line with a plain (or plainly quoted) scalar value — no YAML
     block-scalar folding (`>-`/`|`), no multi-line continuation. `ack-fork`'s
     surgical rewrite matches the `base-hash:` value on its one line; a
     folded or multi-line value would make that rewrite silently no-op.
     Compute the hash with:
     ```bash
     python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "<factory-home>/agents/<slug>.md"
     ```
     Validate this copy with `--project <registry-basename>` per step 4
     above before writing it.

## Step 6 — Assemble

Write `<factory-home>/teams/<name>.yaml` from
`${CLAUDE_PLUGIN_ROOT}/assets/factory-templates/team.yaml`, fields sourced
explicitly:

- `id` / `name` — from the team name (ask, if not already settled during the
  interview).
- `purpose` — from intake item 1.
- `project` — the resolved `wiki_root` from Step 0; **omit entirely** when
  staffing proceeded base-only (no wiki resolved).
- `members` — one entry per slate row from Step 4/5: `agent` (slug), `role`
  (the hat on this team), `model`, `effort`, `invocation` (`on-demand` for
  bench members beyond the active set).
- `notes` — an additional top-level scalar (the parser tolerates unknown
  scalars) linking the two files this run produced: the working-guidelines
  path (Step 3, if written) and the staffing-intake path (Step 2). e.g.
  `notes: "guidelines: instructions/working-guidelines.md; intake:
  instructions/staffing-intake.md"`.

Show the assembled YAML as a diff before writing (same gate as every other
factory-home write this run); atomic write.

**Closing handoff:**
- **Claude Code:** show the roster table (name, role, layer, active/on-demand)
  and close with *"run `/team <name>` to hold your first session."*
- **On Gemini:** the shim has no `/team` dispatch path — close instead with
  *"open Claude Code to run `/team <name>` for your first session."*

## Step 7 — Bookkeeping

End the run's output with:

- **Hires made**, grouped by layer — factory-home base hires and project
  copies listed separately, each with slug and role.
- **Guidelines / intake paths** — `instructions/working-guidelines.md` (if
  written) and `instructions/staffing-intake.md`, both with their absolute
  paths.
- **Triage decisions** — which Step 3 rows were approved into which
  destination, and which were declined.
- **Anything declined** — dropped slate rows, declined triage rows, declined
  wiki-ingest offers — named plainly, not silently omitted.
