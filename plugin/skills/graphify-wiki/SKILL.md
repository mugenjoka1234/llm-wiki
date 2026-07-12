---
name: graphify-wiki
description: Expert in building and querying the semantic _graph.json of the wiki. Trigger when `/llm-wiki:graphify-wiki` is invoked, or whenever the user asks to build or refresh the wiki's knowledge graph.
---

# graphify-wiki skill

This skill compiles a high-performance semantic graph index (`_graph.json`) of the wiki. It maps entities, headings, and keywords directly to their file paths and line ranges. This allows AI agents to locate specific facts and claims instantly, reading only targeted line ranges instead of loading massive consolidated documents into the context window.

## Workflow: Building the Graph

1. **Locate the Wiki Root**:
   - Resolve the active wiki root path `$wiki_path` using the standard `resolve_wiki.py` script.

2. **Execute the Graphify Engine**:
   - Ensure the `CLAUDE_PLUGIN_ROOT` environment variable is set.
   - Run the Python AST indexer script to parse the files and output the graph:
     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT}/scripts/graphify_wiki.py" --wiki-root "$wiki_path"
     ```

3. **Verify the Graph**:
   - Read the newly generated `$wiki_path/wiki/_graph.json` file.
   - Present a concise summary of the graph's metadata (e.g., total pages indexed, headings compiled, and mapped entities) to the user.

---

## Workflow: Querying the Graph (Agent Guidance)

When you (the agent) are asked to find or query information about an entity or keyword inside a "dual-engine" consolidated wiki:

1. **Do NOT Read All Files**:
   - Do **not** load large consolidated files (like `market-landscape.md` or `regulatory-framework.md`) into your context window in their entirety. This is token-inefficient.

2. **Load `_graph.json` First**:
   - Open and search `$wiki_path/wiki/_graph.json` using `grep_search` or a targeted read tool to find the target entity slug (e.g. `boram`, `cleo`) or keyword (e.g. `medicaid`, `rates`).

3. **Retrieve Targeted Line Ranges**:
   - Extract the `"path"`, `"start_line"`, and `"end_line"` from the graph mapping.
   - Use the `read_file` tool passing `start_line` and `end_line` parameters to read **only** the specified line range of the consolidated file.
   - Synthesize and present your answer with precise line-range citations. This achieves high-speed, ultra-token-efficient retrieval.
