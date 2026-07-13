# llm-wiki

**A persistent wiki, plus an AI-factory layer on top.** A Claude Code plugin that dispatches specialist agents to research, analyze, critique, and synthesize — filing findings into a growing markdown wiki that compounds over time — and, once a factory home is registered, guides a user through staffing a team, spawns budgeted persona teams that read that wiki, close out sessions idempotently, and propose their own instruction edits for human approval.

Built on Karpathy's [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

## What you get

Twelve wiki skills, invokable from any Claude Code (or Gemini CLI, via the bundled shim) session once installed:

| Skill | What it does |
|---|---|
| `/llm-wiki:research` | Three-stage research: Haiku planner finds URLs → no-LLM fetcher snapshots them once → Sonnet reader synthesizes from disk with URL citations; offer to ingest. `--fetcher free\|firecrawl` (default `free`): choose the fetch backend. Firecrawl needs `FIRECRAWL_API_KEY`; if it fails, the run halts and asks you (no silent fallback) |
| `/llm-wiki:analyze` | Dispatch analyst on a local doc or wiki page; produce themes/gaps/risks |
| `/llm-wiki:critique` | Dual-mode: fidelity audit (page has sources) or contrarian challenge (page has none) |
| `/llm-wiki:synthesize` | Cross-page synthesis → new digest; never modifies existing pages |
| `/llm-wiki:query` | Answer a question from the wiki's pre-synthesized knowledge, with `[[wikilink]]` citations |
| `/llm-wiki:overview-refresh` | Rewrite `overview.md` in place after major ingest sessions, with diff + confirmation |
| `/llm-wiki:wiki-init` | Scaffold a new wiki (asks for domain, purpose, entity types, section names) |
| `/llm-wiki:wiki-lint` | Run deterministic lint (frontmatter, stale, orphans, PII gate) |
| `/llm-wiki:wiki-ingest` | Manual ingest fallback; also runs the PII gate |
| `/llm-wiki:wiki-forget` | Remove a wiki from the plugin registry (registry only — never deletes files) |
| `/llm-wiki:wiki` | Single entry point that classifies intent and routes to the right skill above |
| `/llm-wiki:graphify-wiki` | Build/query the wiki's semantic `_graph.json` index for targeted, line-range reads instead of full-file loads |

Six bundled specialist agents (wiki-planner, wiki-researcher, wiki-analyst, wiki-analyst-haiku, wiki-critic, wiki-synthesizer) — invoked by the skills above via plugin-namespaced subagent dispatch.

Five factory skills sit on top of the wiki skills once a factory home is
registered — four Claude-only, plus `/staff`, which also runs on the Gemini
CLI shim (with documented degradation):

### /llm-wiki:factory-init

Scaffolds or adopts a project for factory-backed work: the wiki (delegating
to `wiki-init`), a deliverables tree (`docs_path`), factory-home
registration, and default-team selection. Supersedes `wiki-init` for new
projects; `--adopt` brings an existing wiki up to date without touching its
content.

### /staff

Guides a user through staffing a whole team in one session, from an empty
(or partially staffed) factory home: a context-first interview against a
fixed 7-item checklist (confirm-or-correct from project/wiki/factory-home
context, one question at a time, coverage fixed but wording composed fresh),
a triage of any shared corp docs into working guidelines, persona-shaping
material, or a wiki-ingest offer (approval before any write, never
auto-ingest), a doctrine-driven slate proposal (decision coverage,
complementing the user's own expertise, tension by design, a domain
conscience, sharp-but-deferring boundaries, a small active bench, and
evidence-style diversity), and layered hiring — generic hires land in the
factory home's roster, client-flavored hires split into a project-level
persona copy at `<wiki-root>/personas/` instead. Candidates are sourced from
a bundled starter roster, the vendored ~270-persona `agency-agents` catalog,
and the factory home's own `references/`; every hire is validated and shown
as a diff before writing. `factory-init` hands off here when a roster is
empty; `/team recruit` remains the single-hire shortcut. Unlike the other
four factory skills, `/staff` also runs on the Gemini CLI shim: plain-text
questions instead of structured option pickers, unified diffs printed inline
for approval, and a closing note to open Claude Code for the first `/team`
session instead of a direct handoff. Use when the user says "/staff", "staff
my team", "help me hire", or "build my agent team".

