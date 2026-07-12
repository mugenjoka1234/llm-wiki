#!/usr/bin/env python3
"""Resolve which wiki a skill should operate on.

Emits JSON on stdout:
  {
    "wiki_path": "<abs-path>" or null,
    "source": "cwd" | "registry-unique" | "registry-ambiguous" | "none",
    "options": [{"path": "...", "domain": "...", "last_used": "..."}]  # when ambiguous
  }

Exit codes: 0 always (caller branches on source).

Subcommands:
  link <child-path> <parent-path>       Set parent for a wiki in the registry.
  resolve-uri wiki://<domain>/<slug>    Resolve a wiki:// URI to an absolute path.
  register-factory-home <path>          Record the AI Factory home in the registry.
  resolve-factory-home                  Resolve the factory home (JSON: ok|missing|absent).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


WIKI_MARKER_SECTIONS = ("## Purpose",)  # a wiki's CLAUDE.md has these sections


def is_wiki(path: Path) -> bool:
    """True if path is a wiki root (contains a CLAUDE.md with wiki markers)."""
    claude_md = path / "CLAUDE.md"
    if not claude_md.is_file():
        return False
    try:
        content = claude_md.read_text()
    except (PermissionError, OSError):
        return False
    return all(marker in content for marker in WIKI_MARKER_SECTIONS)


FACTORY_HOME_PREFIX = "!factory_home|"


def is_factory_home(path: Path) -> bool:
    """True if path is a factory home (contains agents/ and teams/ dirs)."""
    return (path / "agents").is_dir() and (path / "teams").is_dir()


def load_factory_home(reg_path: str | None) -> str | None:
    """Return the recorded factory-home path (last !factory_home line wins), or None.

    Does NOT validate the path against disk — callers decide how to handle
    a recorded-but-missing home (see resolve-factory-home subcommand).
    """
    if not reg_path:
        return None
    p = Path(reg_path)
    if not p.is_file():
        return None
    try:
        lines = p.read_text().splitlines()
    except (PermissionError, OSError):
        return None
    home: str | None = None
    for line in lines:
        line = line.strip()
        if line.startswith(FACTORY_HOME_PREFIX):
            home = line[len(FACTORY_HOME_PREFIX):].strip()
    return home or None


def _unquote_scalar(value: str) -> str:
    """Strip whitespace and one layer of surrounding quotes from a YAML scalar."""
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        v = v[1:-1]
    return v


def parse_project_config(wiki_root: Path) -> dict:
    """Parse the '## Project config' yaml fence in <wiki_root>/CLAUDE.md.

    Stdlib-only line parser (no yaml dependency). Returns
    {"docs_path": str | None, "docs_ignore": list[str]}.

    The opening fence must be exactly ```yaml (other fences are skipped).
    Quoted values in docs_path and docs_ignore are unquoted.
    """
    cfg: dict = {"docs_path": None, "docs_ignore": []}
    claude_md = wiki_root / "CLAUDE.md"
    if not claude_md.is_file():
        return cfg
    try:
        lines = claude_md.read_text().splitlines()
    except (PermissionError, OSError):
        return cfg
    in_section = False
    in_yaml = False
    in_other_fence = False
    in_ignore = False
    for line in lines:
        stripped = line.strip()
        if not in_yaml and not in_other_fence and stripped.startswith("## "):
            in_section = stripped == "## Project config"
            continue
        if not in_section:
            continue
        if stripped.startswith("```"):
            if in_yaml:
                break  # closing fence of the yaml config block — done
            if in_other_fence:
                in_other_fence = False
                continue
            if stripped == "```yaml":
                in_yaml = True
            else:
                in_other_fence = True
            continue
        if not in_yaml or in_other_fence:
            continue
        if stripped.startswith("docs_path:"):
            cfg["docs_path"] = _unquote_scalar(stripped[len("docs_path:"):]) or None
            in_ignore = False
        elif stripped.startswith("docs_ignore:"):
            in_ignore = True
        elif in_ignore and stripped.startswith("- "):
            cfg["docs_ignore"].append(_unquote_scalar(stripped[2:]))
        else:
            in_ignore = False
    return cfg


