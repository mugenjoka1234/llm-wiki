---
name: wiki
description: Single entry point for all wiki operations. Routes any request to the right skill — no need to remember specific skill names or flags. Use when the user says anything wiki-related and isn't sure which skill applies, or just types "/llm-wiki:wiki <anything>".
---

# wiki router skill

The user shouldn't need to remember skill names. This skill classifies intent and dispatches to the right skill. It wraps — it does not replace — the underlying skills.

## Intent classification

Read the user's request and map it to one of these intents:

| Intent signals | Dispatch to |
|---|---|
| "research", "look up", "find out about", "what's the latest on", "investigate" | `/llm-wiki:research` |
| "what do we know", "tell me about", "what's the status", "summarize", "compare", "what are our gaps" | `/llm-wiki:query` |
| "ingest", "add this file", "add this source", "there's a new doc" | `/llm-wiki:wiki-ingest` |
| "analyze this", "read this and", "what's missing in", "risks in" | `/llm-wiki:analyze` |
| "critique", "verify", "challenge", "red-team", "fact-check" | `/llm-wiki:critique` |
| "synthesize", "combine", "pull together findings on", "make a summary page for" | `/llm-wiki:synthesize` |
| "health check", "lint", "is the wiki healthy", "any issues", "check the wiki" | `/llm-wiki:wiki-lint` |
| "create a wiki", "new wiki", "initialize", "scaffold" | `/llm-wiki:wiki-init` |
| "update the overview", "refresh the overview" | `/llm-wiki:overview-refresh` *(v1.1)* |
| "update the [type] summary", "make a [type] overview page" | `/llm-wiki:synthesize` with `--update --type <type>` |
| "deep dive", "thorough analysis", "exhaustive" | Dispatch the matching skill with `--deep` |

## Flag translation

Translate natural language modifiers to skill flags before dispatch:

| User says | Flag |
|---|---|
| "deep dive", "thorough", "exhaustive" | `--deep` |
| "update the existing page", "refresh the summary" | `--update` |
| "since last month", "what changed since [date]" | `--since YYYY-MM-DD` |
| "auto", "no need to confirm", "just do it" | `--auto` |

## Ambiguous requests

If the intent matches more than one skill, ask one clarifying question:

- "Do you want to **ask** the wiki something, or **add** something new to it?"
  - Ask → query
  - Add → ingest or research

- "Do you want a **quick answer** or a **saved synthesis page**?"
  - Quick answer → query
  - Saved page → synthesize

Never guess silently. One question is always better than the wrong dispatch.

## Passthrough

Once intent and flags are clear, invoke the target skill directly. Do not re-implement the target skill's logic here. The router's only job is classification + dispatch.

## Examples

```
/llm-wiki:wiki what do we know about Lightspeed?
→ /llm-wiki:query "what do we know about Lightspeed"

/llm-wiki:wiki research AI insights in POS 2025
→ /llm-wiki:research "AI insights in POS 2025"

/llm-wiki:wiki deep dive on competitor scheduling features
→ /llm-wiki:research --deep "competitor scheduling features"

/llm-wiki:wiki update the competitors summary
→ /llm-wiki:synthesize --update --type competitor

/llm-wiki:wiki is everything healthy?
→ /llm-wiki:wiki-lint

/llm-wiki:wiki there's a new PRD in raw/
→ /llm-wiki:wiki-ingest
```
