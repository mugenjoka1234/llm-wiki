# Release notes — llm-wiki v0.2.0 (initial public release)

**Released:** 2026-07-12 · root commit `30c553a1`
**Changes:** 5 (baseline feature set)

> This is the **initial public release** — the starting state. There's no prior release to diff against, so this note is reconstructed from the shipped feature set (README + skills) rather than a git range. No analytics instrumentation, so `events_touched` is empty throughout.

---

## For the team

**chg-1 · The persistent wiki** — *feature*
A markdown knowledge base built on the [Karpathy LLM-wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): decision pages with lifecycle fields, trust-graded claims (`[verified]` / `[hypothesis]` / `[REFUTED]`), research digests, session logs, and entity pages. Every wiki is also an Obsidian vault. Surfaces: wiki knowledge base, Obsidian vault.
> ⚠️ needs human review: initial-release baseline reconstructed from the shipped feature set, not a git diff.

**chg-2 · The wiki skill set (Claude Code + Gemini CLI)** — *feature*
`research` (Haiku planner → no-LLM fetcher → Sonnet reader, URL-cited), `analyze`, `critique` (fidelity/challenge), `synthesize`, `query`, `wiki-ingest` (PII gate + digest + entity back-propagation), `wiki-lint`, `wiki-init`, `wiki-forget`, `overview-refresh`, `graphify-wiki`, and the `wiki` router. Surface: wiki subsystem skills.

**chg-3 · The factory layer (Claude Code only)** — *feature*
`/team` spawns persona teams with budgeted wiki context, self-authored attribution, and honest partial-panel disclosure; `/session-close` does idempotent session wrap-up; `/improve` proposes human-gated persona edits; `/factory-init` scaffolds a project and registers a factory home. Surfaces: /team, /session-close, /improve, /factory-init.

**chg-4 · Session hooks** — *feature*
A `SessionEnd` breadcrumb plus a `SessionStart` warning that nudges you to `/session-close` when the wiki has fallen behind the work; silent for non-wiki projects. Surface: session hooks.

**chg-5 · Six bundled research/analysis subagents** — *feature*
`wiki-planner`, `wiki-researcher`, `wiki-analyst`, `wiki-analyst-haiku`, `wiki-critic`, `wiki-synthesizer`. Surface: bundled agents.

---

## For stakeholders

llm-wiki launches with a simple premise: **your product knowledge should compound the way your code does.** Codebases have git; product decisions, research, and rejected options usually scatter across docs and heads where neither people nor AI agents can reliably find them.

The initial release ships two halves. **The wiki** is a persistent, human-browsable markdown knowledge base (open it in Obsidian, no terminal required) where knowledge accumulates instead of being re-discovered every session — with claims graded by how well they're sourced (chg-1, chg-2). **The factory** is a layer of AI persona teams that read that wiki with budgeted context, sign their own positions, close out sessions with minutes and decisions, and propose improvements to their own instructions that only you approve (chg-3). A lightweight session hook keeps the wiki from silently falling behind the work (chg-4).

You bring the vision and the judgment; the system runs the team and remembers everything.
