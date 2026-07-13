#!/usr/bin/env python3
"""Session-close operations for AI Factory wikis.

Provides the idempotency primitives that make `/session-close` safe to
re-run: appends that are guarded by a marker already present in the file,
so a second run of the same append is a byte-identical no-op.

Usage:
  session_ops.py append-once <path> --marker M --text T [--heading H]
      Append `text` to `path` unless `marker` already occurs anywhere in
      the file. JSON on stdout, exit 0. `--text` accepts `-` to read the
      block from stdin (for multi-line text). Exit 2 when the path is
      unwritable (e.g. its parent directory does not exist).

  session_ops.py jot-append --home H --session S --date D --observation TEXT
      [--persona SLUG]... [--wiki W]
      Append one JSON line per `--observation` (repeatable) to
      `H/patterns/pattern-log.jsonl`, unless a line with `"session" == S`
      already exists in the file (then the whole call is a no-op). Each
      repeatable `--persona SLUG` is applied to every observation in this
      call and written as a `"personas"` list; omitted entirely when no
      `--persona` is given. `--wiki W` is applied to every observation in
      this call and written as a `"wiki"` string field; omitted entirely
      when not given (same additive, omit-when-absent contract as
      `"personas"`). JSON on stdout, exit 0. Exit 2 when `H` is not a
      directory.

  session_ops.py sweep-scan --wiki-root W
      Read-only detection of stray markdown and unmanifested raw drops
      under `W`. JSON on stdout, exit 0. Exit 2 when `W` is not a readable
      directory. Never writes anything.

  session_ops.py breadcrumb --cwd C --session-id S --date D
      SessionEnd hook write side. Resolves the wiki for `C`; if none
      resolves, a silent no-op (JSON `{"recorded": false, "reason": "no
      wiki"}`, no stdout from the CLI). Otherwise appends one JSON line to
      `<registry-data-dir>/session-breadcrumbs.jsonl`. Exit 0 always
      (exit 2 only when `C` is not a usable directory).

  session_ops.py session-check --cwd C
      SessionStart hook read side. Resolves the wiki for `C`; if none
      resolves, silent no-op (no stdout). Otherwise compares the newest
      recorded breadcrumb for that wiki against the newest
      `wiki/sessions/*.md` page date; if the breadcrumb is newer, prints
      one human-readable warning line to stdout (which SessionStart
      injects as context) telling the user to run `/session-close`. Exit 0
      always (exit 2 only when `C` is not a usable directory).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from scripts import resolve_wiki
except ImportError:  # pragma: no cover - bare-script invocation
    sys.path.insert(0, str(Path(__file__).parent))
    import resolve_wiki


def _atomic_write(path: Path, text: str) -> None:
    """Atomic tmp+rename write, mirroring team_ops.py's _atomic_write."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)  # atomic


def append_once(path: Path, marker: str, text: str, heading: str | None = None) -> dict:
    """Append `text` to `path` unless `marker` already occurs in the file.

    The CALLER must have embedded `marker` somewhere in `text` — this is
    enforced (`ValueError` if not), since the marker is what makes the next
    call to this function a no-op.

    Rules:
      - `marker` found anywhere in the existing file -> no-op, file
        untouched, returns {"appended": False}.
      - File does not exist -> created with exactly `text`, returns
        {"appended": True, "created": True}.
      - `heading` is None -> `text` is appended at EOF, with exactly one
        blank line separating it from existing content.
      - `heading` is given -> `text` is inserted at the end of that
        heading's section (immediately before the next `## ` line, or EOF
        if there is no next section). If the heading is not present in the
        file, the heading itself plus `text` are appended at EOF, and the
        result includes `"created_heading": True`.

    Write is atomic (tmp+rename).
    """
    if marker not in text:
        raise ValueError(f"marker {marker!r} must be embedded in text")

    if not path.is_file():
        _atomic_write(path, text)
        return {"appended": True, "created": True}

    original = path.read_text()
    if marker in original:
        return {"appended": False}

    result: dict = {"appended": True}

    if heading is None:
        new_text = original.rstrip("\n") + "\n\n" + text
        if not new_text.endswith("\n"):
            new_text += "\n"
        _atomic_write(path, new_text)
        return result

    lines = original.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if line.rstrip("\n") == heading:
            start = i + 1
            break

    if start is None:
        # Heading missing entirely — append heading + text at EOF.
        new_text = original.rstrip("\n") + "\n\n" + heading + "\n\n" + text
        if not new_text.endswith("\n"):
            new_text += "\n"
        _atomic_write(path, new_text)
        result["created_heading"] = True
        return result

    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break

    # Trim trailing blank lines within the section so the insertion sits
    # directly after the last real content line, then re-pad with exactly
    # one blank line before the appended block and one after (unless we're
    # at EOF, where a single trailing newline suffices).
    section_end = end
    while section_end > start and lines[section_end - 1].strip() == "":
        section_end -= 1

    insert_block = "\n" + text + "\n"
    if end < len(lines):
        insert_block += "\n"

    new_lines = lines[:section_end] + [insert_block] + lines[end:]
    new_text = "".join(new_lines)
    if not new_text.endswith("\n"):
        new_text += "\n"
    _atomic_write(path, new_text)
    return result


