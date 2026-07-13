---
name: improve
description: Review the factory home's pattern jot and propose persona edits as diffs, one per persona, never applying without explicit human approval; the fenced Immutable Anchors are guarded byte-unchanged before any write. Approved edits commit individually — base personas to the factory home's git repo, project copies to their own project's repo — so git revert is the rollback in whichever repo holds the file. Requires a registered factory home that is a git repo with a clean tree; STOPs otherwise. Use when the user says "/improve review", "review the pattern log", "improve the personas", or asks whether recurring feedback should change a persona.
---

# improve skill

Reads the factory home's pattern jot — durable, user-authored observations
appended by `/session-close` — groups them by persona, and proposes concrete,
minimal edits to each affected persona's mutable sections. Every edit is a
diff shown to the human before anything is written; nothing is applied
without explicit per-diff approval. The fenced `## Immutable Anchors` section
of a persona is never touched, and a deterministic guard
(`team_ops.py anchors-unchanged`) verifies that byte-for-byte before any
write lands. Approved edits are committed one diff at a time — a base
persona's edit to the factory home's git repo, a project copy's edit to its
own project's repo — **the commit is the change log; `git revert` is the
rollback.** That holds in whichever repo holds the edited file.

The machinery (guard, validation) lives in `scripts/team_ops.py`; this skill
is the judgment layer on top of it — reading the jot, grouping observations,
drafting the minimal diff, and running the human gate.

Spec rule, held to verbatim: **"Agents propose, never apply. Human gate
always."**

## Preflight

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded?}"
```

`/improve` operates entirely on the factory home (personas + pattern jot) —
it never touches the current project's wiki, so there is no project-wiki
resolution step here (unlike `/team`, `/session-close`, or the `llm-wiki:`
skills).

## Step 1 — Resolve the factory home (git-gated, clean-tree-gated)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" resolve-factory-home
```

Branch on `status` — this is the **same** rule as `/team`'s, the opposite of
`/session-close`'s degrade-gracefully rule: `/improve` never runs against a
missing or unregistered factory home.

- `ok` → note `factory_home`; continue.
- `missing` or `absent` → **STOP.** Surface the JSON `hint` field to the user
  verbatim:
  - `absent`: `"No factory home registered. Register with: resolve_wiki.py register-factory-home <path>"`
  - `missing`: `"Recorded factory home no longer exists or lost agents/ or teams/. Re-register with: resolve_wiki.py register-factory-home <path>"`

  Do not continue past a STOP here.

`status: ok` is necessary but not sufficient. `/improve`'s entire rollback
story depends on the factory home being a git repository, so confirm that
next:

```bash
git -C "<factory-home>" rev-parse --git-dir
```

- **Fails** (not a git repo) → **STOP.** Tell the user, verbatim:
  > the commit is the change log; git revert is the rollback — run git init first

  This is not a style preference — the spec's rollback mechanism ("The
  commit is the change log; `git revert` is the rollback.") is
  unimplementable without a git repo to commit into, so `/improve` refuses
  to propose anything until one exists.
- **Succeeds** → continue.

Finally, require a clean tree before proposing anything:

```bash
git -C "<factory-home>" status --porcelain
```

- **Non-empty output** → the home has uncommitted changes. Surface this to
  the user **first**, before reading the jot or drafting anything — show the
  `git status --porcelain` output and ask how they want to proceed (commit or
  stash their own changes first). `/improve` does not draft proposals against
  a dirty tree, since a proposal's diff and the eventual commit both assume
  the working tree matches the last commit.
- **Empty output** → continue to Step 2.

## Step 2 — Read the jot

```bash
test -f "<factory-home>/patterns/pattern-log.jsonl" && cat "<factory-home>/patterns/pattern-log.jsonl" || echo "absent"
```

(Or simply `Read` the file — preferred — it's a plain-text JSON-lines file,
no script wraps it; grouping and parsing is this skill's own judgment work,
not delegated to `team_ops.py`.)

- **File absent, or present but empty** → report to the user, verbatim:
  > no jot lines — nothing to review

  and **STOP.** This is a valid, non-error outcome — never fabricate
  observations to have something to show. (On the real factory home, at the
  time this skill was written, this is in fact the current state: no session
  has jotted a genuine observation yet.)
