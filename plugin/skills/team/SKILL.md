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
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded?}"
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

For the `/team <name>` form, resolve the team's roster:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" resolve-team "<name>"
```

This call re-checks the factory home itself and will also exit 2 with a JSON
`hint` if it has gone missing between the two calls above — treat that exit
the same way (STOP, surface the hint). On success it returns
`{"team": {...}, "members": [...resolved, each with "file"...], "missing":
[...]}`. Members in `missing` (persona file absent from `agents/`) are added
directly to the panel roster (Step 4) with reason "persona file not found" —
they are never retried or drafted on the fly; that is what `/team recruit` is
for.

Members whose team-YAML entry has `invocation` starting with `on-demand` are
**not spawned by default** — set them aside and list them to the user at the
end as available (see Step 3).

## Step 2 — Lazy upgrade (per member, before first spawn)

Run once for every member about to be spawned this run (default members
always; an on-demand member only when the user explicitly asks to include it,
or via solo invocation):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" validate-persona "<member-file>"
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
       already happened by the time the command returns.
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
  - If `errors` contains anything other than exactly `["missing description"]`
    (e.g. `"missing citation anchor (CITATION_STANDARD)"`, a `"denylist: ..."`
    hit, or an over-budget description) → **never spawn an invalid persona.**
    Treat this member as MISSING for Step 4's panel roster, with the
    validate-persona `errors` list as the reason. Do not attempt to fix these
    errors automatically — they require a human edit to the persona file.

## Step 3 — Context assembly & spawn

For every member that passed Step 2 (default members, plus any explicitly
requested on-demand members):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" assemble-context --wiki-root "<wiki-root>" --persona "<member-file>"
```

Returns `{"persona": ..., "orientation": [<paths>], "prior_positions":
[{"page", "date", "type", "position"}, ...], "budget": {...}, "warnings":
[...]}`.

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

   The attribution contract:

   ```
   End your output with a section `## Position (self-authored)` — 2-4 sentences in your own voice stating your position, dissent included. This exact text is what future sessions will quote as YOUR prior position; never leave it to the orchestrator to summarize you.
   ```

   Before composing the deliverable-stub instruction, resolve the project's
   docs_path: `python3 "$CLAUDE_PLUGIN_ROOT/scripts/resolve_wiki.py"
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

## Step 4 — Partial failure (panel roster, always first)

Before any synthesis content, the orchestrator's output **must open with a
panel roster**:

- **Spawned:** every member actually dispatched (name, role).
- **Missing:** every member that did not run, each with name, role, and why —
  one of: persona file absent (from `resolve-team`'s `missing` list),
  validation error (from Step 2, with the actual error text), or spawn
  failure (the Agent tool call itself errored). For each missing member, also
  state **what they were expected to cover** — their `role` (and `note`, if
  you read the team YAML: `resolve-team`'s `missing` payload carries only
  `agent` + `role`, so `note` is only available by reading
  `teams/<name>.yaml` directly) — so the gap is legible, not just named.

Spec rule, held to verbatim: synthesis "names missing members and what they
were expected to cover — never presents a partial panel as complete." A team
run with 2 of 5 members missing is reported as a 3-member panel with 2 gaps
called out, never quietly presented as if it were the whole team's view.

## Step 5 — Synthesis

After the panel roster, the orchestrator synthesizes across the spawned
members' outputs:

- Pull out agreements, disagreements, and open questions across the panel.
- **Every member's `## Position (self-authored)` block is carried into the
  synthesis output VERBATIM** — copy the text exactly as the sub-agent wrote
  it, under that member's name. This is attribution integrity: the
  orchestrator never paraphrases a persona's position on their behalf: it
  only ever quotes it.
- On any contested point, name the specific personas on each side (e.g. "Wren
  and Marnie disagree on X — Wren: ...; Marnie: ...") — never "some members
  felt X."

## Step 6 — Solo invocation

Triggers: `/team solo <persona> <question>`, or natural language directly
addressing a named persona ("Wren, what do you think about X?").

Same pipeline, single member, no team YAML and no synthesis step:

1. Resolve the persona file directly: lowercase-and-hyphenate the given name
   to a candidate slug and check `<factory-home>/agents/<slug>.md`. If it
   doesn't exist, list the roster (`ls "<factory-home>/agents/"*.md`) and ask
   the user which persona they meant — do not guess or fall back to a generic
   answer voiced as that persona.
2. Run Step 2 (lazy upgrade) against that one file.
3. Run Step 3's `assemble-context` and dispatch, with the question as the
   task. Same two verbatim instructions apply.
4. Return the sub-agent's output as-is, including its `## Position
   (self-authored)` section — no panel roster needed for a single member, but
   if that one member failed validation or the dispatch itself failed, say so
   plainly instead of silently answering as a generic assistant.

## Step 7 — Recruit

Trigger: `/team recruit <role> for <task>`.

1. **Source material.** Browse `<factory-home>/references/agency-agents/` for
   a persona to adapt. **This directory may be empty — it currently is** in
   the real factory home. When it has nothing usable for `<role>`, fall back
   to drafting the persona from the role description + task directly, or from
   a source file the user names.
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
