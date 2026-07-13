# Guided Staffing — Plan 3 of 3: Starter Roster

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Content plan, not code.** The deliverables are nine persona files. The test harness: `validate-persona` clean per file, the leak-sweep, a shape test, and a blind cold-read.

**Goal:** `plugin/assets/starter-roster/` ships nine genericized archetype personas, each validating clean out of the box, reading as truly generic (no trace of the maintainer's clients, projects, people, or employer), and good enough that a stranger's first team feels staffed, not templated.

**Spec:** `docs/superpowers/specs/2026-07-12-guided-staffing-design.md` (Starter roster row + Companion plan section). The nine slugs, verbatim: `product-strategist`, `ux-realist`, `domain-reality-checker`, `market-strategist`, `marketplace-economist`, `delivery-gatekeeper`, `copy-qa-lead`, `privacy-trust-lead`, `visual-design-lead`.

## Global Constraints

- Work on `main`; controller pushes. **Source material handling:** the archetypes derive from the maintainer's PRIVATE roster (the registered factory home's `agents/` dir) — implementers READ those files for the archetype's shape (what makes the role effective: champions, push-backs, expertise boundaries, communication style) but must WRITE domain-blank generics: no person names, no client/project/company references, no domain specifics beyond what the archetype inherently needs (e.g. the domain-reality-checker's DOMAIN is a fill-in-the-blank; her METHOD — credential precision, reality-vs-claims gap, the 3am-style stress standard generalized — is the archetype).
- Every file: full factory format — frontmatter (`name`, `role`, `description:` ≤600 "Use when…", `version: v1.0`, `domain: []` EMPTY — staffing fills it), body sections per `plugin/assets/factory-templates/persona.md` (Identity, Communication Style, Champions, Pushes Back On, Expertise Deep/Working/Defers-on, fenced Immutable Anchors WITH the verbatim citation-anchor bullet, Mutable Instructions), defer-with-a-view baked into the anchors ("when deferring, state your recommendation from your own lens before handing off").
- Defers-on fields must reference the OTHER starter archetypes by role (not personal names), forming a coherent org: the nine must cross-reference consistently.
- Names: pick nine fresh human first names NOT in the maintainer's roster (grep it to confirm zero collisions — the leak-sweep treats roster names as leaks).
- Leak-sweep (CLAUDE.local.md) extended for this plan with the maintainer's persona names; must return LICENSE only.
- Commit trailers as on this branch.

---

### Task 1: shape test first

**Files:** Test `plugin/scripts/tests/test_starter_roster.py`.

- [ ] Step 1: write the test (RED against the empty dir): exactly the nine spec slugs present; each passes `validate_persona(path, denylist=[])` with zero errors AND zero warnings; each description ≤600 starting "Use when"; each `domain: []` empty; each contains both fence markers + the citation-anchor bullet; every `Defers on` mention of another archetype matches one of the nine roles (parse and cross-check); no two personas share a name; total description budget across nine ≤ 5400 chars.
- [ ] Step 2: RED confirmed. Commit — `test(staff): starter-roster shape gate (red until roster lands)`. NOTE: the suite will carry expected failures until Task 3 — mark the class `@unittest.skipUnless(ROSTER_DIR.exists(), ...)`? NO — instead gate on dir presence with a single always-on test asserting the dir exists ONLY after Task 3 (controller: run this task and Task 2-3 in one review cycle if the red suite blocks other work; simplest: implement Task 1 tests but commit them together with Task 3's files — the brief for Task 3 includes committing the test file. Decision for the controller at execution time; default: Task 1's file is written and held uncommitted until Task 3's commit).

### Task 2: author personas 1–5 (the analysis core)

**Files:** Create `product-strategist.md`, `ux-realist.md`, `domain-reality-checker.md`, `market-strategist.md`, `marketplace-economist.md` under `plugin/assets/starter-roster/`.

- [ ] Step 1: read the private-roster counterparts + the template + 2 vendored agency-agents files (register calibration: the starter nine should read RICHER than catalog entries — that's their value).
- [ ] Step 2: author the five. Each ~55-70 lines. Archetype extraction guidance per persona: product-strategist = life-stage/WTP-evidence discipline, kill-signals, like/act/pay separation; ux-realist = depleted-user default, resumability, friction-cost visibility (generalize the stress standard: "the worst-hour standard: judge every flow by its most depleted plausible user"); domain-reality-checker = DOMAIN-BLANK conscience ("whatever domain the product claims to navigate: what the system says vs what people can actually get"), credential/taxonomy precision, claims-vs-plan variance flagging; market-strategist = graveyard tour, free-alternative honesty, why-now on structural change, beachhead discipline; marketplace-economist = attribution-before-monetization, ops-labor pricing, leakage profiles, precedent-with-break-analysis.
- [ ] Step 3: run `validate-persona` on each (zero errors AND warnings); run the Task 1 test module locally.
- [ ] Step 4: leak-sweep incl. roster names. Hold for Task 3's combined commit (or commit if controller directed a running suite-red).

### Task 3: author personas 6–9 (the gate + craft bench) + commit

**Files:** Create `delivery-gatekeeper.md`, `copy-qa-lead.md`, `privacy-trust-lead.md`, `visual-design-lead.md`; commit everything incl. Task 1's test.

- [ ] Step 1: author the four: delivery-gatekeeper = NEEDS-WORK-default, evidence artifacts, fix-cycle cap, DEFERRED≠PASS (closest to the already-generic source — least invention); copy-qa-lead = audience-appropriate language gates, locked-language discipline, reading-under-stress compression; privacy-trust-lead = data-minimization default, regulatory-surface awareness kept GENERIC (no specific statutes as facts — method not citations), trust-pacing; visual-design-lead = context-discovery-before-pixels, system-consistency, accessibility floor.
- [ ] Step 2: full nine cross-reference pass (defers-on graph coherent; evidence styles span all three doctrine categories — annotate each persona's style in its Expertise section footer comment).
- [ ] Step 3: `python3 -m unittest scripts.tests.test_starter_roster -v` GREEN; full suite GREEN; leak-sweep (with roster names) clean.
- [ ] Step 4: Commit — `feat(staff): starter roster — nine generic archetype personas`.

### Task 4: blind cold-read acceptance

- [ ] Step 1: fresh blind agent (zero context): reads the nine files only. Questions: (1) describe each persona's job in one line — do descriptions match bodies? (2) do any read as derived from a specific company/client/person/industry? name evidence; (3) as a startup founder in a domain of the AGENT's choosing, which five would you hire and would the domain-reality-checker archetype make sense for YOUR domain? (4) rate each: would you be embarrassed shipping it?
- [ ] Step 2: any "reads as specific" or "embarrassing" finding → rewrite that persona, re-run the shape test, re-read by the same agent.
- [ ] Step 3: Commit fixes — `fix(staff): cold-read findings on starter roster`. Record evidence in scratch.

## Acceptance

Shape test green in the full suite; nine personas validate with zero errors AND warnings; blind cold-read passes (generic, hire-able, unembarrassing); leak-sweep incl. roster-name terms returns LICENSE only.

## Out of scope

Wiring into `/staff` (Plan 2 treats the dir as an interface); translations; more than nine; any domain-specialized variants (that's what staffing adaptation is for).