### /team

Spawns AI Factory personas — a whole team or a single one — with budgeted
context from the current project's wiki (persona file + citation anchor
verbatim, index/overview + up to 5 focus-tag pages, up to 10 self-authored
prior positions), an identical attribution contract on every dispatch, and
honest disclosure of any member that couldn't be spawned. Requires a
registered factory home; STOPs with a remediation hint if none is registered.
Three forms:

- `/team <name>` — spawn the named team from the factory home's `teams/`
  directory and synthesize across all spawned members' outputs.
- `/team solo <persona> <question>` (or `"<persona-name>, what do you think
  about X?"`) — spawn a single persona directly, no synthesis.
- `/team recruit <role> for <task>` — draft a new persona (from the factory
  home's recruiting library, or from role + task when it's empty), validate
  it, show the user a diff before saving it to the roster, and offer team
  membership.

### /session-close

Closes out a working session against the current project's wiki: sweeps
stray files and unmanifested raw drops (the only guaranteed stub-creation
point), writes/refreshes the session page and any decision pages, keeps
`overview.md` and the quarterly log current, jots durable user-feedback
patterns to the factory home, then re-lints and reindexes the wiki. Every
step is idempotent — a crashed close is fixed by simply re-running it; a
completed close re-run is a no-op. Use when the user says "wrap up", "close
the session", "done for today", or invokes `/session-close`.

Unlike `/team`, a missing or unregistered factory home does not stop the
run — it degrades gracefully: everything except the factory-home jot still
happens, and the session page's Bookkeeping section notes that the jot was
skipped and why.

An unclosed-session detector runs automatically: a SessionEnd hook records
an activity breadcrumb for the current wiki, and the next SessionStart
warns if that breadcrumb is newer than the wiki's last recorded session
page — a nudge to run `/session-close` before the wiki falls behind. It is
silent for non-wiki projects and for wikis that are already caught up.

### /improve

Reviews the factory home's pattern jot (`patterns/pattern-log.jsonl`,
appended by `/session-close`), groups the observations by persona, and
proposes a minimal edit to each affected persona's mutable sections as a
unified diff — the verbatim triggering observation(s) quoted above every
diff. Agents propose, never apply: nothing is written until the user
approves that specific diff. A deterministic guard
(`team_ops.py anchors-unchanged`) verifies the fenced Immutable Anchors
survived byte-for-byte before any write; catching an adversarial or wrong
edit to the *unfenced* text is still the human diff review's job, not the
guard's. Approved edits are written atomically and committed to the factory
home's git repo one persona at a time — the commit is the change log,
`git revert` is the rollback. Like `/team`, requires a registered factory
home and STOPs with a remediation hint if none is registered or if the home
isn't a git repository; also requires a clean working tree before proposing
anything. Use when the user says "/improve review", "review the pattern
log", "improve the personas", or asks whether recurring feedback should
change how a persona behaves.

## Install

```bash
claude plugin marketplace add mugenjoka1234/llm-wiki
claude plugin install llm-wiki@llm-wiki
```

Or from inside a session: `/plugin` → browse marketplaces → `llm-wiki`.

While iterating on the plugin itself, load it locally from a checkout instead:

```bash
claude --plugin-dir ~/llm-wiki/plugin/
```

After any edit to a locally-loaded plugin: `/reload-plugins` in-session.

## First use

```
cd ~/wherever-you-want-the-wiki
claude
# In-session:
/llm-wiki:research <your topic>
```

