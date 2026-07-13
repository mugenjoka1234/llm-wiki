---
name: session-close
description: Close out a working session, idempotently: sweep stray files and unmanifested raw drops into the wiki (the only guaranteed stub-creation point), write/refresh the session page and any decision pages, keep overview.md and the quarterly log current, jot durable user-feedback patterns to the factory home (degrades gracefully — skipped, not blocked, when the factory home is unavailable), then lint and reindex. A crashed close is fixed by re-running it. Use when the user says "wrap up", "close the session", "done for today", or invokes `/session-close`.
---

# session-close skill

Orchestrates end-of-session bookkeeping for an AI-Factory-backed wiki: sweeps
stray output into the wiki, writes the session page (and any decision pages
it produced), keeps `overview.md` and the quarterly log current, jots durable
user-feedback patterns to the factory home, and re-lints/reindexes — in that
order, every step idempotent so a crash mid-run is fixed by simply re-running
the skill.

The machinery (idempotent append, pattern-jot dedup, read-only stray/raw
detection) lives in `scripts/session_ops.py`; this skill is the judgment
layer on top of it — deriving the session ID, drafting page content, and
deciding what gets written where.

A SessionEnd hook records an activity breadcrumb for this wiki on every
session, and the next SessionStart warns the user if that breadcrumb is
newer than the newest `wiki/sessions/*.md` page — re-running `/session-close`
writes a session page dated today, which clears the warning on the session
after that.

**Hook internals.** The two hooks (`plugin/hooks/hooks.json`, dispatched via
`plugin/hooks/run-hook.sh`) call `session_ops.py breadcrumb --cwd [--session-id
--date]` (SessionEnd) and `session_ops.py session-check --cwd` (SessionStart).
Both take `--cwd`, not `--wiki-root` — this is deliberate, not an
inconsistency: the hooks fire on every session in every working directory
(most of which aren't wikis at all) and resolve the wiki from `cwd`
internally, silently no-op-ing when there isn't one. `sweep-scan` in Step 1
below takes `--wiki-root` instead because it's invoked by this skill only
after the wiki is already resolved — it targets a known wiki directly rather
than discovering one from a working directory.

## Preflight

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT is not set — is the plugin loaded?}"
```

## Step 0 — Resolve & session ID

Resolve the project wiki the same way every other skill does:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --cwd "$(pwd)"
```

If `source` is `none` or ambiguous, resolve it the same way `research`/`team`
do before continuing (offer to scaffold, or ask which registry entry).
`/session-close` never proceeds against an unresolved wiki — **STOP** if one
cannot be resolved.

Resolve the factory home:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" resolve-factory-home
```

Branch on `status` — this is the **opposite** of `/team`'s rule, which STOPs
outright when no factory home is registered:

- `ok` → note `factory_home`; continue with no restriction.
- `missing` or `absent` → set a session-scoped **DEGRADED** flag and
  **continue** (do NOT stop). Capture the JSON's `status` and `hint` fields —
  the two statuses are different problems (`absent` = no factory home was
  ever registered; `missing` = one is recorded but has vanished or lost its
  `agents/`/`teams/` dirs) and the `hint` carries the right remediation for
  each; it is surfaced to the user verbatim, the same way `/team` surfaces
  it. Nothing about sweep, the session page, decision pages, overview/log
  upkeep, or lint/reindex depends on a factory home — only Step 5 (the jot)
  does. DEGRADED means: skip Step 5, and make sure the session page's
  Bookkeeping section (Step 2) carries the warning line
  `factory home unavailable (<status>): <hint>` with the captured status and
  the hint text verbatim.

Derive the session ID:

```
<YYYY-MM-DD>-<headline-slug>
```

`YYYY-MM-DD` is today's date. `<headline-slug>` is a ≤6-word, lowercase,
hyphenated slug drafted from the session's main thread (what the user
actually worked on this session — not a generic word like "session"). State
the derived ID to the user before writing anything. This ID is the filename
stem of the session page written in Step 2 (`wiki/sessions/<ID>.md`) — deriving
it from the session's actual content, not from a counter or timestamp, is
what makes a re-run land on the same ID: the transcript being closed hasn't
changed, so the same headline produces the same slug, so a crashed close is
fixed by re-running the skill rather than by resuming some internal state.

**Every marker used in Steps 1–6 below is `<!-- session: <ID> -->`** — the
same literal comment, embedded in whatever text is being appended, is the
idempotency guard for every `append-once` call in this skill.

## Step 1 — Sweep (the sole guaranteed stub-creation point)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_ops.py" sweep-scan --wiki-root "<wiki-root>"
```

