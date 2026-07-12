# llm-wiki plugin — smoke-test checklist

Manual 11-item validation. Run in a fresh terminal session with `claude --plugin-dir ~/llm-wiki/plugin/`.

## Setup

- Fresh empty directory for testing (e.g. `~/tmp/llm-wiki-smoketest/`)
- `claude --plugin-dir ~/llm-wiki/plugin/` starts without errors
- `/reload-plugins` works after any edit

## Core checks

1. [ pass] **Install.** Plugin loads without warnings. `${CLAUDE_PLUGIN_ROOT}` is set.
2. [ ] **Empty-dir research + auto-scaffold.** In an empty dir, `/llm-wiki:research <topic>` detects no wiki and offers to scaffold. Accept. wiki-init runs; after scaffold, research continues automatically.
3. [ ] **Existing-wiki smoke.** `cd` into an already-scaffolded wiki and run `claude --plugin-dir ~/llm-wiki/plugin/`. Invoke `/llm-wiki:research <topic>` — resolves to that wiki, runs, saves to raw/.
4. [ ] **Multi-wiki resolution.** With two wikis scaffolded, open a session from a THIRD directory. `/llm-wiki:research X` prompts with options for both wikis.
5. [ ] **Analyze.** `/llm-wiki:analyze [[some-existing-page]]` produces analysis with gap/risk sections. Validates output envelope.
6. [ ] **Critique — fidelity mode.** On a page with sources, `/llm-wiki:critique [[some-page]]` runs fidelity audit; produces severity-labeled findings (`**[unsupported]**` etc.).
7. [ ] **Critique — challenge mode.** Create a stub page WITHOUT sources. `/llm-wiki:critique [[stub-page]]` prompts to confirm challenge mode, then runs web research for contrary evidence.
8. [ ] **Synthesize.** `/llm-wiki:synthesize <topic>` produces a new digest at `wiki/digests/synthesis-<slug>-<date>.md`. Verify overview.md is NOT modified.
9. [ ] **Lint.** `/llm-wiki:wiki-lint` runs and reports cleanly on both wikis.
10. [ ] **PII gate.** Seed a raw file with `Call Sarah at 650-555-1234.` Try to ingest. PII gate blocks with specific line reference and `--wiki-root` was passed correctly (blocklist checked).
11. [ ] **Registry.** After scaffold + operations, `cat ${CLAUDE_PLUGIN_DATA}/registry.txt` shows touch entries. After a `wiki-lint` run on a large registry, compaction happens opportunistically.
12. [ ] **Query.** `/llm-wiki:query <question>` answers from existing wiki pages with `[[wikilink]]` citations, without dispatching a research agent.
13. [ ] **Overview refresh.** `/llm-wiki:overview-refresh` shows a diff against the current `overview.md` and only writes on confirmation.
14. [ ] **Wiki-forget.** `/llm-wiki:wiki-forget <path>` removes the registry entry only; source files on disk are untouched.

## Regression

- After all tests, each wiki's pages still lint clean: `cd <wiki> && python3 scripts/lint.py`

## Cleanup

- `rm -rf ~/tmp/llm-wiki-smoketest/`

