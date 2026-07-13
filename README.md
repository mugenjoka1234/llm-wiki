# llm-wiki

**Institutional memory for AI agents — and the agent team that uses it.**

Great PMs don't remember everything; they run a process: write decisions down, record who dissented, brief the team before the meeting, review the work. Your codebase has git — but your product knowledge (decisions, research, rejected options, "what would change our mind") usually lives in scattered docs and heads, where neither humans nor AI agents can reliably find it.

llm-wiki is that process, packaged as a Claude Code plugin, in two halves:

- **The wiki (the memory):** a persistent markdown knowledge base — decision pages with lifecycle fields, trust-graded claims (`[verified]` / `[hypothesis]` / `[REFUTED]`), research digests, session logs. Based on the [Karpathy LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): knowledge compounds instead of being re-discovered every session. Every wiki is an **Obsidian vault** — you browse your team's knowledge in a friendly app, no terminal required.
- **The factory (the organization):** persona teams that read that wiki with budgeted context, sign their own positions (agents are never paraphrased), close out sessions idempotently — minutes, decisions, action items — and propose improvements to their own instructions that only *you* can approve.

**You bring the vision, the problem statements, and the judgment on results. The system runs the team — and remembers everything.**

## Who this is for

- **PMs, UX researchers, strategists** — people whose work has no natural git. You get a staffed agent team, a documentation structure, and context that survives between sessions, out of the box. Interaction happens in Obsidian and plain markdown; the CLI footprint is two install commands.
- **Engineers supporting them** — or building products where the agent needs more than code: the *why* behind the feature, not just the what.
- **Anyone new to agent workflows** — the basics are taken care of: context preservation, specialist subagents from day one, and a filing discipline you don't have to invent.

---

## Install

```bash
claude plugin marketplace add mugenjoka1234/llm-wiki
claude plugin install llm-wiki@llm-wiki
```

Or from inside a Claude Code session: `/plugin` → browse marketplaces → `llm-wiki`.

After editing a local checkout of the plugin: `/reload-plugins` in-session.

## Requirements

- **Claude Code.** All 16 skills work there.
- **python3** — standard library only. No `pip install` needed for any bundled script.
- **git** — each wiki and each factory home is its own git repo (history + rollback).
- **Gemini CLI** — the wiki skills (research, analyze, critique, synthesize, query, wiki-init, wiki-lint, etc.) work there too via the bundled shim (`plugin/GEMINI.md`); the four factory skills (`factory-init`, `/team`, `/session-close`, `/improve`) are Claude Code-only.

## Quick start

```bash
# Just want a wiki? Scaffold one in the current directory:
/llm-wiki:wiki-init

# Want the full setup — wiki + a deliverables tree + factory-team registration?
/llm-wiki:factory-init
```

Three layers, one owner each:

- **The plugin** (this repo) is machinery only — skills, agents, and scripts. It ships with zero personas and zero project knowledge.
- **Your factory home** (a separate local directory you register once, e.g. `~/my-factory/`) holds *your* personas and team compositions. It's registered data, never shipped with the plugin.
- **Each project** owns one wiki plus a deliverables tree — the only place agents read project facts from.

---

## Skills

12 skills in the wiki subsystem plus 4 Claude-only skills in the factory subsystem — 16 total.

### Wiki subsystem (Claude Code + Gemini CLI)

| Skill | What it does |
|---|---|
| `/llm-wiki:wiki-init` | Scaffold a new llm-wiki in the current directory |
| `/llm-wiki:wiki-lint` | Deterministic health check (frontmatter, stale pages, orphans, PII gate); also handles Obsidian setup |
| `/llm-wiki:research` | Three-stage pipeline — Haiku planner finds URLs, a no-LLM fetcher snapshots them once, Sonnet reader synthesizes with URL citations — then offers to ingest |
| `/llm-wiki:analyze` | Analyze a local document or wiki page — themes, gaps, risks, implications; routes small docs to Haiku automatically |
| `/llm-wiki:critique` | Critique a wiki page — fidelity audit against cited sources, or a web challenge when it has none |
| `/llm-wiki:synthesize` | Cross-page synthesis into a new digest; never modifies existing pages |
| `/llm-wiki:query` | Answer a question from the wiki's pre-synthesized knowledge, with `[[wikilink]]` citations |
| `/llm-wiki:overview-refresh` | Rewrite `wiki/overview.md` in place after major ingest sessions, with diff + confirmation |
| `/llm-wiki:wiki-ingest` | Ingest a raw source file — PII gate, digest, entity-page updates, log append |
| `/llm-wiki:wiki-forget` | Remove a wiki from the plugin registry (registry only — never deletes files) |
| `/llm-wiki:wiki` | Single entry point — classifies intent and routes to the right skill above |
| `/llm-wiki:graphify-wiki` | Build/query the wiki's semantic `_graph.json` index for targeted, line-range reads instead of full-file loads |

### Factory subsystem (Claude Code only)

