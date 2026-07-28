---
name: wiki-lint
description: Run the deterministic lint pass on the current wiki. Also handles Obsidian setup for existing wikis. Use when the user says "lint the wiki", "health check the wiki", "set up obsidian", "open in obsidian", or after adding/editing pages.
---

# wiki-lint skill

## Preflight

```bash
[ -d "${CLAUDE_PLUGIN_ROOT}/scripts" ] || { echo "llm-wiki plugin scripts not found (is the plugin installed and loaded?)"; exit 1; }
```

## Flow

1. Resolve wiki:
   ```bash
   resolution=$("${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py" --cwd "$(pwd)")
   ```
   Parse JSON. If source is `none` → "No wiki found; run `/llm-wiki:wiki-init` first." If `registry-ambiguous` → present options and ask user to pick.

2. Run lint from the wiki root:
   ```bash
   cd "$wiki_path"
   python3 scripts/lint.py
   ```
   Capture exit code.

3. Report:
   - Exit 0 → "Lint: OK (N pages, no issues)."
   - Exit 1 → "Lint: warnings. <findings>"
   - Exit 2 → "Lint: SCHEMA ERRORS. <findings>"

4. On exit 1 or 2, offer to help fix (e.g. "Want me to walk through the stale pages?").

5. Opportunistic registry compaction: if `${CLAUDE_PLUGIN_DATA}/registry.txt` has more than 500 lines, run `${CLAUDE_PLUGIN_ROOT}/scripts/resolve_wiki.py --compact`.

## Obsidian setup (for existing wikis)

If the user says "set up obsidian", "open in obsidian", or ".obsidian is missing" — run this after resolving the wiki:

```bash
abs_path="$wiki_path"

# Check if already configured
if [ -f "$abs_path/.obsidian/app.json" ]; then
    echo "Obsidian already configured. Opening vault..."
    open -a Obsidian "$abs_path"
else
    # Full setup
    mkdir -p "$abs_path/.obsidian/plugins/dataview"
    cp "${CLAUDE_PLUGIN_ROOT}/assets/obsidian-config/app.json"               "$abs_path/.obsidian/app.json"
    cp "${CLAUDE_PLUGIN_ROOT}/assets/obsidian-config/community-plugins.json" "$abs_path/.obsidian/community-plugins.json"
    cp "${CLAUDE_PLUGIN_ROOT}/assets/obsidian-config/core-plugins.json"      "$abs_path/.obsidian/core-plugins.json"
    cp "${CLAUDE_PLUGIN_ROOT}/assets/obsidian-config/hotkeys.json"           "$abs_path/.obsidian/hotkeys.json"
    curl -sL "https://github.com/blacksmithgu/obsidian-dataview/releases/latest/download/main.js" \
         -o "$abs_path/.obsidian/plugins/dataview/main.js"
    curl -sL "https://github.com/blacksmithgu/obsidian-dataview/releases/latest/download/manifest.json" \
         -o "$abs_path/.obsidian/plugins/dataview/manifest.json"
    # Register the vault in obsidian.json before opening, so a first-time vault
    # isn't rejected with "Vault not found" (same fix as wiki-init).
    obsidian_json="$HOME/Library/Application Support/obsidian/obsidian.json"
    if [ -f "$obsidian_json" ]; then
        python3 - "$obsidian_json" "$abs_path" << 'PY'
import json, secrets, sys, time
cfg_path, vault_path = sys.argv[1], sys.argv[2]
with open(cfg_path) as f:
    cfg = json.load(f)
vaults = cfg.setdefault("vaults", {})
if not any(v.get("path") == vault_path for v in vaults.values()):
    vaults[secrets.token_hex(8)] = {"path": vault_path, "ts": int(time.time() * 1000), "open": True}
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)
PY
        open "obsidian://open?path=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$abs_path")"
    else
        open -a Obsidian "$abs_path"
    fi
    echo "Obsidian configured and opening. Click 'Trust author and enable plugins' if prompted."
fi
```

## Error handling

- FC-11: If `python3` is not on PATH or `scripts/lint.py` is missing: "Wiki's lint script is missing or Python 3 is unavailable. Verify Python 3 is on PATH and the wiki was scaffolded via the llm-wiki plugin."
- FC-13 (CLAUDE_PLUGIN_ROOT not set): abort with remediation.
