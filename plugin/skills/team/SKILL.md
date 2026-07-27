---
name: team
description: Spawn a factory team (or a single persona) with budgeted wiki context, honest partial-panel disclosure, and self-authored attribution; also recruits new personas into the factory home's roster. Claude-only — requires a registered factory home; STOPs with a remediation hint if none is registered. Use when the user says "/team <name>", "run the <team> team on X", "<persona-name>, what do you think about X" (solo), or "recruit a <role> for <task>".
---

# team skill

Orchestrates AI Factory personas against the current project's wiki: resolves a
team (or a single persona) from the registered factory home, lazily upgrades
any persona file that's missing required frontmatter, assembles a budgeted
per-persona context manifest, spawns each member via the Agent tool with an
identical attribution contract, and synthesizes their outputs — never hiding a
partial panel as a complete one.

The machinery (team-YAML parsing, persona validation/upgrade, context
budgeting) lives in `scripts/team_ops.py`; this skill is the judgment layer on
top of it — drafting descriptions, composing dispatch prompts, and
synthesizing.

Three invocation forms:
- `/team <name>` — spawn the named team (`teams/<name>.yaml` in the factory home).
- `/team solo <persona> <question>` (or natural language: `"<persona-name>, what
  do you think about X?"`) — spawn a single persona directly.
- `/team recruit <role> for <task>` — draft and save a new persona to the roster.

## Preflight

```bash
[ -d "${CLAUDE_PLUGIN_ROOT}/scripts" ] || { echo "llm-wiki plugin scripts not found (is the plugin installed and loaded?)"; exit 1; }
```

Resolve the project wiki the same way every other skill does — it supplies
`--wiki-root` for context assembly later:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --cwd "$(pwd)"
```

If `source` is `none` or ambiguous, resolve it the same way `research`/`analyze`
do before continuing (offer to scaffold, or ask which registry entry). `/team`
never proceeds against an unresolved wiki.

## Step 1 — Resolve the factory home and the team

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" resolve-factory-home
```

Branch on `status`:
- `ok` → note `factory_home`; continue.
- `missing` or `absent` → **STOP.** Surface the JSON `hint` field to the user
  verbatim and do not continue. `/team` never degrades to running without a
  factory home — that is the spec's rule for factory-home-dependent skills.
  Tell the user to run `resolve_wiki.py register-factory-home <path>` and
  retry.

### Route the request before any single-persona work

`/team` has an open front door, and it is easy to funnel the user into a
single hire when they wanted a whole team. A **bare `/team`**, a `<name>`
that matches no `teams/*.yaml`, or a natural-language "help me staff / recruit
/ build a team for this project" is **NOT** a single-hire request. In these
cases do **not** drop into Step 7's single-persona draft, and do **not** ask a
question scoped to one named persona — that hides the multi-member path, which
is exactly the trap to avoid. Instead, see what already exists and present the
fork explicitly:

```bash
ls "<factory-home>/teams/"*.yaml 2>/dev/null   # what teams already exist
```

Offer these choices (as an explicit pick, one message) and let the user
decide — never pre-select one for them:

- **Run an existing team** — offered only when the list above is non-empty;
  show the team names, and on a pick continue to team resolution below.
- **Build a whole team (guided)** — the right door for a new project, or any
  time the user wants more than one member. Hand off to the `/staff` skill: it
  runs the context-first interview (including the focused-3–5 / full-bench-
  up-to-9 team-size question) and proposes a multi-member slate the user
  edits. State this plainly — the user must never have to already know
  `/staff` exists to find the multi-member path.
- **Hire one individual** — a single role for a single task → Step 7 (Recruit).
- **Something else / not sure** — ask one open question about what they want
  the team to do, then re-route into one of the above.

Skip the fork only when the invocation unambiguously names an existing team
(`/team <name>` with a matching `teams/<name>.yaml`), a single persona
(`/team solo …` or a name addressed directly), or a single role+task
(`/team recruit …`) — then go straight to the matching step. When in doubt,
show the fork; it is never wrong to ask which of these the user meant.