The plugin detects no wiki, offers to scaffold one in cwd, then continues the research flow. First-time experience is single-command.

## Architecture

- **Skills** orchestrate workflows (`skills/<name>/SKILL.md`).
- **Agents** specialize — each has a tightly-scoped role, tool set, and output schema (`agents/*.md` with YAML frontmatter).
- **Helper scripts** (`scripts/*.py`, stdlib-only Python 3) handle wiki resolution, prompt assembly, output validation, and source fetching.
- **Bundled assets** (`assets/`) include meta-templates for CLAUDE.md / README.md / 10 entity templates / `lint.py` — copied into each new wiki at scaffold time.

### Research pipeline (split-stage)

`/llm-wiki:research` runs as three stages, so the expensive model only ever reads — it never fetches:

```
plan (Haiku, wiki-planner)  →  fetch (fetch_sources.py, no LLM)  →  read (Sonnet, wiki-researcher)
```

1. **Plan** — `wiki-planner` (Haiku) turns the question into a ranked, deduped list of source URLs (`WebSearch`, or `firecrawl search` when `--fetcher firecrawl` is active). It never fetches page bodies.
2. **Fetch** — `fetch_sources.py` (no model involved) fetches each URL exactly once and writes a clean markdown snapshot to `raw/snapshots/<slug>-<date>.md` with a YAML front-block recording the original `source_url`, plus a `fetch-manifest.json`. The default `FreeFetcher` does `urllib` → readability-style main-content extraction, escalating to Playwright on empty/403/thin results. The opt-in `FirecrawlFetcher` (`--fetcher firecrawl` + `FIRECRAWL_API_KEY`) shells out to the Firecrawl CLI's documented skill contract instead of reimplementing its API.
3. **Read** — `wiki-researcher` (Sonnet) has no web tools at all (`Read`, `Grep` only) — it synthesizes strictly from the saved snapshots, citing each one's `source_url`. It may request one round-2 fetch via `<need-more>`, capped at 2 rounds by default (3 with `--deep`).

Firecrawl failures never silently fall back to the free path — the run halts and asks you to retry, switch backends, or abort (FC-16).

## Multi-wiki support

Registry at `${CLAUDE_PLUGIN_DATA}/registry.txt` tracks known wikis. Skills resolve the target wiki from current directory first, then registry; respect Claude Code's session-scope permissions.

## Model costs (approximate)

Per typical usage (~5 research + 3 analyze + 1 critique + 1 synthesize per week):

- research: ~$5–6/mo (haiku planner + free-tier fetch + sonnet reader, maxTurns 6/—/20)
- analyze: ~$1.40/mo (sonnet, local only, maxTurns 8; haiku auto-routed for docs <5KB)
- critique: ~$3.30/mo (opus — accuracy-critical fidelity reasoning, maxTurns 20)
- synthesize: ~$1.10/mo (sonnet, opus auto at >20 pages, maxTurns 12)

**~$11–13/mo total.** Switching research to `--fetcher firecrawl` adds Firecrawl API cost (500 free fetches, then paid) in exchange for higher-fidelity extraction.

## Spec + design docs

- Plugin spec: `docs/superpowers/specs/2026-05-07-llm-wiki-plugin-design.md`
- Implementation plan: `docs/superpowers/plans/2026-05-07-llm-wiki-plugin-implementation.md`
- Wiki-pattern spec: `docs/superpowers/specs/2026-05-06-llm-wiki-design.md`
- Split-stage research pipeline spec: `docs/superpowers/specs/2026-07-03-split-stage-research-pipeline-design.md`
- Split-stage research pipeline implementation plan: `docs/superpowers/plans/2026-07-03-split-stage-research-pipeline.md`

## Roadmap

- Per-wiki agent override verification
- Post-ingest/post-research hooks (`PostToolUse`-driven auto-lint, auto-ingest)

## License

MIT.