| Skill | What it does |
|---|---|
| `/llm-wiki:factory-init` | Scaffold or adopt a project — wiki, deliverables tree, factory-home registration, default-team selection |
| `/team` | Spawn a persona team (or a single persona) with budgeted wiki context, honest partial-panel disclosure, and self-authored attribution; also recruits new personas |
| `/session-close` | Idempotent session wrap-up — sweep stray files, refresh the session page and overview, jot durable feedback patterns to the factory home, re-lint |
| `/improve` | Review the factory home's pattern jot and propose persona edits as human-approved diffs, one commit per persona |

## Hooks

A `SessionEnd` hook records an activity breadcrumb for the current wiki; the next `SessionStart` warns if that breadcrumb is newer than the wiki's last recorded session page — a nudge to run `/session-close` before the wiki falls behind. It stays silent for non-wiki projects and wikis that are already caught up.

---

## What's in this repo

```
llm-wiki/
├── plugin/              ← The reusable Claude Code plugin (install this)
└── drafts/              ← Working notes from the design phase
```

Each wiki you create with `/llm-wiki:wiki-init` is its own standalone directory with its own git history and its own Obsidian vault — separate from this outer repo, which only contains the plugin. Your factory home (personas + teams) lives in yet another directory outside this repo entirely.

---

## Set up Obsidian for a wiki

Obsidian is the visual reader — it renders the Dataview tables in `wiki/index.md` and shows the wikilink graph.

### Install

```bash
brew install --cask obsidian
```

### Open a wiki as a vault

1. Open Obsidian
2. Click **"Open folder as vault"**
3. Navigate to the wiki folder and select it
4. Click **Open**

### Configure settings (do this once per vault)

Open Obsidian Settings (`⌘,`) and configure:

| Section | Setting | Value |
|---|---|---|
| Files and links | Default location for new attachments | `raw/assets/` |
| Files and links | Use `[[Wikilinks]]` | ON |
| Files and links | New link format | Shortest path when possible |
| Community plugins | Dataview | Install + enable (required for index views) |
| Community plugins | Templates | Enable (core plugin) → set folder to `_templates/` |
| Hotkeys | Download attachments for current file | `Cmd+Shift+D` |

### Verify it works

Open `wiki/index.md`. The Competitors, Initiatives, JTBDs etc. sections should show as **live tables** (not raw code blocks). If they show as code, Dataview isn't enabled — go back to Community Plugins and enable it.

### Install Web Clipper (browser extension)

1. Install **Obsidian Web Clipper** from your browser's extension store
2. Open the extension settings → **Templates → Default**
3. Set **Note location** to `raw/`
4. Set **Vault** to the vault name
5. Test: clip any web article — it should save a markdown file into `raw/`

---

## Wiki quick reference

### Day-to-day operations

```bash
cd ~/wherever/<your-wiki>

# Health check
python3 scripts/lint.py

# Ingest a file already in raw/
# → tell Claude: "ingest raw/<filename>"

# Research a topic
# → tell Claude: "research <topic>"

# Check wiki status
cat wiki/_health.md
```

### When Obsidian index is empty

If `wiki/index.md` shows empty tables after you add pages:
1. Press `Cmd+P` in Obsidian
2. Search for **"Dataview: Rebuild current index"**
3. Run it — tables should populate immediately

### Default entity types

`wiki-init` scaffolds these 9 types by default — customize the list per wiki when prompted:

| Type | Filename pattern | Purpose |
|---|---|---|
| competitor | `shopify-competitor.md` | Named competitors |
| initiative | `large-catalog-initiative.md` | Strategic programs |
| jtbd | `build-orders-jtbd.md` | Jobs-to-be-Done |
| feature | `bulk-edit-feature.md` | Product features |
| segment | `power-users-segment.md` | Aggregate audience patterns (no PII) |
| experiment | `2026-Q2-onboarding-ab-experiment.md` | A/B tests |
| metric | `activation-rate-metric.md` | Measurable quantities |
| decision | `2026-05-06-kill-feature-x-decision.md` | Roadmap decisions (ADR-style) |
| source | (in `wiki/digests/`) | One per ingested source |

### Frontmatter must be valid YAML

Wikilink lists use **multi-line form**:

```yaml
sources:
  - "[[digest-shopify-q3]]"
  - "[[digest-other]]"
```

**Not** `sources: [[digest-shopify-q3]], [[digest-other]]` — that's invalid YAML and breaks Obsidian's Dataview parsing.

---

## Multi-wiki setup

Each wiki lives in its own folder, each is a separate Obsidian vault, each has its own git repo. The plugin tracks known wikis in a registry.

```bash
# Create a second wiki:
mkdir ~/wikis/notes
cd ~/wikis/notes
claude
# → /llm-wiki:wiki-init

# Switch wikis: open Obsidian, use vault switcher (bottom-left) to switch vaults
```

To open a second wiki in Obsidian: **Manage vaults** (icon in bottom-left corner) → **Open folder as vault** → select the new wiki folder.

---

## Status

Personal-use testing phase. This plugin was built for one person's workflow and is being shared as-is. Feedback, issues, and PRs are welcome, but expect rough edges.

## Tests

```bash
cd plugin && python3 -m unittest discover -s scripts/tests
```

## License

MIT.