For the `/team <name>` form, resolve the team's roster, passing the
Preflight-resolved wiki root so any project-layer persona copy supersedes its
factory-home base for this run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" resolve-team "<name>" --wiki-root "<wiki-root>"
```

This call re-checks the factory home itself and will also exit 2 with a JSON
`hint` if it has gone missing between the two calls above — treat that exit
the same way (STOP, surface the hint). On success it returns
`{"team": {...}, "members": [...resolved, each with "file", "layer"
("project" or "factory")...], "missing": [...]}`. A project-layer member also
carries `"project"` (the wiki-root's basename, verbatim — hand it straight
back as `validate-persona --project` in Step 2, never re-derive it yourself)
and, when its base has drifted since the copy forked, `"drift_notice"`; a
project copy that exists but can't be read instead carries `"layer_warning"`
and that one member degrades to its factory-layer base. Members in `missing`
(persona file absent from BOTH layers) are added directly to the panel
roster (Step 4) with reason "persona file not found" — they are never
retried or drafted on the fly; that is what `/team recruit` is for.

Members whose team-YAML entry has `invocation` starting with `on-demand` are
**not spawned by default** — set them aside and list them to the user at the
end as available (see Step 3).

## Step 1.5 — Right-size the panel to the question (effort scaling)

A team run spawns one subagent per member and costs on the order of **15× a
single response**; models also tend to over-spend effort when left to judge it
themselves. So before lazy-upgrading and spawning, match the panel to the
question rather than reflexively spawning the whole active roster.

Read the question against each active member's lane — their `role`, `domain:`
tags, and the "defers on" boundaries in their persona — and pick the smallest
panel that still covers the question's real decision surface:

- **One lane → one member.** A question squarely inside a single member's deep
  lane (and outside everyone else's) runs as a solo dispatch of that member —
  chosen because the others have nothing to add, not to save effort for its own
  sake.
- **A few lanes → those members.** A question touching two or three lanes runs
  just those members.
- **Cross-cutting decision → the full active panel.** A go/no-go, a strategy
  call, or a design that genuinely spans economics + UX + feasibility + risk
  runs every active member — that is what the panel is for.
- **When unsure, run wider.** Under-scoping silently loses a lens the user
  staffed for, which is the worse failure; on genuine ambiguity, err toward the
  fuller panel.

**Disclose the choice and make it reversible — this is not optional.** State
which members you are running and which you are holding for this question, and
why (the lanes the question touches). A held member is a *scoping choice the
user can see and reverse in one step* — "say the word to bring in <held
members>" — never a silent omission. On-demand members set aside in Step 1 are
held the same way and listed alongside. If the user's phrasing signals they
want the whole team ("get everyone's take"), skip scaling and run the full
active panel.

Everything downstream — Step 2 lazy upgrade, Step 3 spawn — applies only to the
members this step selected.

## Step 2 — Lazy upgrade (per member, before first spawn)

Run once for every member about to be spawned this run (default members
always; an on-demand member only when the user explicitly asks to include it,
or via solo invocation). Branch on the member's `layer` from Step 1: a
**project-layer** member (`"layer": "project"`) passes `--project "<the
member's "project" value>"` verbatim — the same registry-basename exemption
`/staff` uses for its project-copy hires (case-sensitive, never re-derived
from the wiki root yourself). A **factory-layer** member is unchanged — no
`--project`, the factory-home denylist is absolute, no exceptions:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" validate-persona "<member-file>" [--project "<member's project value>"]
```

- **Exit 0** (`ok: true`) → proceed straight to Step 3 for this member.
- **Exit 1** (`ok: false`) → inspect `errors`:
  - If `errors` is exactly `["missing description"]` (that one error, and no
    other) → this is the lazy-upgrade path:
    1. Read the persona file's `role:` and `## Identity` section.
    2. Draft a description ≤ 600 characters, in "Use when…" form,
       routing-oriented — the same register as the plugin's bundled-agent
       descriptions (e.g. `agents/wiki-researcher.md`'s description: what the
       persona is for and when an orchestrator should reach for them, not a
       biography).
    3. Run:
       ```bash
       python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" upgrade-persona "<member-file>" --description "<drafted text>"
       ```
       This is an atomic (tmp+rename) write to the real persona file — it
       already happened by the time the command returns. This lazy-upgrade
       branch applies identically to either layer: `upgrade-persona` writes
       to whatever path it's given, so a project-layer copy at
       `<wiki-root>/personas/<slug>.md` is upgraded exactly like a
       factory-layer file at `<factory-home>/agents/<slug>.md` — no
       layer-specific handling needed here.
    4. Re-run `validate-persona` on the same file.
    5. Regardless of outcome, **show the user a diff-shaped summary line**
       for the file just written, e.g.:
       ```
       <factory-home>/agents/<slug>.md: + description: "<drafted text>"
       ```
       Factory-home writes are user-visible even when they aren't gated —
       disclose every one, always.
    6. If validation now passes → proceed to Step 3. If it still errors →
       fall through to the "any OTHER error" case below.
  - If the ONLY refusal-grade error is the missing **standard** citation anchor
    — `errors` is exactly `["missing citation anchor (CITATION_STANDARD)"]`, or
    exactly that plus `"missing description"` (which is itself lazy-upgradable)
    → OFFER to add the standard boilerplate anchor, with explicit user approval.
    This is the only immutable-rule content the skill may add on its own; a
    persona-SPECIFIC immutable rule is never authored here.
    1. If `"missing description"` is also present, first run the
       description lazy-upgrade above (draft + `upgrade-persona --description`,
       with its disclosure line) so only the anchor remains.
    2. Ask the user for one yes/no: may you add the standard citation anchor to
       `<member-file>`? Note that `upgrade-persona` cannot add the anchor — it
       only adds a description and fences an *existing* `## Immutable Anchors`
       section — so this is a direct edit, and only the verbatim boilerplate
       bullet from `${CLAUDE_PLUGIN_ROOT}/assets/factory-templates/persona.md`
       may be added this way. Never invent or infer a persona-specific rule.
    3. On yes, add this block to the file — paste it verbatim (heading, fence
       markers, and the one bullet, exactly as the template ships it):
       ```markdown
       ## Immutable Anchors (cannot change)

       <!-- IMMUTABLE:BEGIN -->

       - **Always attribute claims.** Every statistic, number, behavioral assertion, or external fact must carry a source tag per `CITATION_STANDARD.md` (`[internal::file]`, `[internal::data]`, `[external::claude-knowledge]`, `[external::web-search]`, `[hypothesis]`, etc.). Unattributed claims are invalid outputs. Internal client metrics must specify the source file and whether the number is a target or a measured baseline. `[hypothesis]` tags must appear in the session's `open_items`.

       <!-- IMMUTABLE:END -->
       ```
       If the file already has a `## Immutable Anchors` heading but no
       CITATION_STANDARD bullet, add the bullet (and fence markers, if absent)
       inside that existing section rather than duplicating the heading.
    4. Re-run `validate-persona` on the same file, and disclose the write with a
       diff-shaped summary line (same as the description upgrade). If it now
       passes → proceed to Step 3. If it still errors → treat this member as
       MISSING below.
    5. On no (user declines) → treat this member as MISSING for Step 4's panel
       roster, reason "missing citation anchor — declined auto-add."
  - If `errors` contains anything else — a `"denylist: ..."` hit, an over-budget
    description, or the citation-anchor error combined with any other error →
    **never spawn an invalid persona.** Treat this member as MISSING for Step
    4's panel roster, with the validate-persona `errors` list as the reason. Do
    not attempt to fix these automatically — they require a human edit to the
    persona file.