def jot_append(home: Path, session: str, date: str, observations: list[str],
                personas: list[str] | None = None, wiki: str | None = None) -> dict:
    """Append pattern-jot observations, deduped by session ID.

    Rules (spec: "pattern-jot appends skip if the session ID is already
    present"):
      - If ANY existing line in `home/patterns/pattern-log.jsonl` parses as
        JSON with `"session" == session` -> the whole call is a no-op:
        returns {"appended": 0, "skipped": True}, file untouched.
      - Otherwise, append one JSON line per observation with the exact
        schema {"session", "date", "observation", "source": "user-turn"},
        creating `patterns/` and the file if missing. Returns
        {"appended": len(observations), "skipped": False}.

    `personas` is an optional list of lowercase slugs applied to ALL
    observations in this call (callers batch a separate call per persona
    when observations classify differently). When None or empty, the
    `personas` key is OMITTED from the written lines entirely (not written
    as `[]`) — this keeps pre-existing (Phase 4) 4-key jot lines and
    freshly-written unclassified lines schema-identical, and dedup (by
    session, above) is unaffected either way since it only inspects
    `"session"`.

    `wiki` is an optional provenance string (the wiki/project this call's
    observations concern — session-close passes the resolved wiki path)
    applied to ALL observations in this call, written as a `"wiki"` field.
    Same additive contract as `personas`: None or empty omits the key
    entirely rather than writing it as `""`, keeping pre-existing jot lines
    (with or without `"personas"`, with or without `"wiki"`) schema-
    compatible, and dedup is unaffected (still inspects only `"session"`).

    Unparseable existing lines are ignored (never a crash) — the file is a
    plain append-only log (`open(path, "a")`), not lock-protected, so the
    spec accepts a worst-case single garbled line over the cost of a lock.
    """
    path = home / "patterns" / "pattern-log.jsonl"

    if path.is_file():
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(row, dict) and row.get("session") == session:
                    return {"appended": 0, "skipped": True}

    if not observations:
        # Nothing to write — no side effects (no patterns/ dir, no file).
        return {"appended": 0, "skipped": False}

    # A hand-edited/truncated file may lack a trailing newline; appending
    # directly would concatenate our first record onto the last existing
    # line, merging both into invalid JSON (and silently breaking that
    # session's dedup on the next run). Normalize by prefixing a newline.
    needs_newline = (path.is_file() and path.stat().st_size > 0
                     and path.read_bytes()[-1:] != b"\n")

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        if needs_newline:
            f.write("\n")
        for observation in observations:
            row = {"session": session, "date": date, "observation": observation,
                   "source": "user-turn"}
            if personas:
                row["personas"] = personas
            if wiki:
                row["wiki"] = wiki
            f.write(json.dumps(row) + "\n")

    return {"appended": len(observations), "skipped": False}


_ROOT_CONFIG_SKIP = {"CLAUDE.md", "README.md", "GEMINI.md", "AGENTS.md"}