def resolve_docs_path(wiki_root: Path, cfg: dict) -> Path | None:
    """Resolve cfg["docs_path"] to an absolute Path, or None when unset.

    Relative paths (e.g. `../docs`) resolve against `wiki_root`; absolute
    paths pass through unchanged. Single source of truth shared by the
    `--get-docs-path` CLI flag and session_ops.sweep_scan.
    """
    dp = cfg.get("docs_path")
    if not dp:
        return None
    p = Path(dp)
    return p if p.is_absolute() else (wiki_root / p).resolve()


def load_registry(reg_path: str | None) -> list[dict]:
    """Read registry.txt; return latest entry per path.

    Line format: <abs-path>|<domain>|<created-YYYY-MM-DD>|<last-used-YYYY-MM-DD>[|<parent-path>]
    Duplicates OK — last occurrence per path wins.
    5th field (parent_path) is optional; defaults to "" for backward compatibility.
    """
    if not reg_path:
        return []
    p = Path(reg_path)
    if not p.is_file():
        return []
    try:
        lines = p.read_text().splitlines()
    except (PermissionError, OSError):
        return []
    latest: dict[str, dict] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        parts = line.split("|")
        if len(parts) < 4:
            continue
        path = parts[0]
        domain = parts[1]
        created = parts[2]
        last_used = parts[3]
        parent = parts[4] if len(parts) >= 5 else ""
        latest[path] = {
            "path": path,
            "domain": domain,
            "created": created,
            "last_used": last_used,
            "parent": parent,
        }
    return list(latest.values())


def _entry_to_line(e: dict) -> str:
    """Serialize a registry entry dict back to a pipe-delimited line.

    The 5th field (parent_path) is optional in the line format — omit it
    entirely when empty rather than emitting a trailing pipe.
    """
    base = f"{e['path']}|{e['domain']}|{e['created']}|{e['last_used']}"
    parent = e.get("parent", "")
    return f"{base}|{parent}\n" if parent else f"{base}\n"