## Step 3 — Context assembly & spawn

For every member that passed Step 2 (default members, plus any explicitly
requested on-demand members):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" assemble-context --wiki-root "<wiki-root>" --persona "<member-file>"
```

Returns `{"persona": ..., "orientation": [<paths>], "prior_positions":
[{"page", "date", "type", "position"}, ...], "budget": {...}, "warnings":
[...]}`.

Carry each member's `layer` (from Step 1) forward alongside its assembled
context — Step 4's panel roster reports it per spawned member, and reports
any `drift_notice`/`layer_warning` the member carries.

Compose the dispatch prompt from four pieces, then dispatch via the **Agent
tool** with `subagent_type: general-purpose` (there is no plugin-registered
subagent type for an arbitrary factory persona — the persona's entire
identity has to live in the dispatch prompt itself, verbatim):

1. **The persona file, verbatim.** Read `<member-file>` in full and paste its
   entire contents into the prompt — frontmatter, `## Identity` through
   `## Mutable Instructions`, and the fenced `<!-- IMMUTABLE:BEGIN -->` /
   `<!-- IMMUTABLE:END -->` anchor section intact. Never summarize or excerpt
   the persona file.
2. **The orientation reading list**, from `orientation` above — hand the
   sub-agent the file paths and instruct it to `Read` them itself (the index
   catalog and `overview.md` are both small; there's no budget reason to
   inline them). Also hand it the `prior_positions` array's `position`
   strings directly as one-liners (these are already self-authored,
   wikilink-carrying summaries — inline them; don't make the sub-agent go
   re-read the source pages just to recover its own past position).
