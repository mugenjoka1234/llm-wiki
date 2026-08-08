Read {{PLUGIN_ROOT}}/skills/wiki-ingest/SKILL.md and follow it by reading that file directly. Do NOT invoke the Skill tool or any installed llm-wiki plugin command — this evaluation must exercise the skill files under {{PLUGIN_ROOT}}, not an installed copy in --auto mode with these arguments: --auto --wiki {{WIKI_ROOT}} {{RAW_FILE}}

This is a non-interactive evaluation run:
- Decline ALL optional offers — including the step-9 question-page extraction offer ("cluster them into question pages? (y/n)" → no) — and continue through every remaining step to completion (log entry, MANIFEST update, auto-lint).
- Where the skill says to invoke a slash command (e.g. /llm-wiki:graphify-wiki), run the equivalent python script directly instead: python3 {{WIKI_ROOT}}/scripts/graphify_wiki.py --wiki-root {{WIKI_ROOT}}
- Snapshot capture (step 5) will fail to fetch every URL — that is expected here (the URLs are fixture URLs); report the failures and continue. Do not treat 0 captures as an error.
