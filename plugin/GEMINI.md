# llm-wiki Extension Context

You are running with the `llm-wiki` extension active in Gemini CLI.

The extension root is located at:
`~/.gemini/extensions/llm-wiki` (which may be a symlink to your local repository `plugin` directory).

### Environment Variable Requirements
Whenever you run any shell script, python script, or subcommand from this extension, you **MUST** ensure the following environment variables are set in your execution environment (e.g. by prepending them directly to your shell command):
- `CLAUDE_PLUGIN_ROOT="${HOME}/.gemini/extensions/llm-wiki"`
- `CLAUDE_PLUGIN_DATA="${HOME}/.claude/plugins/data/llm-wiki"`

For example, when running a script, run it as:
`CLAUDE_PLUGIN_ROOT="${HOME}/.gemini/extensions/llm-wiki" CLAUDE_PLUGIN_DATA="${HOME}/.claude/plugins/data/llm-wiki" python3 "${HOME}/.gemini/extensions/llm-wiki/scripts/resolve_wiki.py" ...`

### Skill and Command Execution
When the user executes a command (e.g., `/llm-wiki:wiki-lint`, `/llm-wiki:research`, etc.), or when you need to use a skill:
1. Call the `activate_skill` tool for that skill to load its detailed instructions (e.g. `wiki-lint`, `wiki-init`, `research`, etc.).
2. Follow the instructions and workflows outlined in the activated skill's `SKILL.md` file step-by-step.
3. Use the subagents defined in `~/.gemini/extensions/llm-wiki/agents/` (e.g. `wiki-planner`, `wiki-researcher`, etc.) when instructed by the skills. You can delegate to these subagents using `@<agent-name>` or calling them as tools if applicable.