3. **The task** — what the user actually asked this run.
4. **Two fixed instructions, included verbatim in every single dispatch, no
   paraphrasing:**

   The reporting contract:

   ```
   Structure your entire response in these five parts, in this order, whatever your role — the parts are fixed; fill each in your own voice with what your lens produced:

   1. **Bottom line** — one sentence: your answer or verdict. Lead with it.
   2. **What I looked at** — the slice of the question you owned, one line.
   3. **What I found** — your substantive result, concrete (the number, the fact, the decision) and the key evidence for it. Not a narration of your process.
   4. **Why it matters** — what your finding changes for the user's decision, and the cost of ignoring it. Write this for a reader who does NOT share your context: translate it, don't assume it.
   5. **My call** — your recommendation; your confidence (high / medium / low) AND what specifically you are unsure about (distinguish confidence in the mechanism from confidence in the numbers); and the alternative you weighed and set aside ("none" only if there genuinely was none).

   Cover your own lens only. Do not synthesize across the panel, restate the whole problem, or speak for other members — synthesis is the orchestrator's job, not yours.

   Then end with a section titled `## Position (self-authored)` — one paragraph (2-4 sentences) distilling the five parts above, bottom line first, into something that stands on its own when quoted out of context months from now. This block is what future sessions quote verbatim as YOUR prior position; never leave it to the orchestrator to summarize you, and never make it a raw dump of the report above.

   Finally, after the Position block, append this machine-readable summary exactly — each value on ONE physical line. It is validated before your report is used: a missing field, an empty value, or a `confidence` outside high/medium/low sends the task straight back to you.

   <!-- REPORT:BEGIN -->
   bottom_line: "<part 1 — your one-sentence answer>"
   scope: "<part 2 — the slice you owned>"
   found: "<part 3 — your finding + the key evidence>"
   why: "<part 4 — what it changes for the decision>"
   call: "<part 5 — your recommendation>"
   confidence: high|medium|low
   confidence_basis: "<what you are sure vs unsure about>"
   dissent: "<the alternative you weighed; 'none' if there genuinely was none>"
   <!-- REPORT:END -->
   ```

   Before composing the deliverable-stub instruction, resolve the project's
   docs_path: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py"
   --get-docs-path "<wiki-root>"` and include the resolved path in every
   dispatch so the sub-agent knows where deliverables (and their stubs'
   `external-ref:`) go; if unset/absent, say so in the dispatch and tell the
   sub-agent to leave deliverables to the wiki's raw/ with a note.

   The deliverable-stub instruction:

   ```
   If you produce a deliverable file under the project's docs_path, also create its `source`-type wiki stub (type source, `external-ref:` to the file, one-paragraph summary, confidence low).
   ```

Dispatch every spawnable member in a single message (one Agent tool call per
member, so they run concurrently) and wait for all of them to complete before
moving to Step 4/5 — synthesis needs every output in hand.

At the end of the run, list any on-demand members that were set aside in Step
1 and not spawned: name, role, and how to invoke them (`/team solo <name>
<question>`).

## Step 3.5 — Validate each returned report (gate before synthesis)