- **File has content** → parse each line as JSON, defensively:
  - A line that fails to parse (`json.JSONDecodeError`, or parses to
    something that isn't the expected object shape) is **skipped**, not
    fatal — but **count** how many lines were skipped and report the count
    in Step 6's bookkeeping. The jot is a plain `open(path, "a")` append log
    with no lock, so a half-written line from a crashed process is an
    expected edge case, not a bug to chase here.
  - Each valid line has the schema `{"session", "date", "observation",
    "source"}` with an optional `"personas"` key (a list of lowercase
    slugs) — `source` is always `"user-turn"` per the jot's provenance rule.
    Lines from before persona classification existed simply lack the
    `personas` key; treat that the same as an empty list.
  - Each valid line may also carry an optional `"wiki"` key (string) —
    `jot_append`'s own documented provenance field: "the wiki/project this
    call's observations concern" (session-close passes the resolved wiki
    path when one resolved for that session). Lines from before wiki
    provenance existed, or written during a factory-home-only session where
    no wiki resolved, simply lack the key; treat that the same as **no
    provenance recorded** — never guess a wiki for an unmarked line.

Group the parsed observations:

- **By persona slug** — a line with `"personas": ["wren", "marnie"]`
  contributes its observation to both `wren`'s and `marnie`'s groups (a
  session-close call can tag one observation with multiple personas).
- **By wiki, within each persona group** — further subdivide each persona's
  group by the literal `"wiki"` string value of its observations: one
  sub-group per distinct value present, plus a **"no wiki recorded"**
  sub-group for observations lacking the key. This sub-grouping is read-only
  bookkeeping for Step 3's routing default below — it does not change what
  counts as "at least one observation" for a persona group, and (unlike
  "general / unassigned") it is not itself surfaced to the user as a
  separate group to act on.
- **Unclassified** — any line with no `personas` key (or an empty list) goes
  into its own **"general / unassigned"** group. Do not guess which persona
  an unclassified observation is about; show this group to the user as-is so
  they can route it manually or dismiss it. `/improve` never auto-assigns an
  unclassified observation to a persona.

## Step 3 — Propose (never apply)