def _write_registry(reg_file: Path, home: str | None, entries: list[dict]) -> None:
    """Atomically rewrite the registry: one optional !factory_home line first,
    then one line per entry. Single write path shared by register/link/compact."""
    reg_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = reg_file.with_suffix(".txt.tmp")
    lines = ([f"{FACTORY_HOME_PREFIX}{home}\n"] if home else []) \
        + [_entry_to_line(e) for e in entries]
    tmp.write_text("".join(lines))
    tmp.replace(reg_file)  # atomic


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve wiki target for a skill.")
    parser.add_argument("--cwd", default=os.getcwd())
    parser.add_argument("--registry", default=None)
    parser.add_argument("--wiki-path", default=None)
    parser.add_argument("--compact", action="store_true",
                        help="Rewrite registry with only latest entry per path.")
    parser.add_argument("--get-parent", metavar="WIKI_PATH", default=None,
                        help="Print the parent path for the given wiki (empty string if none).")
    parser.add_argument("--get-docs-path", metavar="WIKI_ROOT", default=None,
                        help="Print the absolute docs_path for the given wiki (empty if unset).")
    # Subcommands: link, resolve-uri, register-factory-home, resolve-factory-home
    parser.add_argument("subcommand", nargs="?",
                        choices=["link", "resolve-uri", "register-factory-home",
                                 "resolve-factory-home"],
                        help="Subcommand.")
    parser.add_argument("subargs", nargs="*",
                        help="Arguments to the subcommand.")
    args = parser.parse_args(argv)

    reg_path = args.registry or _default_registry_path()

    # --get-parent flag
    if args.get_parent is not None:
        wiki_abs = str(Path(args.get_parent).resolve())
        entries = load_registry(reg_path)
        for e in entries:
            if e["path"] == wiki_abs:
                print(e.get("parent", ""))
                return 0
        # Not registered — return empty string (best-effort)
        print("")
        return 0

    # --get-docs-path flag
    if args.get_docs_path is not None:
        wiki_root = Path(args.get_docs_path).resolve()
        docs = resolve_docs_path(wiki_root, parse_project_config(wiki_root))
        print(str(docs) if docs is not None else "")
        return 0

    # Compaction mode: write-only, no resolution
    if args.compact:
        if not reg_path:
            print(json.dumps({"error": "no registry path"}), file=sys.stderr)
            return 1
        return compact_registry(Path(reg_path))

    # Subcommand: link
    if args.subcommand == "link":
        if len(args.subargs) != 2:
            print("Usage: resolve_wiki.py link <child-path> <parent-path>", file=sys.stderr)
            return 1
        return cmd_link(args.subargs[0], args.subargs[1], reg_path)

    # Subcommand: resolve-uri
    if args.subcommand == "resolve-uri":
        if len(args.subargs) != 1:
            print("Usage: resolve_wiki.py resolve-uri wiki://<domain>/<slug>", file=sys.stderr)
            return 1
        return cmd_resolve_uri(args.subargs[0], reg_path)

    # Subcommand: register-factory-home
    if args.subcommand == "register-factory-home":
        if len(args.subargs) != 1:
            print("Usage: resolve_wiki.py register-factory-home <path>", file=sys.stderr)
            return 1
        return cmd_register_factory_home(args.subargs[0], reg_path)

    # Subcommand: resolve-factory-home
    if args.subcommand == "resolve-factory-home":
        return cmd_resolve_factory_home(reg_path)

    # Default resolution mode
    cwd = Path(args.cwd).resolve()

    if args.wiki_path:
        p = Path(args.wiki_path).resolve()
        if is_wiki(p):
            print(json.dumps({"wiki_path": str(p), "source": "override"}))
            return 0
        print(json.dumps({"wiki_path": None, "source": "none",
                          "error": f"override path {p} is not a wiki"}))
        return 0

    if is_wiki(cwd):
        print(json.dumps({"wiki_path": str(cwd), "source": "cwd"}))
        return 0

    entries = load_registry(reg_path)
    reachable = [e for e in entries if is_wiki(Path(e["path"]))]

    if not reachable:
        print(json.dumps({"wiki_path": None, "source": "none"}))
        return 0
    if len(reachable) == 1:
        e = reachable[0]
        print(json.dumps({"wiki_path": e["path"], "source": "registry-unique",
                          "domain": e["domain"]}))
        return 0
    print(json.dumps({
        "wiki_path": None,
        "source": "registry-ambiguous",
        "options": reachable,
    }))
    return 0


def cmd_link(child_path_str: str, parent_path_str: str, reg_path: str | None) -> int:
    """Link subcommand: set the parent field for a child wiki in the registry.

    Validates both paths are wikis, then atomically updates registry.txt.
    """
    child_path = Path(child_path_str).resolve()
    parent_path = Path(parent_path_str).resolve()

    if not is_wiki(child_path):
        print(f"error: child path '{child_path}' is not a wiki (no CLAUDE.md with ## Purpose)",
              file=sys.stderr)
        return 1
    if not is_wiki(parent_path):
        print(f"error: parent path '{parent_path}' is not a wiki (no CLAUDE.md with ## Purpose)",
              file=sys.stderr)
        return 1

    if not reg_path:
        print("error: no registry path (set CLAUDE_PLUGIN_DATA or pass --registry)", file=sys.stderr)
        return 1

    reg_file = Path(reg_path)
    entries = load_registry(reg_path)

    # Build lookup by path
    by_path: dict[str, dict] = {e["path"]: e for e in entries}

    child_abs = str(child_path)
    parent_abs = str(parent_path)

    # Get domain names for the confirmation message
    child_domain = by_path.get(child_abs, {}).get("domain", child_path.name)
    parent_domain = by_path.get(parent_abs, {}).get("domain", parent_path.name)

    # Ensure child entry exists
    from datetime import date
    today = date.today().isoformat()
    if child_abs not in by_path:
        # Auto-register child — read its CLAUDE.md for domain if possible
        by_path[child_abs] = {
            "path": child_abs,
            "domain": child_path.name,
            "created": today,
            "last_used": today,
            "parent": "",
        }
        child_domain = child_path.name

    # Ensure parent entry exists
    if parent_abs not in by_path:
        by_path[parent_abs] = {
            "path": parent_abs,
            "domain": parent_path.name,
            "created": today,
            "last_used": today,
            "parent": "",
        }
        parent_domain = parent_path.name

    # Set the parent field on the child
    by_path[child_abs]["parent"] = parent_abs

    # Atomic rewrite (preserving the !factory_home line, which load_registry skips)
    home = load_factory_home(reg_path)
    _write_registry(reg_file, home, list(by_path.values()))

    print(f"Linked: {child_domain} → {parent_domain}")
    return 0


