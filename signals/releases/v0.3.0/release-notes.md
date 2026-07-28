# Release notes — llm-wiki v0.3.0 (guided staffing)

**Window:** `v0.2.0` → `v0.3.0` · 2026-07-12 → 2026-07-13
**Changes:** 10 (34 commits; 3 low-signal excluded)
**Theme:** guided team staffing — go from an empty factory home to a validated agent team.

> Note: no analytics instrumentation in this plugin, so `events_touched` is empty throughout.

---

## For the team

**chg-1 · README repositioned** — *feature* — `bc90a81a`
Reframed the plugin as "institutional memory + an agent org that uses it," with a who-this-is-for section. Surface: README.

**chg-2 · Guided-staffing design spec + plans** — *infra* — 14 commits
The design spec (context-first interviewing, embedded staffing doctrine, layered personas, blind-review fixes) and three implementation plans. Surface: `docs/superpowers`.
> ⚠️ needs human review: internal design/spec/plan docs, no user-facing behavior; grouped and included for completeness.

**chg-3 · Vendored agency-agents catalog** — *feature* — `92333bfc`
Bundled the ~277-persona agency-agents catalog (MIT) with a sync script and attribution, as a candidate pool for staffing. Surfaces: agency-agents catalog, /staff candidate search.

**chg-4 · search-candidates** — *feature* — `ea8f1026`, `9eae08a8`
Search personas across starter / catalog / references pools, with term-dedupe and word-boundary scoring. Surfaces: /staff candidate search, `team_ops.py`.

**chg-5 · Layered personas** — *feature* — `7d7fe335`, `e004acb9`, `a84f20d4`, `eb9650a2`, `2191e440`, `7d291144`, `38051fa0`
Project copies shadow factory-home base personas, with drift notices, `ack-fork`, `list-copies`, and graceful degradation when a project copy is unreadable. Surfaces: `team_ops.py` (resolve/validate/ack-fork), /team, /improve.

**chg-6 · The /staff skill** — *feature* — `35f9bed8`, `2191e440`
Context-first interview, doctrine-driven slate composition, and layered hiring (base personas to the factory home, client-flavored copies to the project wiki). Surface: /staff.
> ⚠️ needs human review: shares commit `2191e440` with chg-5 (a collision-check fix touching both the /staff flow and the layered-resolution machinery).

**chg-7 · /team layered spawning** — *feature* — `1c804124`
`--wiki-root`, `--project` validation, drift surfacing, and solo parity. Surface: /team.

**chg-8 · /improve layer-aware routing** — *feature* — `3290787e`, `5c904891`
Explicit base/copy/both targeting, two-repo commits, per-target diffs. Surface: /improve.

**chg-9 · factory-init / session-close integration** — *feature* — `672596c9`
factory-init hands off to /staff on an empty roster; session-close jots wiki provenance; persona template notes. Surfaces: factory-init, session-close.

**chg-10 · Starter roster** — *feature* — `87c8c659`, `847c6da9`, `286b828d`, `91adb279`
Nine generic archetype starter personas, refined for domain-neutrality (blank-domain reality-checker, real defers-on assertions, verbatim citation anchors). Surface: starter roster.

**Excluded as low-signal:** `85e12593` (chore: release bump), `72701808`, `0e9af0f3` (chore: gitignore).

---

## For stakeholders

v0.3.0 answers the question every new user hits: *"I have the machinery — now who's on my team?"*

It adds **guided staffing** — a `/staff` flow that interviews you about your project, then proposes a validated agent team drawn from a bundled catalog of ~277 ready personas plus nine generic starter archetypes (chg-3, chg-4, chg-6, chg-10). You approve the slate; the plugin hires them. Crucially, the personas are **layered**: a shared base persona lives in your reusable factory home, and project-specific tailored copies live with each project — so tuning a persona for one client never contaminates another (chg-5). The team-running, self-improvement, and project-setup skills all became layer-aware to match (chg-7, chg-8, chg-9).

> ⚠️ needs human review: chg-1, chg-2, and chg-6 carry framing/evidence caveats — see "For the team" before publishing externally.
