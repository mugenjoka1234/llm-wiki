Read {{PLUGIN_ROOT}}/skills/query/SKILL.md and follow it to answer the question below. Follow the SKILL.md file directly — do NOT invoke the Skill tool or any installed llm-wiki plugin command; this evaluation must exercise the skill files under {{PLUGIN_ROOT}}, not an installed copy.

The resolved wiki root is {{WIKI_ROOT}} — treat it as the target wiki; do not run wiki resolution against any other location.

This is a non-interactive evaluation run: never ask for confirmation; if the skill offers optional choices, decline them and continue to completion.

Question: {{QUESTION}}

After your prose answer (which should cite [[wikilinks]] per the skill), end your output with exactly one final line in this format, most relevant page first:

SOURCES (most relevant first): [[slug-1]], [[slug-2]], [[slug-3]]