def _manifest_mentions(manifest_text: str, filename: str) -> bool:
    """True if `filename` occurs in `manifest_text` as a whole token.

    Word-boundary matching, not bare substring: the filename must not be
    preceded by a word char, dot, or hyphen (blocks `a.md` matching inside
    `data.md` or `x--old.md` matching for `old.md`) nor followed by a word
    char or hyphen (blocks `old.md` matching inside `old.md-notes`). A
    preceding `/` is allowed on purpose — the real MANIFEST records some
    entries as relative paths (e.g. `../../docs/research/<file>.md`), so a
    path-tail occurrence counts as manifested. Backticks are not required:
    the current MANIFEST convention wraps names in backticks, but the
    matcher stays robust to plain-text mentions.
    """
    return re.search(
        rf"(?<![\w.-]){re.escape(filename)}(?![\w-])", manifest_text
    ) is not None


def sweep_scan(wiki_root: Path) -> dict:
    """Read-only scan for stray markdown and unmanifested raw/ drops.

    Never writes anything. Returns:
      {"strays": [str, ...], "raw_unmanifested": [str, ...],
       "docs_path": str | None}
      plus "no_manifest": True when raw/MANIFEST.md is missing.

    Strays: `.md` files anywhere under `wiki_root`, excluding `wiki/`,
    `raw/`, the resolved `docs_path` (which may live inside OR outside
    `wiki_root` — e.g. a sibling `../docs`), any directory named in
    `docs_ignore`, and the root-level config-file skip-list (CLAUDE.md,
    README.md, GEMINI.md, AGENTS.md). Two further exclusions cover
    wiki-init's own scaffold, which is infrastructure rather than
    ingest-pending drops:
      - any path with a `_`-prefixed directory component at any depth —
        the wiki-internal convention (`_templates/`, `_drafts/`,
        `_archive/`, ...);
      - the wiki root's own `docs/` directory (wiki-meta docs such as
        `docs/schema-decisions.md`, distinct from the project-level
        `docs_path`).
    All paths in the result are relative to `wiki_root`.

    Unmanifested raw: `.md` files directly under `raw/` and `raw/snapshots/`
    whose filename does not appear anywhere in `raw/MANIFEST.md`'s text as a
    whole-token occurrence (word-boundary match via `_manifest_mentions` —
    a bare substring test would treat `a.md` as manifested whenever the
    manifest mentions `data.md`). If MANIFEST.md is missing, every raw `.md`
    file is listed and `no_manifest: True` is added to the result.
    """
    wiki_root = wiki_root.resolve()

    cfg = resolve_wiki.parse_project_config(wiki_root)
    docs_ignore = set(cfg.get("docs_ignore") or [])
    docs_abs = resolve_wiki.resolve_docs_path(wiki_root, cfg)

    wiki_dir = wiki_root / "wiki"
    raw_dir = wiki_root / "raw"

    strays: list[str] = []
    for md in sorted(wiki_root.rglob("*.md")):
        if md.is_relative_to(wiki_dir) or md.is_relative_to(raw_dir):
            continue
        if docs_abs is not None and md.is_relative_to(docs_abs):
            continue
        rel = md.relative_to(wiki_root)
        parts = rel.parts
        if any(part in docs_ignore for part in parts[:-1]):
            continue
        if any(part.startswith("_") for part in parts[:-1]):
            continue  # wiki-internal convention: _templates/, _drafts/, ...
        if len(parts) > 1 and parts[0] == "docs":
            continue  # the wiki's own docs/ (wiki-meta), not the docs_path
        if len(parts) == 1 and parts[0] in _ROOT_CONFIG_SKIP:
            continue
        strays.append(str(rel))

    manifest = raw_dir / "MANIFEST.md"
    no_manifest = not manifest.is_file()
    manifest_text = "" if no_manifest else manifest.read_text()

    raw_unmanifested: list[str] = []
    for sub in (raw_dir, raw_dir / "snapshots"):
        if not sub.is_dir():
            continue
        for md in sorted(sub.glob("*.md")):
            if md.name == "MANIFEST.md":
                continue
            if no_manifest or not _manifest_mentions(manifest_text, md.name):
                raw_unmanifested.append(str(md.relative_to(wiki_root)))

    result: dict = {
        "strays": strays,
        "raw_unmanifested": raw_unmanifested,
        "docs_path": str(docs_abs) if docs_abs is not None else None,
    }
    if no_manifest:
        result["no_manifest"] = True
    return result


