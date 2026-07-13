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

### /staff on Gemini CLI

Most factory skills (`team`, `session-close`, `improve`, `factory-init`) are
Claude Code-only — they are not part of this shim. `/staff` is the one
exception: it dispatches no subagents (only Q&A, deterministic
`team_ops.py`/`resolve_wiki.py` calls, and gated file writes), so it runs
here too, with three documented degradations versus Claude Code:

1. **Interview questions** — there is no structured multiple-choice picker
   widget. Render each question's choices as a lettered plain-text list in
   the message body (e.g. `(a) idea  (b) prototype  (c) live`) and accept
   the reply in kind. The one-question-at-a-time, context-first rule from
   the `staff` skill is unchanged.
2. **Approval gates** (working-guidelines write, every persona hire, the
   team-YAML write) — there is no native diff viewer. Print the full unified
   diff inline in the message body and get the same explicit approval before
   writing.
3. **Closing handoff** — the flow ends without a `/team` dispatch path (that
   command is Claude Code-only here). Close instead with a note to open
   Claude Code and run `/team <name>` for the first session.

Everything `/staff` reads or writes (starter roster, vendored
`agency-agents` catalog, factory-home `references/`, persona/team files) is
local and vendored — no network call anywhere in the flow, so behavior is
otherwise identical to Claude Code.