Each spawned member ends its output with a `## Position` block and a fenced
`<!-- REPORT:BEGIN -->…<!-- REPORT:END -->` summary. Before synthesizing,
validate that summary — this is what makes the five-part shape a guarantee
rather than a hope. For each returned output, write it verbatim to a temp file
and run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" validate-report "<temp-file>"
```

- **Exit 0** (`ok: true`) → the report is well-formed; carry on.
- **Exit 1** (`ok: false`) → re-dispatch THAT ONE member once, identical to the
  first dispatch except append the returned `errors` and: "resend your full
  response including a corrected `<!-- REPORT:BEGIN -->…<!-- REPORT:END -->`
  block." This is a **single bounded retry** — never loop.
- If the retry still fails (or the member errored, or again returned no block),
  treat that member as **malformed report** for Step 4's roster, reason = the
  `validate-report` errors. Never synthesize an unvalidated member — the same
  discipline as Step 2 never spawning an invalid persona.

The gate is disclosure, not silent repair: if any member needed a retry or
landed as malformed, surface it in the roster.

## Step 4 — Partial failure (panel roster, always first)

Before any synthesis content, the orchestrator's output **must open with a
panel roster**:

- **Spawned:** every member actually dispatched (name, role, and its
  `layer` — "project" or "factory"). If the member carries a `drift_notice`
  (its project copy's base has changed since the copy forked), surface it
  plainly as a note — this is disclosure, not a stop — quoting the exact
  remediation command: `python3
  "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" ack-fork "<member-file>"`. If
  the member carries a `layer_warning` instead (its project copy was
  unreadable and the member ran on its factory-layer base), surface that
  too, so the user knows they got the factory base, not the project copy
  they may have expected.
- **Missing:** every member that did not run, each with name, role, and why —
  one of: persona file absent (from `resolve-team`'s `missing` list),
  validation error (from Step 2, with the actual error text), spawn
  failure (the Agent tool call itself errored), or **malformed report** (from
  Step 3.5, with the `validate-report` errors — the member ran but its report
  failed the gate twice). For each missing member, also
  state **what they were expected to cover** — their `role` (and `note`, if
  you read the team YAML: `resolve-team`'s `missing` payload carries only
  `agent` + `role`, so `note` is only available by reading
  `teams/<name>.yaml` directly) — so the gap is legible, not just named.
- **Held (not needed for this question):** every active or on-demand member
  deliberately not spawned per Step 1.5's scaling — name, role, the one-line
  reason (outside the question's lane / on-demand), and "available on request."
  A held member is a **scoping choice, not a gap** — keep it visually distinct
  from Missing so a deliberate scope-down never reads as a failure.

Spec rule, held to verbatim: synthesis "names missing members and what they
were expected to cover — never presents a partial panel as complete." A team
run with 2 of 5 members missing is reported as a 3-member panel with 2 gaps
called out, never quietly presented as if it were the whole team's view.

## Step 5 — Synthesis (for the user: action-first and concrete)

The synthesis exists to make the panel's work **actionable for the user** — not
a transcript, and not a birds-eye abstract. The failure mode to avoid is a "big
ball of text": every lens quoted in full, pitched high, with no clear
recommendation the user can act on. Your job as orchestrator is to **decide and
recommend**, grounded in what the panel found. Lead with what to DO, keep every
claim concrete, and compress the individual takes. Fixed order:

1. **Recommended next steps — the headline, and your own call.** The concrete,
   ordered action the panel's work points to: 2–5 specific steps, each naming
   the actual thing — the file, the number, the lever, the owner — not a
   category. ("Tighten the guardrail" is fluff; "raise the ceiling check from
   15% to 20% in `pnl.html:1073`, then re-verify at ARR=$500M" is a step.) Take
   a position — "do X, then Y; I'd hold Z" — and if the panel split, recommend
   the path AND name what would change your recommendation. This is the first
   thing the user reads.
2. **Why — the bottom line, concrete.** 2–4 sentences grounded in specifics (the
   actual figure, the named threshold, the `file:line`), never abstractions.
   Litmus test: if a sentence could be pasted into any other project's review
   unchanged, it is fluff — replace it with the specific fact from the panel's
   output.
3. **The crux — only if there is one.** The single load-bearing disagreement or
   risk that would change the recommendation, stated concretely, with the
   specific personas on each side (e.g. "Rowan and Sloane split on the 2.0×
   threshold — Rowan: …; Sloane: …"): **1–3, up to 5**, never padded, never a
   manufactured split. If the panel agreed, say so in one line and skip this.
4. **The takes — compressed, not a wall.** ONE line per member: their name +
   their headline position, so the user sees who contributed what without
   reading six verbatim blocks. The full self-authored positions are **not
   discarded** — session-close writes each `## Position` block verbatim to the
   record, and you offer them in full on request ("say the word for the full
   individual takes"). The one-liner is a reading aid pointing at a preserved
   verbatim position; never overwrite a persona's self-authored position with
   your summary.

**Concreteness gate (parts 1–3):** every claim names a specific number, file,
lever, or action. A synthesis that could describe any project has failed — go
back to the panel's outputs and pull the specifics. Name specific personas on
any contested point — never "some members felt X."

## Step 6 — Solo invocation

Triggers: `/team solo <persona> <question>`, or natural language directly
addressing a named persona ("Wren, what do you think about X?").

Same pipeline, single member, no team YAML and no synthesis step:

1. Resolve the persona file directly: lowercase-and-hyphenate the given name
   to a candidate slug, then resolve it through the same layered machinery
   Step 1 uses — never a hand-rolled path check:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" resolve-persona "<slug>" --wiki-root "<wiki-root>"
   ```
   Exit 0 returns `{"file": ..., "layer": "project"|"factory"}` (+
   `"project"`/`"drift_notice"`/`"layer_warning"` under the same conditions
   as Step 1's member dicts). Exit 2 (the slug resolves in neither layer) →
   list the roster (`ls "<factory-home>/agents/"*.md`) and ask the user
   which persona they meant — do not guess or fall back to a generic answer
   voiced as that persona.
2. Run Step 2 (lazy upgrade) against that one file — same `--project` rule:
   pass it when `"layer": "project"`, omit it when `"layer": "factory"`.
3. Run Step 3's `assemble-context` and dispatch, with the question as the
   task. Same two verbatim instructions apply.
4. Run the Step 3.5 gate on the returned output (`validate-report`), with the
   same single bounded retry — a solo answer is held to the same reporting
   contract as a panel member.
5. Return the sub-agent's output as-is, including its `## Position
   (self-authored)` section — no panel roster needed for a single member, but
   if that one member failed validation, its report stayed malformed after the
   retry, or the dispatch itself failed, say so plainly instead of silently
   answering as a generic assistant.

## Step 7 — Recruit

Trigger: `/team recruit <role> for <task>`.

**Confirm this is a single hire before drafting.** Recruit produces exactly
**one** persona. If the user is staffing a new project from scratch, wants more
than one member, or is unsure how many, do not proceed here — hand off to the
`/staff` skill (guided interview + multi-member slate), the whole-team door.
Only continue below once a single role for a single task is settled.

1. **Source material.** Search the factory home's own curated pool first,
   then the vendored catalog second — the same references-before-catalog
   tie-break `search-candidates` documents (ties break starter > references
   > catalog):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" search-candidates --query "<role terms>" --source references
   ```
   **This pool may be empty — it currently is** in the real factory home.
   When it has nothing usable for `<role>`, fall back to the vendored
   catalog:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" search-candidates --query "<role terms>" --source catalog
   ```
   If neither pool has anything usable, draft the persona from the role
   description + task directly, or from a source file the user names.
   Staffing a whole team rather than a single hire? Point the user at
   `/staff` instead — that skill runs the full guided interview and slate
   composition; this step is the single-hire shortcut.
2. **Draft.** Fill `${CLAUDE_PLUGIN_ROOT}/assets/factory-templates/persona.md`
   placeholders (`{{NAME}}`, `{{ROLE}}`, `{{DESCRIPTION}}`, plus the body
   sections) from the source material and the task. The description must be
   ≤ 600 chars, "Use when…" form, same as Step 2's lazy-upgrade drafts. Also
   fill the frontmatter `domain:` list with 2-5 lowercase topic tags for the
   persona's expertise — these drive focus-page selection in context
   assembly; an empty list means the persona gets no focus pages. Compute a
   slug from the name (lowercase, hyphenated).
3. **Refuse to overwrite.** Before writing anywhere real:
   ```bash
   test -f "<factory-home>/agents/<slug>.md" && echo "slug already exists — pick a different name"
   ```
   If it exists, stop and ask the user for a different name/slug.
4. **Validate before saving — never save an invalid persona.** Write the
   draft to a scratch temp path (not the real roster location yet) and run:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" validate-persona "<scratch-path>"
   ```
   If it errors, show the errors to the user and fix the draft (missing
   description, missing citation anchor, denylist hit, etc.) — repeat
   validation until it passes. Only a persona that validates clean may
   proceed to Step 5. This is a hard refusal: a persona with validation
   errors is never written to `<factory-home>/agents/`.
5. **Human gate, then atomic write.** Show the user the full drafted persona
   file as a diff (new file, so the whole thing is the "diff") **before
   writing it** to the real roster location — factory-home persona writes are
   shown to the user before writing, always. On confirmation, write it
   atomically (tmp+rename, mirroring `resolve_wiki.py`'s pattern):
   ```bash
   cp "<scratch-path>" "<factory-home>/agents/<slug>.md.tmp" && mv "<factory-home>/agents/<slug>.md.tmp" "<factory-home>/agents/<slug>.md"
   ```
6. **Offer team membership.** Show the exact `members:` YAML block the user
   would append to a team file (using the same shape as
   `assets/factory-templates/team.yaml`):
   ```yaml
   members:
     - agent: <slug>
       role: "<role on this team>"
       model: claude-opus-4-8
       effort: deep
   ```
   Ask which team (if any) to add it to — or "none." If the user picks a
   team, append the block to `<factory-home>/teams/<team>.yaml` (again shown
   as a diff before writing).

## Step 8 — Bookkeeping

Every run (team, solo, or recruit) ends its output with a one-line note of
which personas were lazily upgraded this run (Step 2), e.g. "Lazily upgraded:
wren (added description)." or "Lazily upgraded: none this run."