For every persona group from Step 2 with **at least one** observation
(skip the "general / unassigned" group here — it has no single persona file
to edit; just display it for the user's own judgment):

0. **Routing lookup, before drafting anything:**

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" list-copies "<slug>"
   ```

   Returns `{"copies": [{"wiki", "path", "forked", "drifted"}, ...]}` (plus
   `"skipped"` when > 0 copy files were unreadable) — one entry per
   registered wiki carrying a project-copy persona forked from this slug.
   `"wiki"` is the registered wiki's path, verbatim; `"drifted"` is
   tri-state (`true` / `false` / `null` — `null` means the comparison
   couldn't be made, e.g. no recorded `base-hash`) and is only carried
   forward here, not acted on. An empty `"copies"` list means no project
   copies exist for this slug — routing is base-only, no question to ask.
1. Read `<factory-home>/agents/<slug>.md` in full, and — if `list-copies`
   returned any copies — read each copy's file too (its `"path"` field), so
   a multi-target proposal (below) can draft each target's diff against
   that file's real current text rather than assuming a copy still reads
   like the base.
2. **Determine the routing** — the set of target files this persona's
   proposal will carry diffs for — from provenance, before drafting:
   - No copies → route to **base**; no question to surface.
   - Copies exist → compare this persona's Step 2 wiki sub-groups against
     the copies' `"wiki"` values:
     - Every observation in this persona's group carries a `"wiki"` value
       matching **exactly one** copy's `"wiki"` → default to **that copy**,
       and quote the provenance reason back to the user, the spec's own
       phrasing: *"this feedback came from sessions where the `<wiki>` copy
       ran."* This clean single-copy-provenance case is the **only** one
       that gets a default.
     - No observation in the group carries any wiki provenance at all, but
       copies exist anyway → default **base**, but mention in the proposal
       that copies exist so the user can redirect.
     - Observations span **multiple** wikis, or the routing is otherwise
       N-way ambiguous (e.g. split between a "no wiki recorded" sub-group
       and one or more copies) → **ASK before drafting**: present the
       observation sub-groups and the candidate targets (each implicated
       copy, plus base where eligible per the rule below) and let the user
       pick the target set — never silently default a multi-target
       routing.
   - **Base joins the target set only when some observation lacks wiki
     provenance** (the "no wiki recorded" sub-group is non-empty) **or the
     user says so** — feedback whose provenance is purely copy-side never
     silently implicates the base.
3. Draft a **minimal** edit to a non-fenced section — normally
   `## Mutable Instructions`, but any section outside the
   `<!-- IMMUTABLE:BEGIN -->` / `<!-- IMMUTABLE:END -->` markers is fair
   game — that addresses the recurring feedback in that persona's
   observation group, against each file in the routed target set.
   "Minimal" means: the smallest change that actually resolves the
   pattern, not a rewrite of the file. **Never** draft a change
   inside the fenced Immutable Anchors block — that section cannot change,
   full stop. **Never** invent feedback that isn't present in an actual jot
   observation; every clause in the diff must trace back to something a
   real observation said.
4. Present the proposal to the user as a **unified diff**, with the
   **verbatim triggering jot observation(s) quoted directly above the
   diff** — the spec's own phrase: "with the verbatim triggering feedback
   attached" — and, always, the routing question up front so the user never
   has to recall which layer their feedback targets. Example shape:

   ```
   ### Proposal: <persona-name> (<slug>)

   Routing: <the target set — base, the "<wiki>" copy, or several targets listed out> (defaulted from jot provenance, or as you chose when asked; say which target(s) you'd rather have to change it)

   Triggering observation(s):
   > "<jot observation text, verbatim>"
   > "<second observation, verbatim, if more than one>"

   --- a/agents/<slug>.md
   +++ b/agents/<slug>.md
   @@ ...
   -<removed line>
   +<added line>
   ```

   **Per-target diffs — one separately drafted diff PER routed target,
   never one patch ported.** When the target set holds more than one file
   (base plus one or more copies, or several copies), each target's diff
   is drafted fresh against ITS OWN current text — a copy may have
   diverged from the base since it forked, so a base diff is never
   mechanically re-applied to a copy. If a copy's equivalent section has
   diverged so far that the base diff doesn't conceptually apply to it,
   draft what actually fits the copy's current text and label that diff
   **"adaptation, not a port"** in the gate presentation — never force-port
   a base diff onto a copy whose relevant section no longer resembles it.

**One proposal per persona per run** — if a persona's group has three
observations, they inform a single combined diff, not three separate
proposals. The one documented exception is multi-target routing: that
single persona's proposal carries one diff per routed target file, each
still gated independently in Step 4 ("the gate is per-diff, not
per-run").

## Step 4 — Human gate

For **each** proposal from Step 3, individually:

- The user **approves**, **rejects**, or **edits** it.
- **Nothing is written to disk before that specific diff's explicit
  approval.** Approving one persona's proposal does not approve any other
  persona's proposal — the gate is per-diff, not per-run.
- A **rejected** proposal is simply dropped — optionally note to the user
  that its triggering jot line(s) can be treated as dismissible (they are
  never deleted from the jot itself; see Step 6).
- An **edited** proposal (the user changes the diff before approving) is
  applied as the user's edited version, not the original draft.

**What this gate is actually for:** Step 5's `anchors-unchanged` guard is a
narrow, deterministic backstop — it protects the fenced bytes, fence
structure, and each fence's section location, and nothing else. It does
**not** detect prose inserted or rewritten outside the fences, even prose
placed immediately adjacent to a fence or within the same section. Catching
an adversarial or simply wrong edit to the *unfenced* text is the human
diff review's job, right here at this gate — read every diff, don't rubber
stamp it because the guard will "catch it" downstream. It won't.

## Step 5 — Apply, verify, commit (approved proposals only)

Each approved diff from Step 3 targets exactly one file — the base persona
(`<factory-home>/agents/<slug>.md`) or one project copy (its `list-copies`
`"path"`) — call it `<target-file>` below. Under multi-target routing there
is one approved diff per routed target for the same persona, so this whole
chain runs **once per target file, independently**. The command blocks in
steps 2 and 4 take `<target-file>` directly; anywhere else a step still
spells out `<factory-home>/agents/<slug>.md` (e.g. step 2's lazy-upgrade
recovery branch), read it as `<target-file>` — the scratch-write, guard,
and atomic-write mechanics are identical regardless of which file is being
edited; only validation (step 3) and the commit destination (step 5)
differ by layer, both called out explicitly where they occur.

For each **approved** proposal, in order:

1. Write the edited persona file to a scratch path (e.g. under `$TMPDIR`,
   same convention as `/session-close`'s and `/team`'s scratch writes) —
   never edit the real file directly yet.
2. Run the deterministic guard against the original and the scratch copy:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" anchors-unchanged "<target-file>" "<scratch-path>"
   ```

   Exit codes are this skill's branch points:
   - **Exit 0** (`ok: true`) → the fenced anchors survived the edit
     untouched; continue to step 3.
   - **Exit 1** (`ok: false`) with reason exactly
     `"original has no fenced anchors"` → the persona predates fencing and
     must be lazily upgraded before /improve may touch it. **Recovery
     branch**, not a block:
     1. Fence the anchors in place (no `--description` — this run changes
        fencing only, never the description):
        ```bash
        python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" upgrade-persona "<factory-home>/agents/<slug>.md"
        ```
        This is an atomic (tmp+rename) write to the real persona file — it
        already happened by the time the command returns. **Disclose it to
        the user** with a diff-shaped summary line, same rule as `/team`'s
        lazy upgrade:
        ```
        <factory-home>/agents/<slug>.md: + <!-- IMMUTABLE:BEGIN --> / <!-- IMMUTABLE:END --> fence around Immutable Anchors
        ```
        Factory-home writes are user-visible even when they aren't gated —
        disclose every one, always.
     2. **Re-create the scratch edit against the NOW-FENCED file** — the old
        scratch copy was drafted from the unfenced original and would itself
        fail the guard; discard it, re-read the persona file, and re-apply
        the approved diff to the fenced text.
     3. Re-run this chain from step 2 (guard, then validation) against the
        new scratch copy. The recovery runs **once** per persona — if the
        guard still reports `"original has no fenced anchors"` after the
        upgrade, treat it as blocked with that reason (something is wrong
        with the file, e.g. no `## Immutable Anchors` heading for
        upgrade-persona to fence).
   - **Exit 1** (`ok: false`) with any other reason → the proposal is
     **INVALID** — some fenced byte, fence structure, or fence section
     location changed. Do **not** apply it. Tell the user the guard's
     `reason` field verbatim, and treat this persona's edit as blocked
     (counted in Step 6). This is the deterministic backstop the spec
     relies on, not a formality — never override it by hand.
   - **Exit 2** → one of the two paths was unreadable; treat as blocked the
     same way, with the reported reason.
3. Validate the scratch copy:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/team_ops.py" validate-persona "<scratch-path>" [--project "<registry-basename>"]
   ```

   **Project copies validate with `--project`:** when `<target-file>` is a
   project copy, pass `--project` with that copy's `list-copies` `"wiki"`
   value's own basename (`Path(copy["wiki"]).name`) — the same
   registry-entry basename `validate-persona` derives internally
   (`Path(entry["path"]).name`), **not** the wiki's `domain:` label, and the
   match is case-sensitive; this is the same own-name exemption `/staff` and
   `/team` pass for their project-copy validations, never re-derived some
   other way here. A base-file target omits `--project` exactly as before —
   the factory-home denylist is absolute, no exceptions.

   - **Exit 0** (`ok: true`) → clean; continue to step 4.
   - **Exit 1** (`ok: false`) → the edit broke something validate-persona
     checks (description budget, citation anchor, denylist). Do **not**
     apply it — tell the user the `errors` list and treat this persona's
     edit as blocked (counted in Step 6). Never patch around a validation
     failure automatically; that's a human call.
   - **Exit 2** → the scratch path isn't a readable file (missing or
     unreadable). Do **not** apply — treat as blocked the same way as the
     guard's exit 2, with the reported error.
4. Only once both checks pass, write the scratch copy over the real file
   atomically (tmp+rename, mirroring `/team recruit`'s write pattern):

   ```bash
   cp "<scratch-path>" "<target-file>.tmp" && mv "<target-file>.tmp" "<target-file>"
   ```
5. Commit **this diff's edit alone** — one commit per approved diff, so a
   single `git revert` can undo exactly one persona's (or one copy's) change
   without touching any other. **The commit destination follows the file:**

   - **Base target** → the factory-home repo, unchanged from before:

     ```bash
     git -C "<factory-home>" add "agents/<slug>.md"
     git -C "<factory-home>" commit -m "improve(<slug>): <one-line summary of the change>

     Triggering observation: \"<verbatim jot observation quoted in Step 3>\""
     ```

     Record the resulting commit SHA
     (`git -C "<factory-home>" rev-parse HEAD`) for Step 6.
   - **Project-copy target** → that copy's own project repo, never the
     factory home. `<project-root>` is that copy's `list-copies` `"wiki"`
     value (the registered wiki root path, verbatim). Confirm it's a git
     repo first:

     ```bash
     git -C "<project-root>" rev-parse --git-dir
     ```

     - **Fails** (not a git repo) → the edit already landed on disk (step 4
       above already wrote it) — this is not a STOP. Tell the user plainly
       that the edit is **uncommitted**: `"<project-root>` is not a git
       repo — the edit to `personas/<slug>.md` is on disk but not
       committed; commit it yourself once the project has a repo."` Record
       "uncommitted" (no SHA) for this diff in Step 6. Do not run `git init`
       on the user's behalf here — that STOP-and-ask posture is reserved
       for the factory home in Step 1, not something to silently fix on a
       project `/improve` hasn't been asked to manage.
     - **Succeeds** → commit exactly this copy's file, same
       one-edit-per-commit discipline as the base path:

       ```bash
       git -C "<project-root>" add "personas/<slug>.md"
       git -C "<project-root>" commit -m "improve(<slug>): <one-line summary of the change>

       Triggering observation: \"<verbatim jot observation quoted in Step 3>\""
       ```

       Record the resulting commit SHA
       (`git -C "<project-root>" rev-parse HEAD`) for Step 6.

   **After an approved edit that targeted the base ONLY** (the routed
   target set was the base alone, with no copy diff alongside it), when
   this persona's Step 3 `list-copies` result was
   non-empty: remind the user, once, that the existing project copies did
   **not** receive this edit — they will surface a `drift_notice` (the same
   spawn-time backstop `/team` and `/staff` already show) the next time a
   team resolves them, since the base's bytes just changed underneath them
   with no corresponding `ack-fork`. This is disclosure only, not a gate —
   it doesn't block or delay the commit just made.

## Step 6 — Bookkeeping

End the run's output with, **every tally below split by layer** (base vs.
project-copy) — a multi-target persona contributes one count per routed
target's layer, since each target got its own independently drafted diff:

- **Proposals made** — count from Step 3, base diffs / project-copy diffs.
- **Approved** / **Rejected** / **Blocked by guard** (anchors-unchanged
  exit ≠ 0, or validate-persona exit 1 or 2) — counts from Steps 4–5, each
  split base / project-copy.
- **Commit SHAs** — one line per commit actually made in Step 5, persona
  slug + layer (base or the copy's project name) + SHA + subject; a
  project-copy diff whose project root wasn't a git repo lists
  "uncommitted" in place of a SHA (see Step 5).
- **Drift reminders surfaced** — how many times Step 5's "base edited while
  copies exist" reminder fired this run, one per affected persona.
- **Unparseable jot lines skipped** — the count from Step 2, if any.
- **General / unassigned observations** — how many were shown but not
  acted on this run (they remain in the jot for a future run to pick up).

**No jot line is ever deleted or rewritten by `/improve`** — regardless of
whether its proposal was approved, rejected, or never drafted at all.
`patterns/pattern-log.jsonl` is append-only history, not a work queue to be
drained; a rejected or applied observation stays in the file exactly as
`/session-close` wrote it.