def _resolve_wiki_for_cwd(cwd: Path, reg_path: str | None) -> Path | None:
    """Resolve the wiki for `cwd` for HOOK purposes: `cwd` itself first
    (when it is a wiki), else a registered wiki with a PATH RELATIONSHIP
    to `cwd` — `cwd` inside the wiki, or the wiki inside `cwd` (covers a
    project root above its nested research/ wiki). This is deliberately
    stricter than resolve_wiki.py's interactive fallback, which offers the
    single registered wiki for ANY cwd: hooks fire in every project, so an
    unrelated cwd must never be attributed to someone else's wiki —
    misattribution means breadcrumbs and nags in projects that have
    nothing to do with the wiki. No related entry (or several — ambiguous)
    -> None; hooks degrade to silence rather than guessing."""
    cwd = cwd.resolve()
    if resolve_wiki.is_wiki(cwd):
        return cwd
    entries = resolve_wiki.load_registry(reg_path)
    related: list[Path] = []
    for e in entries:
        wiki = Path(e["path"]).resolve()
        if not resolve_wiki.is_wiki(wiki):
            continue
        if cwd.is_relative_to(wiki) or wiki.is_relative_to(cwd):
            related.append(wiki)
    if len(related) == 1:
        return related[0]
    return None


def _breadcrumbs_path(reg_path: str | None) -> Path | None:
    """Breadcrumbs live alongside registry.txt, in the same
    CLAUDE_PLUGIN_DATA-derived data dir."""
    if not reg_path:
        return None
    return Path(reg_path).parent / "session-breadcrumbs.jsonl"


def record_breadcrumb(cwd: Path, session_id: str, date: str) -> dict:
    """SessionEnd hook write side: append one activity breadcrumb for the
    wiki resolved from `cwd`.

    No wiki resolves for `cwd` -> no-op, {"recorded": False, "reason": "no
    wiki"}, nothing written. Non-wiki projects must produce zero noise.

    Otherwise appends a single JSON line {"cwd", "wiki", "date",
    "session_id"} to `<registry-data-dir>/session-breadcrumbs.jsonl` (plain
    append, no lock — garbled lines are tolerated at read time, same
    posture as the pattern-jot). Growth is bounded: when the post-append
    file exceeds 1000 lines it is rewritten (atomic tmp+rename) to its
    newest 500 — session_check only ever needs the newest line per wiki,
    so old lines carry no value.
    """
    reg_path = resolve_wiki._default_registry_path()
    wiki = _resolve_wiki_for_cwd(Path(cwd), reg_path)
    if wiki is None:
        return {"recorded": False, "reason": "no wiki"}

    path = _breadcrumbs_path(reg_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "cwd": str(Path(cwd).resolve()),
        "wiki": str(wiki),
        "date": date,
        "session_id": session_id,
    }
    with open(path, "a") as f:
        f.write(json.dumps(row) + "\n")

    lines = path.read_text().splitlines(keepends=True)
    if len(lines) > 1000:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text("".join(lines[-500:]))
        tmp.replace(path)  # atomic

    return {"recorded": True, "wiki": str(wiki)}


