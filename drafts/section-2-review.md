# LLM Wiki — Section 2 Review Draft (v2, revised after expert reviews)

**Status:** Revised draft for user review before approval
**Date:** 2026-05-06
**Revision:** v2 — incorporates 17 recommendations from AI Engineer (workflow robustness) and Technical Writer (templates/IA) reviews.
**Context:** Section 1 approved. This covers templates, frontmatter, CLAUDE.md workflows. Once approved, Section 3 (skill design + Obsidian setup + implementation plan) follows.

---

## What changed in v2 (diff summary)

**Workflow robustness (A1–A7):**
- A1 — Ingest is now transactional via a plan file (`raw/_ingest/<slug>.plan.md`)
- A2 — PII scrub combines LLM semantic pass + deterministic regex gate + blocklist
- A3 — Pre-scrub approval is captured as auditable frontmatter on the scrubbed file, with mandatory diff summary
- A4 — Query has an explicit page-selection heuristic (index → frontmatter grep → top-5 → wikilink fan-out), capped at ~15 pages
- A5 — Lint split into Pass A (deterministic script) + Pass B (LLM per-type with confidence scores)
- A6 — Log format adds `touched:` array + one-line change summary
- A7 — New `wiki/_health.md` regenerated on every lint

**Templates & IA (B1–B10):**
- B1 — Heading normalization: Strengths/Weaknesses for "Pros/Cons"; Trade-offs-accepted for Decisions; `jtbd` "Friction points" → "Pain points" (matches Segment)
- B2 — `feature.md` gains a **Status** section
- B3 — Frontmatter adds `quarter`, `okr`, `confidence`; defers `external-ref` until wiki #2 exists
- B4 — Open Questions now uses dated checkbox format: `- [ ] YYYY-MM-DD — question (source: [[digest-...]])`
- B5 — Digest template tightened: Summary capped at 2 sentences; every Key-claim bullet requires a `→ [[entity-page]]` destination; adds **Not captured** section
- B6 — New `_templates/overview.md` for synthesis pages (`overview.md`, `glossary.md`)
- B7 — New `docs/schema-decisions.md` (ADR log for the wiki's own schema evolution)
- B8 — New `README.md` at wiki root (human-facing "how to read this wiki")
- B9 — Explicit link-hygiene rule in CLAUDE.md
- B10 — Missing inline section hints filled in (`competitor.md`, `feature.md`)

---

## Recap: what Section 1 locked in

- Per-domain wikis. First: `~/llm-wiki/research/`. Each wiki is a standalone git repo + Obsidian vault.
- Flat entity structure in `wiki/` root. Two exceptions: `wiki/digests/` (one page per ingested source) and a Segments entity type (no individuals — aggregate-only).
- Special subdirs: `wiki/_drafts/`, `wiki/_archive/`, `wiki/log/` (quarterly files), `wiki/_pii/` (gitignored blocklist; new in v2), `_templates/` (schema, visible, sorts last).
- Day-1 pages: `index.md`, `overview.md`, `glossary.md`, `people.md`, `_health.md` (new in v2), `README.md` (new in v2).
- `raw/` with `MANIFEST.md`; binaries gitignored; MANIFEST.md versioned.
- 9 entity types: **Competitors, Initiatives, JTBDs, Features, Segments, Experiments, Metrics, Decisions, Sources** (Sources = digests under `wiki/digests/`).
- 10 templates in `_templates/`: 9 entity templates + `overview.md` for synthesis pages.
- PII: dual workflow. Pre-scrub is default when Claude detects PII risk; user can override per-source.
- Review granularity: summary per ingest; full-review diff per page on lint.

---

## 2.1 Frontmatter schema (every entity page)

```yaml
---
type: competitor          # competitor | initiative | jtbd | feature | segment | experiment | metric | decision | source
status: active            # active | archived | superseded | draft | running | complete | shipped | planned | deprecated
last-updated: 2026-05-06
quarter: 2026-Q2          # NEW (B3) — the quarter this page is most relevant to; enables quarterly views
okr: [P&S-feature-usage]  # NEW (B3) — list of OKR IDs (from CLT 2026 scorecard); enables "which initiatives have no OKR link?"
confidence: med           # NEW (B3) — high | med | low. Critical on JTBDs, segments, metrics where claims rest on 1-2 sources.
sources: [[digest-shopify-q3-earnings]], [[digest-industry-report-2026]]
related: [[jtbd-manage-large-catalog]], [[feature-bulk-edit]]
tags: [catalog, omnichannel]
---
```

**Synthesis pages** (`overview.md`, `glossary.md`) also include:
```yaml
as-of: 2026-05-06         # when this synthesis was last rewritten (not just edited)
```

**Source digests** also include:
```yaml
source-path: raw/2026-04-15-customer-interview-032.pdf
ingested: 2026-05-06
pii-workflow: pre-scrub   # pre-scrub | scrub-at-ingest
scrub-approved-by: user   # NEW (A3) — only when pii-workflow = pre-scrub
scrub-approved-at: 2026-05-06T14:22
```

**Deferred (not added in v2):** `external-ref:` — only becomes valuable once wiki #2 exists. Adding dead fields is a tax.

---

## 2.2 Required prose sections (every entity page)

- **Overview** — 2-4 sentences. What this is, why it matters.
- **Open questions** — dated checkbox format (B4). Always present; may be a single line containing just `_none_`.

Open-questions format:
```markdown
## Open questions
- [ ] 2026-05-06 — Does Shopify's POS Pro include inventory sync with OLS out of the box? (source: [[digest-shopify-q3-earnings]])
- [ ] 2026-05-06 — What's the revenue cutoff where high-volume customers adopt dedicated ERP? (source: _none_ yet)
- [x] 2026-04-20 — ~~How does Clover handle multi-location inventory?~~ → answered in [[clover-competitor]]
```

Why: the checkbox makes closure explicit; the date makes staleness queryable ("open questions older than 90 days" is a Dataview view worth adding to `index.md`). Without this, Open Questions becomes a junk drawer.

Everything below these two required sections is type-specific free-form.

---

## 2.3 Template skeletons (10 total)

All live in `_templates/`. Claude copies the template when creating a new page, fills in frontmatter, and adapts the body.

**Normalized heading conventions (B1), enforced in CLAUDE.md:**
- Use **Strengths / Weaknesses** for competitor-like pros/cons.
- Use **Trade-offs accepted** when analyzing a decision's costs.
- Use **Pain points** (not "Friction points") for user-side difficulties.
- Use **Caveats & limitations** for a metric's definition/data issues (distinct concept from weaknesses or trade-offs).
- New headings must pattern-match to the above; Claude should not invent synonyms.

### `_templates/competitor.md`

```markdown
---
type: competitor
status: active
last-updated: TBD
quarter: TBD
okr: []
confidence: med
sources: []
related: []
tags: []
---
# {{Name}}

## Overview
<!-- 2-4 sentences: what they do, who they target, why they matter to us -->

## Pricing & packaging
## Positioning
## Strengths
## Weaknesses
## Relevant to us
<!-- B10: Scope of this section — concrete tie-ins to our [[initiative-*]], [[jtbd-*]], or [[feature-*]] pages.
     Only capture parallels that shift OUR priorities, not every analogy. -->

## Recent moves
<!-- Public launches, pricing changes, earnings highlights. Date each item. -->

## Open questions
- [ ] YYYY-MM-DD — question (source: [[digest-...]])
```

### `_templates/initiative.md`

```markdown
---
type: initiative
status: active
last-updated: TBD
quarter: TBD
okr: []
confidence: med
sources: []
related: []
tags: []
---
# {{Initiative name}}

## Overview

## Strategic rationale
<!-- Why this matters — tie to OKRs, JTBDs, metrics -->

## Scope & boundaries
<!-- What's in, what's out. Link to related [[feature-*]] pages. -->

## Success metrics
<!-- Wikilinks to [[metric-*]] pages, with target values if set -->

## Status & milestones

## Dependencies & risks

## Open questions
- [ ] YYYY-MM-DD — question (source: [[digest-...]])
```

### `_templates/jtbd.md`

```markdown
---
type: jtbd
status: active
last-updated: TBD
quarter: TBD
okr: []
confidence: med
sources: []
related: []
tags: []
---
# {{JTBD statement — "When ___ I want to ___ so I can ___"}}

## Overview

## Segments that prioritize this
<!-- Wikilinks to [[segment-*]] pages -->

## Current solutions & workarounds

## Pain points
<!-- B1: renamed from "Friction points" to match segment.md.
     Evidence: wikilinks to [[digest-*]] pages. Segment-level claims only. -->

## Features that address this
<!-- Wikilinks to [[feature-*]] pages with coverage notes -->

## Open questions
- [ ] YYYY-MM-DD — question (source: [[digest-...]])
```

### `_templates/feature.md`

```markdown
---
type: feature
status: active          # active | shipped | planned | deprecated | archived
last-updated: TBD
quarter: TBD
okr: []
confidence: med
sources: []
related: []
tags: []
---
# {{Feature name}}

## Overview

## Problem / JTBD served
<!-- Wikilink to [[jtbd-*]] -->

## Behavior
<!-- B10: What the feature DOES from a user's point of view — the interaction model.
     Scope of this section: happy path + key edge cases. NOT implementation. NOT rollout plans. -->

## Scope
<!-- B10: The boundaries of the feature — which platforms, which user tiers, which regions.
     Distinct from Behavior because it's about reach, not interaction. -->

## Status                                  <!-- B2: NEW in v2 -->
<!-- Where this feature is in its lifecycle. If the parent initiative tracks progress in detail,
     link there and keep this short: "Tracked on [[initiative-large-catalog]] milestones." -->

## Related features / alternatives
<!-- Competitor parallels, internal adjacencies -->

## Open questions
- [ ] YYYY-MM-DD — question (source: [[digest-...]])
```

### `_templates/segment.md`

```markdown
---
type: segment
status: active
last-updated: TBD
quarter: TBD
okr: []
confidence: med
sources: []
related: []
tags: []
---
# {{Segment name}}

## Overview
<!-- AGGREGATE ONLY. No individuals.
     Size, spend tier, vertical, channel mix, tool sophistication. -->

## Pain points
<!-- Segment-level claims with [[digest-*]] wikilinks -->

## JTBDs they prioritize

## What they currently use / switch from

## Opportunities for us

## Open questions
- [ ] YYYY-MM-DD — question (source: [[digest-...]])
```

### `_templates/experiment.md`

```markdown
---
type: experiment
status: running         # running | complete | cancelled | archived
last-updated: TBD
quarter: TBD
okr: []
confidence: med
sources: []
related: []
tags: []
---
# {{YYYY-QN slug}} — {{Short name}}

## Hypothesis
<!-- "If we <change>, then <metric> will <direction> because <reason>" -->

## Design
<!-- Variants, audience, duration, sample-size target -->

## Success criteria
<!-- Which [[metric-*]] moves, by how much, with what confidence -->

## Results
<!-- Fill on completion; until then: "pending" -->

## Decision / next step
<!-- Wikilink to [[decision-*]] if one was made -->

## Open questions
- [ ] YYYY-MM-DD — question (source: [[digest-...]])
```

### `_templates/metric.md`

```markdown
---
type: metric
status: active
last-updated: TBD
quarter: TBD
okr: []
confidence: med
sources: []
related: []
tags: []
---
# {{Metric name}}

## Definition
<!-- Exact formula, data source, slice dimensions -->

## Current value & trend
<!-- Last known + window; wikilink to source digest -->

## Targets & thresholds
<!-- 2026 OKR target if applicable; historical benchmarks -->

## Related initiatives & experiments
<!-- What moves this metric -->

## Caveats & limitations
<!-- B1: renamed from "Known caveats".
     Definition gotchas, data quality issues, known biases. Distinct from weaknesses. -->

## Open questions
- [ ] YYYY-MM-DD — question (source: [[digest-...]])
```

### `_templates/decision.md`

```markdown
---
type: decision
status: active          # active | superseded | reversed
last-updated: TBD
quarter: TBD
okr: []
confidence: high
sources: []
related: []
tags: []
---
# {{YYYY-MM-DD}} — {{Decision headline}}

## Context
<!-- What was the situation that forced a decision? -->

## Options considered
<!-- Bullet each with pros/cons -->

## Decision
<!-- What was chosen -->

## Rationale
<!-- Why. Capture the reasoning so future-you doesn't relitigate. -->

## Trade-offs accepted

## Supersedes
<!-- Wikilink to any prior [[decision-*]] this replaces -->

## Open questions
- [ ] YYYY-MM-DD — question (source: [[digest-...]])
```

### `_templates/source.md` (for pages in `wiki/digests/`) — **B5 tightened**

```markdown
---
type: source
status: active
last-updated: TBD
source-path: raw/<filename>
ingested: YYYY-MM-DD
pii-workflow: scrub-at-ingest     # or pre-scrub
scrub-approved-by:                # only set if pre-scrub
scrub-approved-at:                # only set if pre-scrub
quarter: TBD
okr: []
confidence: med
sources: []
related: []
tags: []
---
# {{Source title}}

## Summary
<!-- B5: HARD CAP at 2 sentences. The wiki's synthesis lives on entity pages,
     not here. A digest that summarizes competes with [[overview]]. -->

## Key claims
<!-- B5: Each bullet MUST include a destination: `→ [[entity-page]]`.
     If a claim has no destination, either it's not a claim or a new page is needed.
     NO PII. Claims expressed at segment level, not individual level. -->

- Claim text. → [[entity-page]]
- Another claim. → [[other-entity]]

## Verbatim quotes (if any)
<!-- Only if truly valuable. Public sources only. Never quote private PII. -->

## Not captured                     <!-- B5: NEW in v2 -->
<!-- One-line notes of what was in the source but deliberately excluded:
     PII (per scrub rules), off-topic material, redundant with existing pages.
     Helps lint detect under-extraction — "why is this 40-page interview only 3 claims?" -->

## Open questions
- [ ] YYYY-MM-DD — question (source: [[digest-...]])
```

### `_templates/overview.md` — **B6: NEW in v2** (used by `wiki/overview.md` and `wiki/glossary.md`)

```markdown
---
type: synthesis            # overview | glossary
status: active
last-updated: TBD
as-of: TBD                 # when this synthesis was last rewritten (not just edited)
quarter: TBD
okr: []
confidence: high
sources: []
related: []
tags: []
---
# {{Overview title — e.g. "Research Wiki — Current Synthesis"}}

## As of
<!-- Human-readable: "Rewritten 2026-04-30. Edited 2026-05-06."
     Tells the reader if this is current. -->

## What changed this quarter
<!-- Bullet list of major synthesis shifts since last rewrite. -->

## Top 5 entities to know
<!-- Highest-leverage wikilinks right now. -->

## Open strategic questions
<!-- Segment-level: the hardest things we don't know.
     Not the same as Open questions on entity pages — this is the meta-set. -->

## Current theses
<!-- 3-7 short claims summarizing our current synthesis. -->
```

---

## 2.4 CLAUDE.md outline (revised — the rulebook)

CLAUDE.md will be ~500-700 lines, structured as:

```
# LLM Wiki — Research (schema & workflows)

## Purpose

## Hard rules
- raw/ is immutable
- No PII in wiki/, digests/, or _templates/
- Every entity page has required frontmatter + Overview + Open questions
- Wikilinks in frontmatter sources/related; relative paths only for raw/ assets   (B9)
- Dates in frontmatter, not filenames (except decisions/experiments)
- New section headings must match the style guide (Strengths/Weaknesses,
  Trade-offs, Pain points, Caveats & limitations) — do not invent synonyms (B1)

## Directory layout

## Entity types & templates
- Table: 9 types → template paths → primary use → canonical section names

## Naming conventions
- kebab-case; type-suffix disambiguation; date-prefix for decisions/experiments

## Frontmatter spec
- Field-by-field allowed values; quarter/okr/confidence guidance

## Style guide for section naming                                                (B1)
- Canonical forms and when to use each

## Workflows

### Ingest — low-sensitivity source (scrub-at-ingest)                            (A1)
1. Read source from raw/
2. Write an ingest plan to raw/_ingest/<slug>.plan.md:
   - target_pages: [list with checkbox]
   - new_pages: [list with checkbox]
   - digest_path: wiki/digests/<slug>.md
   - frontmatter_updates: { page → { sources: [+...], related: [+...] } }
3. Discuss key takeaways with user (1-2 paragraphs)
4. PII scrub (LLM semantic pass + deterministic regex gate, rules below)         (A2)
5. Write wiki/digests/<slug>.md (check box in plan)
6. Update each target entity page (check box per page in plan)
   - For frontmatter-only updates, read only the frontmatter block, not full body
7. Append log entry to wiki/log/<current-quarter>.md                             (A6)
   - Format: ## [YYYY-MM-DD HH:MM] ingest — [[slug]] | touched: [p1, p2, ...] | <one-line summary>
8. Mark MANIFEST entry as ingested
9. Delete the ingest plan file
10. Report to user: summary of pages touched + one-line changes

Recovery: if the session ends mid-ingest, on resume Claude reads the plan file,
determines which boxes are checked, and continues from the first unchecked box.

### Ingest — sensitive source (pre-scrub)                                        (A3)
1. Read source from raw/
2. Produce scrubbed copy at raw/_scrubbed/<slug>.md
3. Produce a mandatory diff summary: "Redacted 4 names, 2 phone numbers, 
   1 address. Quasi-ID risks: 'floral retailer in SF'."
4. Show user the scrubbed file + diff summary
5. On user approval, write frontmatter fields to the scrubbed file:
     scrub-approved-by: user
     scrub-approved-at: <ISO-8601 timestamp>
6. No approval = hard stop. No fallback to scrub-at-ingest.
7. On approval: run ingest steps 2-10 against the scrubbed file only
8. Original raw source stays on disk, gitignored, never quoted in wiki/

### Query                                                                        (A4)
1. Read wiki/index.md for orientation
2. Grep frontmatter across wiki/ for matching `type` and `tags`
3. Read top-5 candidate pages
4. If more context needed, fan out via wikilinks (one hop only)
5. Cap: ~15 pages per query. If more needed, surface to user:
   "This query needs 22 pages. Continue or narrow?"
6. Synthesize answer with [[wikilink]] citations
7. Offer: "File this back into the wiki as a new page?"

### Lint                                                                         (A5)
Pass A — deterministic (run as a script, no LLM):
- Frontmatter schema validation (required fields present, allowed values)
- Stale-date check (last-updated > 90d AND status=active)
- Orphan detection (length(inlinks) = 0 AND type ≠ source)
- Stuck _none_ (Open questions = _none_ but sources array grew since last lint)
- Regenerate wiki/_health.md with counts and ages                               (A7)

Pass B — LLM contradiction sweep:
- Scoped per-type (all competitors together, all metrics together, etc.)
- Every finding gets a confidence score (high | med | low)
- User reviews findings; low-confidence auto-filter by default
- Propose: new questions, sources to hunt for
- Rewrite overview.md if warranted (quarterly cadence — check as-of date)

### PII scrub rules                                                              (A2)
Two-stage:

Stage 1 — LLM semantic rewrite:
- Pseudonymize names → segment role; emails/phones → [redacted]
- Aggregate individual quotes → segment claims with confidence wording
- Retain: CAS-IDs, public company names, public-source quotes

Stage 2 — Deterministic regex gate:
- Regex patterns for: email, phone (multiple formats), order ID, URLs with PII,
  name blocklist (wiki/_pii/blocklist.txt, gitignored, Claude maintains)
- If ANY match → abort ingest, force pre-scrub workflow
- Regex is the gate. LLM alone is insufficient.

## Review policy
- Ingest: summary-level report ("Updated 6 pages: ...")
- Lint Pass A: auto-run weekly, surface only findings
- Lint Pass B: on-demand, full-review, diff per finding

## Log format                                                                    (A6)
## [YYYY-MM-DD HH:MM] <verb> — [[slug]] | touched: [p1, p2, ...] | <summary>
# verb ∈ {ingest | query | lint | scrub | rewrite | archive}
# touched = list of pages whose content changed (not just frontmatter)
# summary = one-line change description, <= 80 chars

## Observability                                                                 (A7)
wiki/_health.md is regenerated on every Pass A lint:
- Pages per type (counts)
- Pages by status (active/archived/superseded/draft/etc.)
- Stale pages (last-updated > 90d, active)
- Orphan pages
- Open-questions-older-than-90d count
- Last ingest date + count this month
```

---

## 2.5 `wiki/index.md` design (Dataview-driven) — updated in v2

```markdown
# Research Wiki — Index

## Start here
- [[overview]] — current synthesis (as-of: YYYY-MM-DD)
- [[glossary]] — acronyms & terminology
- [[people]] — stakeholders (non-audience)
- [[_health]] — wiki health dashboard                         <!-- A7 -->
- [[log/index]] — activity timeline

## Competitors
```dataview
TABLE status, quarter, last-updated, confidence, length(sources) AS "# sources"
FROM ""
WHERE type = "competitor" AND status != "archived"
SORT last-updated DESC
```

## Initiatives, JTBDs, Features, Segments, Experiments, Metrics, Decisions
<!-- same pattern -->

## Recently updated (last 14 days)
```dataview
LIST last-updated
FROM ""
WHERE last-updated >= date(today) - dur(14 days)
SORT last-updated DESC
```

## Open questions older than 90 days                              <!-- B4 + new -->
```dataview
LIST
FROM ""
WHERE contains(file.text, "- [ ] 20") AND !contains(file.text, "Open questions\n_none_")
```

## Orphans (no inbound links)
```dataview
LIST
FROM ""
WHERE length(file.inlinks) = 0 AND type != "source"
```

## Missing OKR link (initiatives only)                            <!-- B3 enables this -->
```dataview
LIST
FROM ""
WHERE type = "initiative" AND length(okr) = 0
```
```

---

## 2.6 Documents outside the wiki itself

Two docs live in `research/docs/` (alongside, not in wiki/) because they're meta:

**B7 — `research/docs/schema-decisions.md`** — ADR log for the schema's own evolution.
- Why flat entity structure (vs 9 subdirs) — 2026-05-06
- Why segments not individuals — 2026-05-06
- Why pre-scrub default for sensitive sources — 2026-05-06
- Why deferred `external-ref:` — 2026-05-06
- Append new entries when the schema changes. Readers of the wiki in 6 months will have lost this context otherwise.

**B8 — `research/README.md`** — human-facing "how to read this wiki":
- What lives where (raw/, wiki/, _templates/, docs/)
- What's auto-maintained (index.md via Dataview, _health.md via lint) vs hand-maintained (nothing — Claude owns it all)
- Status values and what they mean
- How to ingest a source ("drop it in raw/, tell Claude to ingest")
- How to query the wiki
- How to request a lint
- What to edit yourself (answer: almost nothing — edit the schema if needed, let Claude do the rest)

---

## 2.7 Open decisions to confirm before finalizing v2

1. **`as-of` field on synthesis pages** — added. OK?
2. **Log filename cadence** — quarterly. OK or monthly?
3. **Lint Pass A cadence** — weekly auto-run. OK?
4. **Lint Pass B cadence** — on-demand only. OK?
5. **PII blocklist location** — `wiki/_pii/blocklist.txt`, gitignored. OK?
6. **`_health.md`** — regenerated on every Pass A lint (weekly by default). OK?

---

## What's next after approval of v2

**Section 3** will cover:
- The `llm-wiki-init` skill: scaffold a new wiki, handle existing repos, MANIFEST catalog flow, template generation
- Obsidian setup: install, vault, Web Clipper, Dataview plugin, attachment folder, and the lint-Pass-A script
- The deterministic regex/blocklist for PII Stage 2 (what it contains, how Claude maintains it)
- The implementation plan: exact build order, tasks, acceptance criteria

Then we write the final design doc to `docs/superpowers/specs/2026-05-06-llm-wiki-design.md`, you review it, and we hand off to the `writing-plans` skill.