Returns `{"strays": [...], "raw_unmanifested": [...], "docs_path": ..., ...}`
(read-only; never writes anything itself). This is the **only** place in
`/session-close` — and, per the spec, the only guaranteed place in the whole
skill set — where a stub is created no matter what else happened this
session:

- **For each stray** (a `.md` file sitting outside `wiki/`, `raw/`, and
  `docs_path`): offer the user routing:
  - **Ingest it into the wiki** via the wiki's own ingest conventions
    (`/llm-wiki:wiki-ingest`), or
  - **Move it to `docs_path`** (resolved via
    `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --get-docs-path "<wiki-root>"`
    if not already known) and create a `source`-type stub for it.
- **For each unmanifested raw drop** (a `.md` file under `raw/` or
  `raw/snapshots/` that `raw/MANIFEST.md` doesn't mention): offer ingestion
  the same way.

Every stub created in this step follows the deliverable-stub contract: `type
source`, `external-ref:` pointing at the file, a one-paragraph summary,
`confidence: low`, and it is PII-gated before writing. `lint.py` gates real
files only — it has no stdin mode — so gate drafted content via a scratch
temp file:

1. Write the drafted stub to a temp file (e.g. under `$TMPDIR`).
2. Run
   `python3 "<wiki-root>/scripts/lint.py" --check-content "<temp-path>" --wiki-root "<wiki-root>"`.
3. Only on exit 0, write the real wiki page; on a nonzero exit, treat it
   exactly as `wiki-ingest` does (flag it, show the flagged spans, do not
   write).
4. Delete the temp file either way.

## Step 2 — Session page

Write (or overwrite) `wiki/sessions/<ID>.md` from
`${CLAUDE_PLUGIN_ROOT}/assets/entity-templates/session.md`. Because the
filename is the session ID from Step 0, re-running this step for the same
session lands on the same file — overwrite, don't append — which is what
makes it idempotent across a crash-and-retry.

Sections, filled per the template's own comments:

- **TL;DR** — exactly 3 bullets: what changed / what was decided / what was
  produced.
- **Needs your attention** — checklist for the human: approvals, blocked
  items, deferred judgment calls.
- **Decisions** — one bullet per decision made this session, each a
  `[[wikilink]]` to its decision page (written in Step 3).
- **Deliverables** — what was produced: stub links or docs paths.
- **Work units** — one entry per participating persona, each formatted
  **exactly**:
  ```
  - **<Name>**: <position in their own words>
  ```
  This is the pinned, machine-parsed shape (the same one `/team`'s
  prior-positions reader consumes) — **never paraphrase a persona's position
  into third person or summarize it down**; carry over its own words as
  written during the session.
- **Bookkeeping** — footer only: any warnings (including, when DEGRADED,
  Step 0's line `factory home unavailable (<status>): <hint>` — status and
  hint carried verbatim — noting the jot was skipped), any other skipped
  writes, and the session ID itself.

Set frontmatter `author:` to every persona that participated this session
(not just the primary one). Before writing, PII-gate the drafted content the
same way as Step 1's stubs — write the draft to a scratch temp file (e.g.
under `$TMPDIR`), run
`python3 "<wiki-root>/scripts/lint.py" --check-content "<temp-path>" --wiki-root "<wiki-root>"`,
and only on exit 0 write `wiki/sessions/<ID>.md`; delete the temp file either
way. If the gate fails, do not write the page; show the flagged spans and
offer pre-scrub the same way `wiki-ingest` does.

