# Guided Staffing (`/staff`) — Design

**Status:** approved-pending-review · **Date:** 2026-07-12 · **Phase:** 6 (first post-release feature)

## Problem

A new user who installs llm-wiki gets working machinery and an empty organization. `/team recruit` hires one role at a time with no guidance; nothing helps a newcomer decide *which* roles they need, shape personas around *their* product, or establish working guidelines. The gap between "installed" and "first productive team session" is where adoption dies.

## Goal

One guided session takes a user from an empty factory home to: a staffed, validated team; a working-guidelines file; and a durable intake record — sourcing candidates from a bundled starter roster, the public `agency-agents` catalog (277 personas, MIT), and any local reference pools.

## Design decisions (settled)

| Question | Decision |
|---|---|
| Where does it live? | A new dedicated skill (`staff`). `factory-init` hands off to it when the roster is empty; `/team recruit` remains the single-hire shortcut. `/team` operates the org; `/staff` builds it. |
| Interview style | **Standard coverage + model-composed questions (the superpowers pattern).** The skill embeds a fixed, versioned intake checklist — the seven items that MUST be known before staffing — but the model phrases each question itself, context-first (confirm-or-correct from what it inferred), one at a time, multiple-choice preferred. Coverage is standard; wording is situational. Everything downstream — triage, composition, matching, adaptation — is model judgment following the skill, grounded in the recorded answers. |
| Corp-doc input | **Triage into three destinations** (shown as a table, approved before any write): process norms → factory-home `instructions/working-guidelines.md`; domain expertise → shapes persona drafts; project facts → offered to the project wiki via the existing ingest path. |
| Project-agnosticism | **Relaxed from refusal to deliberate choice.** A denylist hit during staffing/validation becomes a confirm-gate ("this persona carries <term> — keep deliberately?"). A kept hit is recorded in persona frontmatter (`scope-bound: [<terms>]`); `validate-persona` accepts listed terms thereafter. The model may auto-resolve only unambiguous cases (e.g. the term names the very project the user is staffing for) and must disclose what it resolved. |
| agency-agents access | **Index, not vendoring.** The plugin ships a generated compact catalog (`plugin/assets/agency-agents-index.json`); only *selected* candidates are fetched from GitHub at hire time. `references/agency-agents/` in the factory home doubles as an optional offline mirror (preferred over fetch when present) and generalizes to user-added reference pools. |
| Starter roster | **Nine genericized archetypes** shipped at `plugin/assets/starter-roster/`: product-strategist, ux-realist, domain-reality-checker, market-strategist, marketplace-economist, delivery-gatekeeper, copy-qa-lead, privacy-trust-lead, visual-design-lead. Each in full factory format, validating clean out of the box, `domain: []` left for staffing to fill. |
| Runtimes | Claude Code primary. The flow requires only Q&A, python CLIs, and file writes — no subagent dispatch — so the skill also ships in the Gemini shim (best-effort; `/team` itself remains Claude-only). |

## Context-first interviewing (the superpowers pattern)

The questionnaire below is a **standard intake checklist, not a cold script**. Before asking anything, the skill fetches context and drafts answers from it:

- the current project: README, docs tree, recent git log, package/app manifests;
- the project wiki, if one resolves: `overview.md` theses, open questions, entity catalog;
- the factory home: existing personas, teams, guidelines, prior intake sections.

Each checklist item is then resolved in order of preference: **(1) inferred and confirmed** — present the drafted answer as a specific confirm-or-correct question ("From your README and wiki theses, you're building <X> at prototype stage, for <audience> — right?"); **(2) asked narrowly** when context gave a partial picture; **(3) asked open-ended** only when nothing was inferable. One item per message, always. The intake file records the final answers plus what was inferred vs. user-stated (provenance matters for later re-staffing). The checklist fixes COVERAGE, not wording — the model composes each question; an item already fully answered by context (and confirmed once) is never re-asked.

## The standard intake checklist (v1 — fixed items, context-first resolution)

1. What are you building? One paragraph — and what stage is it at (idea / prototype / live)?
2. Who is it for, and what is the hardest part of serving them well?
3. What decisions are coming in the next month that you want a team's help with?
4. What expertise do you bring yourself — and what do you know is missing?
5. What does a great outcome look like 90 days from now?
6. Do you have documents to share — strategy docs, process norms, research? (optional; paths/folders — triggers the triage step)
7. Team size: focused (3–4 members) or full bench (6–9, extras on-demand)?

Answers are recorded to `<factory-home>/instructions/staffing-intake.md` (create-or-update; one section per questionnaire version) — the durable record that later re-staffing, `/team recruit`, and `/improve` can read.

## Staffing doctrine (embedded in the skill — the basis for questions and composition)

The skill carries its own theory of what a good team is; the model applies it rather than improvising from general knowledge. Every slate proposal must justify each member against these principles, and the intake questions exist to gather exactly the inputs the doctrine needs:

1. **Cover the decision surface, not the org chart.** A team is good if every hard decision the user faces (intake item 3) has at least one lens that will interrogate it. Staff to decisions, not to job titles.
2. **Complement the human.** The user's own expertise (item 4) is already on the team — never duplicate it; staff the declared and inferred gaps.
3. **Tension by design.** Include at least one member whose job is to say no (reality-checker / skeptic archetype). A slate where every lens would agree is an echo chamber — split verdicts are a feature (they surface the real cruxes to the user, who holds the tie-break).
4. **A domain conscience.** One member owns keeping the product honest about what its domain actually allows — regulations, real-world constraints, how the served population actually behaves (items 1–2). In field use this archetype changed more decisions than any other.
5. **Sharp boundaries, but defer-with-a-view.** Every persona declares deep expertise, working knowledge, and explicit "defers on" — overlapping ownership produces mush. Composition must check that no two members claim the same deep lane and that every "defers on" points at someone actually on the team (or at the user). Deferring is never silence: a member who defers still states their recommendation from their own lens ("I defer to <owner> on this; from where I sit it looks like <view>, because <reason>") — the owning lens decides, but the panel never loses a viewpoint to a boundary, and stalemates resolve through the owner rather than through omission. Persona adaptation (flow step 5) bakes this into each hire's instructions.
6. **Small active bench, on-demand extras.** Active bench 3–5 members per session (full roster up to 9, the rest `invocation: on-demand` — matching intake item 7's focused/full-bench choice); specialists (copy QA, privacy, visual) join as `invocation: on-demand`. Context budgets are real — every member must earn their dispatch: if you cannot name a decision a member would change, cut them.
7. **Diversity of evidence style.** Mix at least two of: numbers-first (economics/metrics lens), user-first (behavior/experience lens), and precedent-first (what happened when others tried this). Single-style teams miss whole failure classes.

The intake checklist maps onto the doctrine (1–2 → domain conscience; 3 → decision coverage; 4 → complement; 7 → bench size), which is what grounds the model when it composes context-specific questions: it knows *why* it is asking.

## Flow (skill outline)

1. **Preflight** — resolve factory home (STOP with hint if absent, like `/team`); detect existing roster/teams (staffing an existing org = expansion mode: same flow, slate seeded with current members).
2. **Context fetch + interview** — scan project/wiki/factory-home context, draft answers, then run the intake checklist context-first (confirm-or-correct before open-ended); write the intake file with inferred-vs-stated provenance.
3. **Resource triage** (if Q6 provided) — read the docs; present the three-destination table; on approval write guidelines/shape-notes, and queue wiki-ingest offers (never auto-ingest).
4. **Composition proposal** — recommended slate: role, why (each line names the doctrine principle it satisfies and the intake answer it ties to), source (starter / agency-agents / references), active vs on-demand. Includes the boundary check (no duplicated deep lanes; defers-on targets exist). User edits the slate before anything is fetched.
5. **Source & adapt** — starter/reference candidates copied; agency-agents selections fetched from GitHub (or the local mirror); each written to `<factory-home>/agents/<slug>.md` under recruit's refuse-to-overwrite + atomic-write rules, shaped into factory format: citation anchor + fenced immutables preserved, `description:` ≤600 in "Use when…" form, `domain:` tags from the intake, expertise sections informed by triaged domain material.
6. **Validate + human gate** — `validate-persona` on every draft; denylist confirm-gates per the relaxed rule; every file presented as a diff; one approval per persona; atomic writes; refuse-to-overwrite existing slugs.
7. **Assemble** — `teams/<name>.yaml` per the template with required fields sourced explicitly (`id`/`name` from the team name, `purpose` from intake item 1, `project` from the resolved wiki's project root); the team template gains a documented optional `notes:` field (the parser already tolerates unknown scalars) linking the working-guidelines file and the intake; final output: the roster table + "run `/team <name>` to hold your first session."

## Machinery (deterministic, tested)

- `team_ops.py search-candidates --query "<terms>" [--division D] [--source starter|index|references|all]` → ranked JSON `[{name, source, division, description, path_or_url, score}]`. Scoring: keyword/tag overlap — simple, documented, deterministic. Reads: bundled index, starter-roster frontmatter, `references/**` frontmatter.
- `validate_persona`: honors frontmatter `scope-bound: [<terms>]` — a denylist term listed there downgrades from error to a `warnings` entry (`"scope-bound: <term>"`). All other semantics unchanged.
- `build_agency_index.py` (release-time, not shipped to users' critical path): walks the agency-agents repo via the GitHub API, emits `agency-agents-index.json` `{generated, source_repo, source_ref, agents: [{name, division, description, path}]}`. Release checklist gains "regenerate the index."

## Testing

- Unit: search-candidates ranking + source filters; scope-bound validation semantics; catalog guard (shipped catalog parses, ≥250 entries, required keys; `division` derived from each agent's top-level directory — the files themselves carry no division frontmatter).
- Starter roster: each of the nine passes `validate-persona` clean out of the box (mirrors the template test).
- Integration: fixture factory home from empty → intake file → candidates searched → one starter + one fixture-"fetched" persona adapted → validated → team YAML parses via `parse_team_yaml`.
- Acceptance: blind-adopter run — a fresh agent staffs a team for an invented product following only shipped docs; the resulting team must pass `resolve-team` and `assemble-context`.

## Companion plan: starter-roster authoring

The nine starter personas are content, not machinery — authoring them (genericized from the maintainer's private roster) is its own implementation plan with its own review: per-persona leak-sweep, `validate-persona` clean, and a blind cold-read ("does this archetype read as truly generic?"). The machinery plan treats `plugin/assets/starter-roster/` as an interface (any N validating personas), so the two plans land independently.

## Out of scope (v1)

Auto-ingest of corp docs (offers only); fetching arbitrary URLs as reference pools (local `references/` only for now); Gemini validation beyond best-effort; editing existing personas (that's `/improve`); any paid services.

## Open risk

The starter roster derives from the maintainer's private roster: genericization must pass the repo leak-sweep (archetypes only — no client/project/person traces). The blind-adopter acceptance run doubles as the check that the archetypes read as truly generic.
