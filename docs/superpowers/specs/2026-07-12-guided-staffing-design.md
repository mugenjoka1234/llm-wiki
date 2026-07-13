# Guided Staffing (`/staff`) — Design

**Status:** approved-pending-review · **Date:** 2026-07-12 · **Phase:** 6 (first post-release feature)

## Problem

A new user who installs llm-wiki gets working machinery and an empty organization. `/team recruit` hires one role at a time with no guidance; nothing helps a newcomer decide *which* roles they need, shape personas around *their* product, or establish working guidelines. The gap between "installed" and "first productive team session" is where adoption dies.

## Goal

One guided session takes a user from an empty factory home to: a staffed, validated team; a working-guidelines file; and a durable intake record — sourcing candidates from a bundled starter roster, a bundled index of the public `agency-agents` catalog (~500 personas, MIT), and any local reference pools.

## Design decisions (settled)

| Question | Decision |
|---|---|
| Where does it live? | A new dedicated skill (`staff`). `factory-init` hands off to it when the roster is empty; `/team recruit` remains the single-hire shortcut. `/team` operates the org; `/staff` builds it. |
| Interview style | **Standard questionnaire + model judgment.** The skill embeds a fixed, versioned question set asked verbatim, one at a time. Everything downstream — triage, composition, matching, adaptation — is model judgment following the skill, grounded in the recorded answers. |
| Corp-doc input | **Triage into three destinations** (shown as a table, approved before any write): process norms → factory-home `instructions/working-guidelines.md`; domain expertise → shapes persona drafts; project facts → offered to the project wiki via the existing ingest path. |
| Project-agnosticism | **Relaxed from refusal to deliberate choice.** A denylist hit during staffing/validation becomes a confirm-gate ("this persona carries <term> — keep deliberately?"). A kept hit is recorded in persona frontmatter (`scope-bound: [<terms>]`); `validate-persona` accepts listed terms thereafter. The model may auto-resolve only unambiguous cases (e.g. the term names the very project the user is staffing for) and must disclose what it resolved. |
| agency-agents access | **Index, not vendoring.** The plugin ships a generated compact catalog (`plugin/assets/agency-agents-index.json`); only *selected* candidates are fetched from GitHub at hire time. `references/agency-agents/` in the factory home doubles as an optional offline mirror (preferred over fetch when present) and generalizes to user-added reference pools. |
| Starter roster | **Nine genericized archetypes** shipped at `plugin/assets/starter-roster/`: product-strategist, ux-realist, domain-reality-checker, market-strategist, marketplace-economist, delivery-gatekeeper, copy-qa-lead, privacy-trust-lead, visual-design-lead. Each in full factory format, validating clean out of the box, `domain: []` left for staffing to fill. |
| Runtimes | Claude Code primary. The flow requires only Q&A, python CLIs, and file writes — no subagent dispatch — so the skill also ships in the Gemini shim (best-effort; `/team` itself remains Claude-only). |

## The standard questionnaire (v1 — fixed, asked verbatim, one at a time)

1. What are you building? One paragraph — and what stage is it at (idea / prototype / live)?
2. Who is it for, and what is the hardest part of serving them well?
3. What decisions are coming in the next month that you want a team's help with?
4. What expertise do you bring yourself — and what do you know is missing?
5. What does a great outcome look like 90 days from now?
6. Do you have documents to share — strategy docs, process norms, research? (optional; paths/folders — triggers the triage step)
7. Team size: focused (3–4 members) or full bench (6–9, extras on-demand)?

Answers are recorded to `<factory-home>/instructions/staffing-intake.md` (create-or-update; one section per questionnaire version) — the durable record that later re-staffing, `/team recruit`, and `/improve` can read.

## Flow (skill outline)

1. **Preflight** — resolve factory home (STOP with hint if absent, like `/team`); detect existing roster/teams (staffing an existing org = expansion mode: same flow, slate seeded with current members).
2. **Interview** — the questionnaire above; write the intake file.
3. **Resource triage** (if Q6 provided) — read the docs; present the three-destination table; on approval write guidelines/shape-notes, and queue wiki-ingest offers (never auto-ingest).
4. **Composition proposal** — recommended slate: role, why (tied to intake answers), source (starter / agency-agents / references), what each member covers. User edits the slate before anything is fetched.
5. **Source & adapt** — starter/reference candidates copied; agency-agents selections fetched from GitHub (or the local mirror); each shaped into factory format: citation anchor + fenced immutables preserved, `description:` ≤600 in "Use when…" form, `domain:` tags from the intake, expertise sections informed by triaged domain material.
6. **Validate + human gate** — `validate-persona` on every draft; denylist confirm-gates per the relaxed rule; every file presented as a diff; one approval per persona; atomic writes; refuse-to-overwrite existing slugs.
7. **Assemble** — `teams/<name>.yaml` (template shape), `notes:` linking the working-guidelines file and the intake; final output: the roster table + "run `/team <name>` to hold your first session."

## Machinery (deterministic, tested)

- `team_ops.py search-candidates --query "<terms>" [--division D] [--source starter|index|references|all]` → ranked JSON `[{name, source, division, description, path_or_url, score}]`. Scoring: keyword/tag overlap — simple, documented, deterministic. Reads: bundled index, starter-roster frontmatter, `references/**` frontmatter.
- `validate_persona`: honors frontmatter `scope-bound: [<terms>]` — a denylist term listed there downgrades from error to a `warnings` entry (`"scope-bound: <term>"`). All other semantics unchanged.
- `build_agency_index.py` (release-time, not shipped to users' critical path): walks the agency-agents repo via the GitHub API, emits `agency-agents-index.json` `{generated, source_repo, source_ref, agents: [{name, division, description, path}]}`. Release checklist gains "regenerate the index."

## Testing

- Unit: search-candidates ranking + source filters; scope-bound validation semantics; index schema guard (shipped index parses, ≥400 entries, required keys).
- Starter roster: each of the nine passes `validate-persona` clean out of the box (mirrors the template test).
- Integration: fixture factory home from empty → intake file → candidates searched → one starter + one fixture-"fetched" persona adapted → validated → team YAML parses via `parse_team_yaml`.
- Acceptance: blind-adopter run — a fresh agent staffs a team for an invented product following only shipped docs; the resulting team must pass `resolve-team` and `assemble-context`.

## Out of scope (v1)

Auto-ingest of corp docs (offers only); fetching arbitrary URLs as reference pools (local `references/` only for now); Gemini validation beyond best-effort; editing existing personas (that's `/improve`); any paid services.

## Open risk

The starter roster derives from the maintainer's private roster: genericization must pass the repo leak-sweep (archetypes only — no client/project/person traces). The blind-adopter acceptance run doubles as the check that the archetypes read as truly generic.