**Determinism guardrail (re-runs must be content-identical):** a re-run of
this step on unchanged session facts MUST reproduce the page byte-for-byte —
any diff on unchanged facts is a bug in the close, per the acceptance test.
Concretely:

- No wall-clock timestamps anywhere in the page — the only date is the
  session date already carried in the ID and frontmatter. `last-updated:` is
  pinned to the session date, never the write date.
- List Work units in team-YAML member order; list decisions and bullets in
  the order they occurred in the session.
- On a re-run, READ the existing `wiki/sessions/<ID>.md` first and preserve
  its content wherever the session facts haven't changed — only re-draft the
  parts whose underlying facts actually differ.

## Step 3 — Decisions & assumptions

For each decision actually made this session, create (or, on a same-ID
re-run, overwrite) `wiki/decisions/<YYYY-MM-DD>-<slug>.md` from
`${CLAUDE_PLUGIN_ROOT}/assets/entity-templates/decision.md`:

- Fill the lifecycle fields: `decided-by:` (the accountable owner, distinct
  from `author:`), **Options considered** with a stated reason for every
  option NOT chosen, and **Revisit when** (the trigger that would change the
  decision).
- **Positions** section uses the same pinned shape as the session page's Work
  units: `- **<Name>**: <position in their own words>` — every contributor's
  stance, dissent included, never paraphrased.
- Create-if-missing, same-slug-overwrite on re-run — never append a second
  copy of the same decision.

**Determinism guardrail (same as Step 2's):** a re-run on unchanged session
facts MUST reproduce each decision page byte-for-byte. No wall-clock
timestamps — the only date is the session date in the slug and frontmatter;
`last-updated:` is pinned to the session date, never the write date. Options
and Positions listed in the order they occurred (Positions in team-YAML
member order when multiple personas weighed in); on a re-run, READ the existing
page first and preserve its content wherever the facts haven't changed. Any
diff on unchanged facts is a bug in the close.

**If this decision supersedes an existing decision page:** on the OLD page,
set `superseded-by: [[new-decision-slug]]` and `status: superseded` in its
frontmatter, and add the wikilink under its **Supersedes**-adjacent context.
Agents do this reliably where humans routinely forget — do not skip it just
because the old page "still reads fine."

**Every `[hypothesis]`-tagged claim made this session** (per the wiki's claim
tags convention) gets an entry in the relevant `wiki/questions/` page with
concrete validation criteria — what would need to be true, or what test would
need to run, to move it to `[verified: YYYY-MM-DD]` or `[REFUTED]`. Create the
questions page from
`${CLAUDE_PLUGIN_ROOT}/assets/entity-templates/question.md` if none exists yet
for that theme.

When the target questions page **already exists**, add the new sub-question entry via
`python3 "$CLAUDE_PLUGIN_ROOT/scripts/session_ops.py" append-once "<questions-page>" --marker "<!-- session: <ID> -->" --heading "## Sub-questions" --text "..."` 
with the session marker embedded in the text — never a bare edit. This construction
prevents a crash-and-retry from duplicating the entry; only brand-new question pages
are plain create-if-missing.

## Step 4 — Overview & log upkeep

Append-once (marker = `<!-- session: <ID> -->`, embedded in the appended
text) onto two files:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_ops.py" append-once \
  "<wiki-root>/wiki/overview.md" \
  --marker "<!-- session: <ID> -->" \
  --heading "## What changed this quarter" \
  --text "- <one line summarizing this session's change> <!-- session: <ID> -->"
```

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_ops.py" append-once \
  "<wiki-root>/wiki/log/<YYYY-Qn>.md" \
  --marker "<!-- session: <ID> -->" \
  --text "## [$(date +%Y-%m-%d\ %H:%M)] session — [[<ID>]] | touched: [...] | <one narrative line> <!-- session: <ID> -->"
```

The log entry's shape matches the wiki's own log format (`## [YYYY-MM-DD
HH:MM] <verb> — [[slug]] | touched: [...] | <summary>`) with the session
marker appended so a re-run is a no-op rather than a duplicate line. Because
`append-once` checks for the marker anywhere in the file, re-running this
step after a crash never double-logs the same session. Match the TARGET file's
existing entry shape (e.g. `- YYYY-MM-DD — ...` bullets) rather than this
example's canonical heading form, when they differ — the file's own convention
wins.

If this session verified or refuted a claim that a `## Current theses` entry
in `overview.md` depends on, **flag that entry to the user** — name the
thesis, say what changed, and let the user decide whether/how to revise it.
Never silently rewrite a thesis as a side effect of session-close; that's
what makes `overview-refresh` a distinct, confirmation-gated skill.

## Step 5 — Factory-home jot

Provenance rule, held to verbatim:

> jot lines may only derive from user-authored turns in the session
> transcript — never from wiki pages, raw snapshots, or web content.

Scan the session transcript's **user** messages (not assistant output, not
persona output, not anything read from the wiki) for recurring-feedback
observations: corrections the user repeated, style directives, process
complaints — the kind of durable pattern a future session should already
know about. For each such observation:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_ops.py" jot-append \
  --home "<factory-home>" --session "<ID>" --date "<YYYY-MM-DD>" \
  --observation "<observation text>" --observation "<another, if any>" \
  --wiki "<wiki-root>"