def cmd_resolve_uri(uri: str, reg_path: str | None) -> int:
    """resolve-uri subcommand: map wiki://domain/slug to an absolute file path.

    Prints the resolved path and exits 0, or prints an error to stderr and exits 1.
    """
    if not uri.startswith("wiki://"):
        print(f"error: URI must start with 'wiki://', got: '{uri}'", file=sys.stderr)
        return 1

    remainder = uri[len("wiki://"):]
    if "/" not in remainder:
        print(f"error: URI must be 'wiki://<domain>/<slug>', got: '{uri}'", file=sys.stderr)
        return 1

    domain, slug = remainder.split("/", 1)

    entries = load_registry(reg_path)
    for e in entries:
        if e["domain"] == domain:
            target = Path(e["path"]) / "wiki" / f"{slug}.md"
            print(str(target))
            return 0

    print(f"error: domain '{domain}' not found in registry", file=sys.stderr)
    return 1


def cmd_register_factory_home(path_str: str, reg_path: str | None) -> int:
    """Record <path> as the factory home: one !factory_home line, first in the file."""
    home = Path(path_str).resolve()
    if not is_factory_home(home):
        print(f"error: '{home}' is not a factory home (needs agents/ and teams/ dirs)",
              file=sys.stderr)
        return 1
    if not reg_path:
        print("error: no registry path (set CLAUDE_PLUGIN_DATA or pass --registry)",
              file=sys.stderr)
        return 1
    reg_file = Path(reg_path)
    entries = load_registry(reg_path)  # wiki entries only; ! lines already skipped
    _write_registry(reg_file, str(home), entries)
    print(f"Registered factory home: {home}")
    return 0


def cmd_resolve_factory_home(reg_path: str | None) -> int:
    """Resolve the factory home. Three outcomes: ok | missing | absent. Always exit 0."""
    recorded = load_factory_home(reg_path)
    if recorded is None:
        print(json.dumps({
            "factory_home": None,
            "status": "absent",
            "hint": ("No factory home registered. Register with: "
                     "resolve_wiki.py register-factory-home <path>"),
        }))
        return 0
    home = Path(recorded)
    if is_factory_home(home):
        print(json.dumps({"factory_home": str(home), "status": "ok"}))
        return 0
    print(json.dumps({
        "factory_home": recorded,
        "status": "missing",
        "hint": ("Recorded factory home no longer exists or lost agents/ or teams/. "
                 "Re-register with: resolve_wiki.py register-factory-home <path>"),
    }))
    return 0


def _default_registry_path() -> str | None:
    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA", "")
    if plugin_data:
        return str(Path(plugin_data) / "registry.txt")
    # Fallback for Gemini CLI so it shares the same registry as Claude Code
    fallback_path = Path.home() / ".claude" / "plugins" / "data" / "llm-wiki"
    return str(fallback_path / "registry.txt")


def compact_registry(reg_path: Path) -> int:
    """Rewrite registry.txt keeping only the latest entry per path. Atomic via rename.

    Preserves the !factory_home line (load_registry skips it by design)."""
    if not reg_path.is_file():
        return 0  # nothing to compact
    home = load_factory_home(str(reg_path))
    entries = load_registry(str(reg_path))
    if not entries and not home:
        reg_path.write_text("")
        return 0
    _write_registry(reg_path, home, entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