def _newest_breadcrumb_date(breadcrumbs_path: Path | None, wiki: Path) -> str | None:
    """Newest `date` among breadcrumb lines recorded for `wiki`. Tolerant
    parse: garbled/non-JSON lines and lines for other wikis are skipped,
    never a crash."""
    if breadcrumbs_path is None or not breadcrumbs_path.is_file():
        return None
    wiki_str = str(wiki)
    newest: str | None = None
    with open(breadcrumbs_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(row, dict) or row.get("wiki") != wiki_str:
                continue
            d = row.get("date")
            if not isinstance(d, str):
                continue
            if newest is None or d > newest:
                newest = d
    return newest


_SESSION_PAGE_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _newest_session_page_date(wiki: Path) -> str | None:
    """Newest date parsed from `wiki/sessions/*.md` filenames (the
    `YYYY-MM-DD-<slug>.md` convention `/session-close` writes). Missing
    directory or no matching pages -> None (treated as 0000-00-00 by the
    caller)."""
    sessions_dir = wiki / "wiki" / "sessions"
    if not sessions_dir.is_dir():
        return None
    newest: str | None = None
    for md in sessions_dir.glob("*.md"):
        m = _SESSION_PAGE_DATE_RE.match(md.name)
        if not m:
            continue
        d = m.group(1)
        if newest is None or d > newest:
            newest = d
    return newest


def session_check(cwd: Path) -> dict:
    """SessionStart hook read side: is there unclosed session work for the
    wiki resolved from `cwd`?

    No wiki resolves -> {"status": "no-wiki"}, silent by contract (CLI
    prints nothing).

    Otherwise compares the newest breadcrumb date for that wiki against
    the newest `wiki/sessions/*.md` page date (missing/absent treated as
    the sentinel "0000-00-00" for the comparison only — the returned dict
    always carries the real value, None when absent):
      - breadcrumb strictly newer -> {"status": "unclosed", "wiki",
        "last_activity", "last_close"}.
      - otherwise (including "never recorded any activity") ->
        {"status": "closed", "wiki"}.
    """
    reg_path = resolve_wiki._default_registry_path()
    wiki = _resolve_wiki_for_cwd(Path(cwd), reg_path)
    if wiki is None:
        return {"status": "no-wiki"}

    breadcrumbs_path = _breadcrumbs_path(reg_path)
    last_activity = _newest_breadcrumb_date(breadcrumbs_path, wiki)
    last_close = _newest_session_page_date(wiki)

    activity_key = last_activity or "0000-00-00"
    close_key = last_close or "0000-00-00"
    if activity_key > close_key:
        return {"status": "unclosed", "wiki": str(wiki),
                "last_activity": last_activity, "last_close": last_close}
    return {"status": "closed", "wiki": str(wiki)}


def _cmd_append_once(path_str: str, marker: str, text: str, heading: str | None) -> int:
    path = Path(path_str)
    try:
        result = append_once(path, marker, text, heading=heading)
    except OSError as exc:
        print(json.dumps({"appended": False, "error": str(exc)}))
        return 2
    print(json.dumps(result))
    return 0


def _cmd_jot_append(home_str: str, session: str, date: str, observations: list[str],
                     personas: list[str] | None = None, wiki: str | None = None) -> int:
    home = Path(home_str)
    if not home.is_dir():
        print(json.dumps({"appended": 0, "skipped": False,
                          "error": f"factory home not found: {home}"}))
        return 2
    result = jot_append(home, session, date, observations, personas=personas, wiki=wiki)
    print(json.dumps(result))
    return 0


def _cmd_sweep_scan(wiki_root_str: str) -> int:
    wiki_root = Path(wiki_root_str)
    if not wiki_root.is_dir():
        print(json.dumps({"error": f"wiki root not found or unreadable: {wiki_root}"}))
        return 2
    try:
        result = sweep_scan(wiki_root)
    except OSError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    print(json.dumps(result))
    return 0


def _cmd_breadcrumb(cwd_str: str, session_id: str, date: str) -> int:
    """Crash containment: hooks must never break sessions. On ANY failure,
    print NOTHING to stdout (SessionEnd/SessionStart stdout can enter
    session context), one short line to stderr, exit 0. Exit 2 only for an
    unusable --cwd."""
    cwd = Path(cwd_str)
    if not cwd.is_dir():
        print(f"llm-wiki hook: cwd not found: {cwd}", file=sys.stderr)
        return 2
    try:
        result = record_breadcrumb(cwd, session_id, date)
        if result.get("recorded") is False and result.get("reason") == "no wiki":
            return 0  # non-wiki projects must produce zero noise
        print(json.dumps(result))
    except Exception as exc:  # noqa: BLE001 — a hook must never crash a session
        print(f"llm-wiki hook: {exc}", file=sys.stderr)
    return 0


def _cmd_session_check(cwd_str: str) -> int:
    """Crash containment: same contract as _cmd_breadcrumb — any failure is
    one stderr line and exit 0, never stdout noise, never a crash."""
    cwd = Path(cwd_str)
    if not cwd.is_dir():
        print(f"llm-wiki hook: cwd not found: {cwd}", file=sys.stderr)
        return 2
    try:
        result = session_check(cwd)
        if result.get("status") != "unclosed":
            return 0  # no-wiki and closed are both silent by contract

        wiki = result["wiki"]
        last_activity = result.get("last_activity")
        last_close = result.get("last_close") or "none"
        message = (
            f"llm-wiki: unclosed session work detected in {wiki} "
            f"(last activity {last_activity}, last session page {last_close}) "
            f"— run /session-close to catch the wiki up."
        )
        try:
            stray_count = len(sweep_scan(Path(wiki)).get("strays", []))
        except OSError:
            stray_count = 0
        if stray_count:
            message += f" {stray_count} stray file(s) awaiting sweep."
        print(message)
    except Exception as exc:  # noqa: BLE001 — a hook must never crash a session
        print(f"llm-wiki hook: {exc}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Session-close operations for AI Factory wikis.")
    subparsers = parser.add_subparsers(dest="subcommand")

    append_p = subparsers.add_parser(
        "append-once",
        help="Append text to a file unless a marker already occurs in it.")
    append_p.add_argument("path", help="Path to the file to append to.")
    append_p.add_argument("--marker", required=True, help="Idempotency marker embedded in --text.")
    append_p.add_argument("--text", required=True,
                           help="Text block to append (must contain --marker). Use '-' to read from stdin.")
    append_p.add_argument("--heading", default=None,
                           help="Section heading to insert under (e.g. '## What changed this quarter').")

    jot_p = subparsers.add_parser(
        "jot-append",
        help="Append session-deduped observations to the factory home's pattern jot.")
    jot_p.add_argument("--home", required=True, help="Path to the factory home.")
    jot_p.add_argument("--session", required=True, help="Session ID.")
    jot_p.add_argument("--date", required=True, help="Session date (YYYY-MM-DD).")
    jot_p.add_argument("--observation", dest="observations", action="append", default=[],
                        help="Observation text (repeatable).")
    jot_p.add_argument("--persona", dest="personas", action="append", default=[],
                        help="Persona slug this call's observations belong to (repeatable).")
    jot_p.add_argument("--wiki", default=None,
                        help="Wiki/project path this call's observations concern (provenance).")

    sweep_p = subparsers.add_parser(
        "sweep-scan",
        help="Read-only detection of stray markdown and unmanifested raw/ drops.")
    sweep_p.add_argument("--wiki-root", required=True, help="Path to the wiki root.")

    breadcrumb_p = subparsers.add_parser(
        "breadcrumb",
        help="SessionEnd hook write side: record one activity breadcrumb for the resolved wiki.")
    breadcrumb_p.add_argument("--cwd", required=True, help="Project working directory (from the hook's stdin JSON).")
    breadcrumb_p.add_argument("--session-id", required=True, help="Session ID (from the hook's stdin JSON).")
    breadcrumb_p.add_argument("--date", required=True, help="Session date (YYYY-MM-DD).")

    session_check_p = subparsers.add_parser(
        "session-check",
        help="SessionStart hook read side: warn if the resolved wiki has unclosed session work.")
    session_check_p.add_argument("--cwd", required=True, help="Project working directory (from the hook's stdin JSON).")

    args = parser.parse_args(argv)

    if args.subcommand == "append-once":
        text = sys.stdin.read() if args.text == "-" else args.text
        return _cmd_append_once(args.path, args.marker, text, args.heading)
    if args.subcommand == "jot-append":
        return _cmd_jot_append(args.home, args.session, args.date, args.observations,
                                personas=args.personas, wiki=args.wiki)
    if args.subcommand == "sweep-scan":
        return _cmd_sweep_scan(args.wiki_root)
    if args.subcommand == "breadcrumb":
        return _cmd_breadcrumb(args.cwd, args.session_id, args.date)
    if args.subcommand == "session-check":
        return _cmd_session_check(args.cwd)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