```

`--wiki` takes the resolved wiki root path from Step 0 (per `jot_append`'s
docstring: "the wiki/project this call's observations concern — session-close
passes the resolved wiki path") — the path itself, not its basename or any
other derived form. It is provenance only, applied to every observation in
this call; omit it (never pass an empty string) if for some reason the wiki
root isn't at hand, since `jot_append` treats a falsy `--wiki` as "no
provenance" and omits the `"wiki"` key entirely rather than writing it empty.

`jot-append` dedups by construction — a second call with the same
`--session` is a whole-call no-op, so re-running this step after a crash
never double-jots.

When an observation is clearly about a specific persona's behavior, pass
`--persona <slug>` (repeatable) so `/improve review` can group it; general
process observations stay unclassified — omit `--persona` for those.

**If DEGRADED (Step 0):** skip this step entirely — do not attempt to write
under a factory home that is unavailable — and confirm the session page's
Bookkeeping section (Step 2) carries the warning line
`factory home unavailable (<status>): <hint>`, with Step 0's captured status
and its hint text verbatim, noting the jot was skipped.

## Step 6 — Lint + reindex

Run the wiki's **own** scripts (never the plugin's bundled copies — the
wiki's copies are what `wiki-init`/`factory-init` installed and what every
other skill lints against):

```bash
python3 "<wiki-root>/scripts/lint.py"
python3 "<wiki-root>/scripts/graphify_wiki.py" --wiki-root "<wiki-root>"
```

Surface any new lint errors to the user — do not silently swallow them; the
writes from Steps 1–5 already happened, so there's nothing to roll back, only
to flag for a manual fix. Lint's normal-mode run regenerates the wiki's
catalogs/index as a side effect; no separate step is needed for that.

## Step 7 — Idempotency (verbatim)

> A crashed close is fixed by re-running it; a completed close re-run is a
> no-op.

Every step above holds to this by construction: Step 2 and Step 3 are
same-slug overwrite / create-if-missing (the session and decision IDs are
derived from content, not a counter); Steps 1 and 6 are read-only-then-write
operations with no accumulating state across runs; Steps 4 and 5 are
marker-guarded appends via `append-once` / `jot-append`'s session dedup.
Nothing in this skill ever appends without a marker — if a step doesn't have
one, it's because it overwrites or creates-if-missing instead. Re-running
`/session-close` on a session that already closed cleanly should produce no
diff at all.
