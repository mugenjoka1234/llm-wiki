#!/usr/bin/env python3
"""Team-YAML subset parser and team-resolution operations for AI Factory teams.

Consumes the factory home registered via resolve_wiki.py (register-factory-home)
and resolves a team's YAML manifest (teams/<name>.yaml) against the personas
present in agents/ under that home.

YAML subset contract (hand-rolled, stdlib only — no PyYAML on this machine):
  - Top-level `key: value` scalars (quoted or bare; matching quotes stripped).
  - A `members:` block whose items start with `- agent:` (2-space indent) and
    continue with indented `key: value` lines belonging to that item.
  - `#` comment lines and blank lines are ignored.
  - Unknown top-level blocks (a `key:` line with no inline value, followed by
    indented lines) are skipped without error.
  - Values are split on the FIRST `: ` only, so a quoted value may itself
    contain colons (e.g. `invocation: "on-demand — only when: needed"`).

Usage:
  team_ops.py resolve-team <name>
      Resolve a team's members; JSON on stdout. Exit 0 on success (including
      partial — missing members are data, not an error). Exit 2 when the
      factory home is absent/missing or the team file does not exist; a
      JSON error with a hint is printed to stdout in that case too.
  team_ops.py validate-persona <path>
      Validate a persona file's frontmatter/anchors; JSON on stdout. Exit 0
      when ok, 1 when there are errors, 2 when the path isn't a file.
  team_ops.py upgrade-persona <path> [--description TEXT]
      Idempotently add a missing description / fence Immutable Anchors;
      JSON on stdout. Exit 0, or 2 when the path isn't a file.
  team_ops.py assemble-context --wiki-root <path> --persona <path>
      Assemble a budgeted per-persona context manifest (orientation files +
      self-authored prior positions); JSON on stdout. Exit 0, or 2 when the
      wiki root or persona path is unreadable.
  team_ops.py anchors-unchanged <original> <edited>
      Verify the fenced Immutable Anchors survived an edit: byte-identical
      content, well-formed marker structure, and unchanged section location
      (nearest preceding heading) per fence pair; JSON on stdout. This is
      the deterministic backstop /improve calls after every edit — exit 0
      when unchanged (ok), exit 1 when changed/malformed (not ok), exit 2
      when either path is unreadable. These exit codes are the /improve
      skill's branch points; keep them exact.
  team_ops.py search-candidates --query "<terms>" [--division D]
                                 [--source starter|catalog|references|all]
      Rank staffing candidates across the starter roster
      (assets/starter-roster/, may not exist yet), the vendored
      agency-agents catalog (assets/agency-agents/, division = first
      directory component), and a factory home's references/** pool
      (recursive, frontmatter files only; requires a resolvable factory
      home). JSON {"results": [{name, source, division, description, path,
      score}, ...]} on stdout, plus "suggestions": [<catalog division
      names>] when results is empty. Exit 0 always, except exit 2 when
      --source references is requested and no factory home is resolvable.
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


class TeamError(Exception):
    """Raised when a team manifest cannot be resolved (e.g. file not found)."""


_TOP_LEVEL_KEYS = ("id", "name", "purpose", "project")


def _unquote(s: str) -> str:
    """Strip surrounding whitespace and one matching pair of quotes."""
    v = s.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        v = v[1:-1]
    return v


def parse_team_yaml(text: str) -> dict:
    """Parse the team-YAML subset described in the module docstring.

    Returns a dict with keys `id, name, purpose, project` (str, when present)
    and `members` (list of dicts with keys `agent, role, model, effort,
    invocation, note` — absent keys are simply omitted from each dict).
    """
    result: dict = {"members": []}
    in_members = False
    skip_block = False
    current_member: dict | None = None

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))

        if skip_block:
            if indent == 0:
                skip_block = False
                # fall through: this line ends the skipped block
            else:
                continue

        if in_members:
            if stripped.startswith("- "):
                item_line = stripped[2:]
                k, sep, v = item_line.partition(": ")
                if sep and k == "agent":
                    current_member = {"agent": _unquote(v)}
                    result["members"].append(current_member)
                continue
            if current_member is not None and indent >= 4:
                k, sep, v = stripped.partition(": ")
                if sep:
                    current_member[k] = _unquote(v)
                continue
            # Any other line (indent 0 or 2, not a new item) ends the block.
            in_members = False
            current_member = None
            # fall through to top-level handling for this line

        if stripped == "members:":
            in_members = True
            current_member = None
            continue

        k, sep, v = stripped.partition(": ")
        if not sep:
            # Top-level `key:` with no inline value — an unknown block header
            # (e.g. a list block we don't model). Skip its indented children.
            skip_block = True
            continue
        if k in _TOP_LEVEL_KEYS:
            result[k] = _unquote(v)
        # Other top-level scalar keys (framework, orchestration,
        # performance_rating, tasks_completed, last_used, notes, ...) are
        # part of the real team-file schema but outside this subset's
        # contract — ignored silently.

    return result


def resolve_team(home: Path, team_name: str) -> dict:
    """Resolve `<home>/teams/<team_name>.yaml` against personas in `<home>/agents/`.

    Returns {"team": <meta>, "members": [...resolved...], "missing": [...]}.
    Members whose persona file is missing are DATA (listed in "missing"),
    not an error — only a nonexistent team file raises TeamError.
    """
    team_file = home / "teams" / f"{team_name}.yaml"
    if not team_file.is_file():
        raise TeamError(f"team file not found: {team_file}")

    parsed = parse_team_yaml(team_file.read_text())
    members = parsed.pop("members")
    meta = parsed

    resolved: list[dict] = []
    missing: list[dict] = []
    for member in members:
        agent = member.get("agent")
        persona_file = home / "agents" / f"{agent}.md"
        if persona_file.is_file():
            entry = dict(member)
            entry["file"] = str(persona_file)
            resolved.append(entry)
        else:
            missing.append({"agent": agent, "role": member.get("role")})

    return {"team": meta, "members": resolved, "missing": missing}


# --- Persona validation + idempotent lazy upgrade ---------------------------
#
# Frontmatter `description:` parsing mirrors
# scripts/tests/test_agent_descriptions.py::_description exactly (same two
# regexes) so the 600-char budget means the same thing in both places.

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
_DESCRIPTION_RE = re.compile(
    r"^description:\s*(.*?)(?=^[a-zA-Z_-]+:|\Z)", re.MULTILINE | re.DOTALL)

DESCRIPTION_CHAR_BUDGET = 600
IMMUTABLE_HEADING = "## Immutable Anchors"
IMMUTABLE_BEGIN = "<!-- IMMUTABLE:BEGIN -->"
IMMUTABLE_END = "<!-- IMMUTABLE:END -->"
_MIN_DENYLIST_NAME_LEN = 4


def _frontmatter_description(text: str) -> str | None:
    """Extract and unquote the frontmatter `description:` value.

    Returns None when the frontmatter block, the `description:` key, or its
    value is missing/empty. Double-quoted values are unescaped
    (`\\"` -> `"`, `\\\\` -> `\\`) — the inverse of what upgrade_persona
    writes, so an inserted description round-trips intact.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    dm = _DESCRIPTION_RE.search(m.group(1))
    if not dm:
        return None
    raw = dm.group(1).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        value = re.sub(r'\\(["\\])', r"\1", raw[1:-1])
    else:
        value = _unquote(raw)
    return value or None


def validate_persona(path: Path, denylist: list[str]) -> dict:
    """Validate a persona file's frontmatter, citation anchor, and denylist.

    Returns {"ok": bool, "errors": [...], "warnings": [...]}.

    Errors (refusal-grade): missing/empty `description:`; description over
    DESCRIPTION_CHAR_BUDGET chars; no CITATION_STANDARD anchor anywhere in
    the file; a denylist name found as a case-insensitive substring anywhere
    in the file (frontmatter or body).

    Warnings: description not starting with "Use when"; no
    "## Immutable Anchors" heading; the heading is present but not yet
    fenced with the IMMUTABLE markers.
    """
    text = path.read_text()
    errors: list[str] = []
    warnings: list[str] = []

    description = _frontmatter_description(text)
    if not description:
        errors.append("missing description")
    else:
        if len(description) > DESCRIPTION_CHAR_BUDGET:
            errors.append(
                f"description exceeds {DESCRIPTION_CHAR_BUDGET} chars "
                f"({len(description)})")
        if not description.startswith("Use when"):
            warnings.append('description does not start with "Use when"')

    if "CITATION_STANDARD" not in text:
        errors.append("missing citation anchor (CITATION_STANDARD)")

    lower_text = text.lower()
    for name in denylist:
        if name.lower() in lower_text:
            errors.append(f"denylist: {name}")

    if IMMUTABLE_HEADING not in text:
        warnings.append('missing "## Immutable Anchors" heading')
    elif IMMUTABLE_BEGIN not in text or IMMUTABLE_END not in text:
        warnings.append("anchors not yet fenced")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6} .*", re.MULTILINE)


def _anchor_heading(text: str, pos: int) -> tuple[str, int]:
    """The nearest markdown heading line (`^#{1,6} ...`) starting before
    `pos`, plus its occurrence ordinal: which occurrence of that SAME heading
    text it is, counted 1-based from the top of the file. `("", 0)` when no
    heading precedes `pos`.

    The ordinal is what defeats a byte-identical duplicate heading planted
    elsewhere — heading text alone would compare equal, but a fence moved
    under the second occurrence of the same text carries a different
    ordinal.
    """
    headings = [m.group(0) for m in _MARKDOWN_HEADING_RE.finditer(text, 0, pos)]
    if not headings:
        return ("", 0)
    nearest = headings[-1]
    return (nearest, headings.count(nearest))


def _heading_occurrences(text: str, heading: str) -> int:
    """How many markdown heading LINES in `text` are exactly `heading`."""
    return sum(1 for m in _MARKDOWN_HEADING_RE.finditer(text)
               if m.group(0) == heading)


def _extract_anchor_pairs(text: str) -> list[tuple[str, int, str]] | None:
    """Return `(anchor_heading, heading_ordinal, fenced_content)` for each
    IMMUTABLE:BEGIN/END pair in `text`, in document order — or None when the
    markers are structurally malformed.

    Balance invariant: walked left-to-right, the markers must strictly
    alternate BEGIN -> END starting with BEGIN and ending with END. Any
    violation — an orphan BEGIN with no END, an END before its BEGIN, a
    nested BEGIN inside an open fence — returns None instead of silently
    dropping the unmatched marker (a purely local pair-scan would let an
    orphan BEGIN smuggle unfenced text past the guard).

    `(anchor_heading, heading_ordinal)` is the nearest markdown heading line
    preceding the pair's BEGIN marker plus which occurrence of that heading
    text it is (see `_anchor_heading`) — together they pin each fence to its
    specific section, not just to any section that happens to share the
    heading text.
    """
    events: list[tuple[int, str, int]] = []
    for m in re.finditer(re.escape(IMMUTABLE_BEGIN), text):
        events.append((m.start(), "begin", m.end()))
    for m in re.finditer(re.escape(IMMUTABLE_END), text):
        events.append((m.start(), "end", m.end()))
    events.sort()

    pairs: list[tuple[str, int, str]] = []
    open_begin: tuple[int, int] | None = None  # (start, content-start) of open BEGIN
    for start, kind, end in events:
        if kind == "begin":
            if open_begin is not None:  # nested BEGIN
                return None
            open_begin = (start, end)
        else:
            if open_begin is None:  # END before any BEGIN
                return None
            begin_start, content_start = open_begin
            heading, ordinal = _anchor_heading(text, begin_start)
            pairs.append((heading, ordinal, text[content_start:start]))
            open_begin = None
    if open_begin is not None:  # dangling BEGIN
        return None
    return pairs


def anchors_unchanged(original: Path, edited: Path) -> dict:
    """Deterministic /improve guard: verify fenced Immutable Anchors survived
    an edit untouched — bytes, fence structure, and section location.

    Checks, in order (first failure wins); returns {"ok": bool,
    "reason": str|None}:

    1. Balance invariant, per file: BEGIN/END markers must strictly
       alternate BEGIN -> END (no orphan BEGIN, no END-first, no nested
       BEGIN). Violation -> reason "malformed fence markers in original" /
       "malformed fence markers in edited" (edited is only checked once the
       original is well-formed).
    2. Presence: ORIGINAL with zero pairs -> exactly "original has no fenced
       anchors" (an unfenced persona must be lazily upgraded via
       `upgrade_persona` before /improve may touch it). EDITED with zero
       pairs -> exactly "edited file removed the fence".
    3. Pair count must match (some-but-not-all fences added/removed).
    4. Heading-anchored pairwise compare, in document order: each pair's
       (nearest preceding markdown heading, heading-occurrence ordinal,
       fenced content) must be byte-equal. Content drift -> "fenced anchor
       pair {i} content changed"; identical bytes relocated under a
       different section heading -> "fence pair {i} moved (heading
       changed)"; identical bytes relocated under a byte-identical
       DUPLICATE of the same heading text (a planted second occurrence) ->
       "fence pair {i} moved (heading occurrence changed)".
    5. No new occurrences of any pair's anchor heading text in the edited
       file: a planted duplicate of an anchor heading is refused even when
       the fence itself has not moved -> "duplicate anchor heading added".

    What this guard does NOT protect: prose inserted or rewritten OUTSIDE
    the fences — even immediately adjacent to a fence or within the same
    section — passes. Catching adversarial edits to unfenced text is the
    human diff review's job; this guard protects fenced bytes, fence
    structure, and fence location-by-section only.
    """
    original_text = original.read_text()
    original_pairs = _extract_anchor_pairs(original_text)
    if original_pairs is None:
        return {"ok": False, "reason": "malformed fence markers in original"}
    if not original_pairs:
        return {"ok": False, "reason": "original has no fenced anchors"}

    edited_text = edited.read_text()
    edited_pairs = _extract_anchor_pairs(edited_text)
    if edited_pairs is None:
        return {"ok": False, "reason": "malformed fence markers in edited"}
    if not edited_pairs:
        return {"ok": False, "reason": "edited file removed the fence"}

    if len(original_pairs) != len(edited_pairs):
        return {"ok": False,
                "reason": (f"fenced anchor count changed ({len(original_pairs)} -> "
                           f"{len(edited_pairs)})")}

    for i, ((orig_heading, orig_ordinal, orig_content),
            (edit_heading, edit_ordinal, edit_content)) \
            in enumerate(zip(original_pairs, edited_pairs)):
        if orig_content != edit_content:
            return {"ok": False, "reason": f"fenced anchor pair {i} content changed"}
        if orig_heading != edit_heading:
            return {"ok": False, "reason": f"fence pair {i} moved (heading changed)"}
        if orig_ordinal != edit_ordinal:
            return {"ok": False,
                    "reason": f"fence pair {i} moved (heading occurrence changed)"}

    for heading in {h for h, _, _ in original_pairs if h}:
        if _heading_occurrences(edited_text, heading) \
                > _heading_occurrences(original_text, heading):
            return {"ok": False, "reason": "duplicate anchor heading added"}

    return {"ok": True, "reason": None}


def build_denylist(home: Path) -> list[str]:
    """Build the denylist of project names personas must not mention.

    Sources (combined, deduped, order-preserving):
      - registry.txt: the first `|`-field (the registered wiki's absolute
        path) of each non-`!`-prefixed line, via resolve_wiki's own registry
        reader (`_default_registry_path()` + `load_registry()` — no
        path-discovery logic re-implemented here). The path's final
        component is taken as the project name (the raw field is an
        absolute path, not a bare slug; see task-2-report.md for why).
      - <home>/instructions/project-names.txt, if present: one name per
        line; blank lines and `#`-comment lines are ignored.
    Names shorter than 4 chars are dropped (avoids absurd substring hits,
    e.g. "ai", "go").
    """
    names: list[str] = []

    reg_path = resolve_wiki._default_registry_path()
    for entry in resolve_wiki.load_registry(reg_path):
        name = Path(entry["path"]).name
        if name:
            names.append(name)

    names_file = home / "instructions" / "project-names.txt"
    if names_file.is_file():
        for line in names_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            names.append(line)

    deduped = list(dict.fromkeys(names))
    return [n for n in deduped if len(n) >= _MIN_DENYLIST_NAME_LEN]


def _atomic_write(path: Path, text: str) -> None:
    """Atomic tmp+rename write, mirroring resolve_wiki.py's _write_registry."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)  # atomic


def upgrade_persona(path: Path, description: str | None) -> dict:
    """Idempotently upgrade a persona file: add a missing description, fence
    the Immutable Anchors section. Atomic write (tmp+rename); no-op (no
    write at all) when nothing changes.

    Returns {"changed": bool, "added_description": bool, "fenced": bool}.
    """
    original = path.read_text()
    lines = original.split("\n")
    added_description = False

    if description and _frontmatter_description(original) is None \
            and lines and lines[0].strip() == "---":
        fm_close_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                fm_close_idx = i
                break
        if fm_close_idx is not None:
            role_idx = name_idx = None
            for i in range(1, fm_close_idx):
                key = lines[i].split(":", 1)[0].strip()
                if key == "role" and role_idx is None:
                    role_idx = i
                elif key == "name" and name_idx is None:
                    name_idx = i
            insert_after = role_idx if role_idx is not None else name_idx
            if insert_after is not None:
                # Escape for a YAML double-quoted scalar: backslashes first,
                # then double quotes (unescaped by _frontmatter_description).
                escaped = description.replace("\\", "\\\\").replace('"', '\\"')
                lines.insert(insert_after + 1, f'description: "{escaped}"')
                added_description = True

    text = "\n".join(lines)
    fenced = False
    if IMMUTABLE_BEGIN not in text and IMMUTABLE_END not in text:
        lines = text.split("\n")
        heading_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith(IMMUTABLE_HEADING):
                heading_idx = i
                break
        if heading_idx is not None:
            end_idx = len(lines)
            for j in range(heading_idx + 1, len(lines)):
                if lines[j].startswith("## "):
                    end_idx = j
                    break
            lines.insert(end_idx, IMMUTABLE_END)
            lines.insert(heading_idx + 1, IMMUTABLE_BEGIN)
            fenced = True
        text = "\n".join(lines)

    changed = added_description or fenced
    if changed:
        _atomic_write(path, text)

    return {"changed": changed, "added_description": added_description, "fenced": fenced}


# --- Budgeted context assembly ----------------------------------------------
#
# `assemble_context` reads wiki-page frontmatter (Phase 2 conventions:
# `type:`, `author:` list, `tags:` list, `last-updated:`, `summary:`) and
# builds a per-persona manifest: orientation reading (index + overview + up
# to ORIENTATION_FOCUS_PAGES focus-tag pages) plus up to
# PRIOR_POSITIONS_LIMIT self-authored prior positions. `_frontmatter` is a
# small hand-rolled reader kept local to this module — it must NOT import
# `assets/scripts/lint.py`, which ships into wikis and is not an importable
# library from here.

ORIENTATION_FOCUS_PAGES = 5
PRIOR_POSITIONS_LIMIT = 10

_FRONTMATTER_BLOCK_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_POSITION_LINE_RE = re.compile(r"^-\s+\*\*(.+?)\*\*:\s*.*$")
_POSITION_HEADING = {"decision": "## Positions", "session": "## Work units"}
_NO_POSITION_PREFIX = "(no self-authored position recorded) "


def _frontmatter(path: Path) -> dict:
    """Parse a wiki/persona page's frontmatter block.

    Handles the subset this module needs: `key: value` scalars (quotes
    stripped), `key: [a, b]` / `key: []` inline lists, and multi-line
    `key:` blocks followed by indented `- item` lines. Not a general YAML
    parser — matches the hand-rolled frontmatter convention shared by wiki
    pages and persona files. Returns {} when there is no frontmatter block.

    LIMITATION — no multi-line SCALAR continuation: only `- item` list
    blocks continue across lines. A folded/literal block scalar
    (`key: >-` / `key: |`) comes back as the literal indicator string
    (e.g. `'>-'`), NOT the continuation text, and an unindicated wrapped
    scalar loses its continuation lines. In particular, `description:`
    (which may span lines in persona frontmatter) must be read via
    `_frontmatter_description`, which handles continuation correctly —
    never via this helper.
    """
    text = path.read_text()
    m = _FRONTMATTER_BLOCK_RE.match(text)
    if not m:
        return {}

    fm: dict = {}
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        key, sep, val = stripped.partition(":")
        if not sep:
            i += 1
            continue
        key = key.strip()
        val = val.strip()

        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [] if not inner else [_unquote(p.strip()) for p in inner.split(",")]
            i += 1
            continue

        if val == "":
            items: list = []
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("- ") \
                    and (lines[j].startswith(" ") or lines[j].startswith("\t")):
                items.append(_unquote(lines[j].strip()[2:].strip()))
                j += 1
            if items:
                fm[key] = items
                i = j
                continue
            fm[key] = ""
            i += 1
            continue

        fm[key] = _unquote(val)
        i += 1

    return fm


def _date_from_filename(name: str) -> str:
    """Extract a leading YYYY-MM-DD date prefix from a filename, or ''."""
    m = _DATE_PREFIX_RE.match(name)
    return m.group(1) if m else ""


_VALID_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _recency_key(date_val: str) -> tuple[int, str]:
    """Sort key for newest-first ordering (use with reverse=True).

    Valid YYYY-MM-DD dates sort by recency; malformed or missing dates
    (e.g. the template placeholder `TBD`, which would otherwise sort FIRST
    under a plain reversed string sort because 'T' > '2' in ASCII) sort
    LAST deliberately.
    """
    if _VALID_DATE_RE.match(date_val):
        return (1, date_val)
    return (0, "")


def _section_lines(text: str, heading: str) -> list[str]:
    """Return the lines between an exact `## Heading` line and the next
    `## ` heading (or EOF). Empty list if the heading isn't found."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break
    if start is None:
        return []
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return lines[start:end]


def _self_authored_position_line(text: str, heading: str, persona_name: str) -> str | None:
    """Find the `- **<persona_name>**: ...` line (case-insensitive on the
    name) within the given section heading's body. Returns the line
    verbatim (stripped of surrounding whitespace only), or None."""
    for line in _section_lines(text, heading):
        stripped = line.strip()
        m = _POSITION_LINE_RE.match(stripped)
        if m and m.group(1).strip().lower() == persona_name.lower():
            return stripped
    return None


def assemble_context(home: Path, wiki_root: Path, persona_file: Path) -> dict:
    """Assemble a budgeted per-persona context manifest.

    `home` is accepted for signature parity with the other team_ops entry
    points (resolve_team, build_denylist) and reserved for future use — it
    is not consulted here; `wiki_root` (the project root containing a
    `wiki/` directory) and `persona_file` are self-sufficient.

    Returns:
      {"persona": <abs path str>,
       "orientation": [<abs path str>, ...],   # index, overview, focus pages
       "prior_positions": [{"page": "[[slug]]", "date": "YYYY-MM-DD",
                             "type": "decision"|"session",
                             "position": "<self-authored line or flagged
                                           summary fallback>"}, ...],
       "budget": {"focus_pages": ORIENTATION_FOCUS_PAGES,
                  "prior_positions": PRIOR_POSITIONS_LIMIT},
       "warnings": [...]}   # e.g. missing index.md/overview.md; never fails

    Focus-tag pages: persona frontmatter `domain:` list (may be absent, in
    which case there are no focus pages) intersected case-insensitively
    with each candidate page's `tags:`. Candidates are non-synthesis pages
    directly under `wiki/` (top level only — skip `_`-prefixed files and
    `catalog` pages); sorted by `last-updated` descending, capped at
    ORIENTATION_FOCUS_PAGES.

    Prior positions: `type: decision` or `type: session` pages anywhere
    under `wiki/` whose `author:` list contains the persona's frontmatter
    `name:` (case-insensitive); sorted by `last-updated` (falling back to
    a YYYY-MM-DD filename prefix) descending, capped at
    PRIOR_POSITIONS_LIMIT. `position` is the self-authored
    `- **<Name>**: ...` line from `## Positions` (decision) or
    `## Work units` (session); when no such line exists, `position` falls
    back to the page's `summary:` prefixed with
    "(no self-authored position recorded) " rather than silently
    paraphrasing the missing self-authored content.

    Both recency sorts use `_recency_key`: malformed/non-YYYY-MM-DD
    `last-updated` values (e.g. the template placeholder `TBD`) sort LAST,
    not first by ASCII accident.
    """
    persona_fm = _frontmatter(persona_file)
    persona_name = persona_fm.get("name", "")
    domain_tags = {t.lower() for t in persona_fm.get("domain", [])}

    warnings: list[str] = []
    orientation: list[str] = []
    wiki_dir = wiki_root / "wiki"

    index_path = wiki_dir / "index.md"
    if index_path.is_file():
        orientation.append(str(index_path.resolve()))
    else:
        warnings.append(f"missing {index_path}")

    overview_path = wiki_dir / "overview.md"
    if overview_path.is_file():
        orientation.append(str(overview_path.resolve()))
    else:
        warnings.append(f"missing {overview_path}")

    if domain_tags and wiki_dir.is_dir():
        focus_candidates: list[tuple[str, str]] = []
        for p in sorted(wiki_dir.iterdir()):
            if not p.is_file() or p.suffix != ".md":
                continue
            if p.name.startswith("_") or p.stem == "catalog":
                continue
            fm = _frontmatter(p)
            if fm.get("type") == "synthesis":
                continue
            tags = {t.lower() for t in fm.get("tags", [])}
            if not (tags & domain_tags):
                continue
            focus_candidates.append((fm.get("last-updated", ""), str(p.resolve())))
        focus_candidates.sort(key=lambda item: _recency_key(item[0]), reverse=True)
        orientation.extend(path for _, path in focus_candidates[:ORIENTATION_FOCUS_PAGES])

    prior_candidates: list[dict] = []
    if wiki_dir.is_dir():
        for p in sorted(wiki_dir.rglob("*.md")):
            fm = _frontmatter(p)
            page_type = fm.get("type")
            heading = _POSITION_HEADING.get(page_type)
            if heading is None:
                continue
            authors = [a.lower() for a in fm.get("author", [])]
            if not persona_name or persona_name.lower() not in authors:
                continue

            date_val = fm.get("last-updated") or _date_from_filename(p.name)
            line = _self_authored_position_line(p.read_text(), heading, persona_name)
            if line is None:
                position = _NO_POSITION_PREFIX + fm.get("summary", "")
            else:
                position = line

            prior_candidates.append({
                "_sort_key": date_val or "",
                "page": f"[[{p.stem}]]",
                "date": date_val,
                "type": page_type,
                "position": position,
            })

    prior_candidates.sort(key=lambda c: _recency_key(c["_sort_key"]), reverse=True)
    prior_positions = [
        {k: v for k, v in c.items() if k != "_sort_key"}
        for c in prior_candidates[:PRIOR_POSITIONS_LIMIT]
    ]

    return {
        "persona": str(persona_file.resolve()),
        "orientation": orientation,
        "prior_positions": prior_positions,
        "budget": {"focus_pages": ORIENTATION_FOCUS_PAGES,
                   "prior_positions": PRIOR_POSITIONS_LIMIT},
        "warnings": warnings,
    }


# --- Candidate search across starter/catalog/references pools --------------
#
# search_candidates ranks candidate persona files for staffing across three
# pools: the starter roster (assets/starter-roster/ — Plan 3 content, may
# not exist yet), the vendored agency-agents catalog (assets/agency-agents/,
# division = first directory component under the catalog root), and a
# factory home's references/** pool (user-curated, recursive, frontmatter
# files only). Scoring is deliberately simple and deterministic:
# case-insensitive term overlap against name + description (+ `domain:`
# tags where present — starter/references personas in full factory format
# carry `domain:`; the vendored catalog does not). Ties break starter >
# references > catalog (the user's own curated pools outrank the generic
# catalog), then name.
#
# Catalog frontmatter is NOT factory format (no `domain:`, no fenced
# anchors) — only `name:`/`description:` are guaranteed. `description:` is
# read via `_frontmatter_description`, never the generic `_frontmatter`
# reader above: `_frontmatter` cannot follow a folded/literal block scalar
# (`description: >-` / `description: |`) and would hand back the bare
# indicator string instead of the continuation text (see its docstring).
# The live vendored catalog happens to use single-line descriptions today
# (verified against the real files), but nothing guarantees that survives a
# future re-sync, so every source reads description the robust way.

_SOURCE_PRIORITY = {"starter": 0, "references": 1, "catalog": 2}
SEARCH_SOURCES = ("starter", "catalog", "references")


def _plugin_root() -> Path:
    """The plugin/ directory, derived from this file's own location — the
    CLAUDE_PLUGIN_ROOT-equivalent lookup that works whether or not the
    plugin is actually installed via CLAUDE_PLUGIN_ROOT. Mirrors
    sync_agency_agents.py's DEFAULT_DEST derivation."""
    return Path(__file__).resolve().parent.parent


def _catalog_root() -> Path:
    return _plugin_root() / "assets" / "agency-agents"


def _starter_root() -> Path:
    return _plugin_root() / "assets" / "starter-roster"


def _division_for(root: Path, path: Path) -> str | None:
    """First directory component of `path` relative to `root`, or None when
    `path` sits directly at `root` (a root-level file with no division —
    e.g. the catalog's ATTRIBUTION.md — or a flat starter-roster/references
    pool with no subdirectories)."""
    parts = path.relative_to(root).parts
    return parts[0] if len(parts) > 1 else None


def _search_candidate(path: Path, source: str, division: str | None) -> dict | None:
    """Build a raw candidate dict from a persona/agent markdown file, or
    None when it has no parseable frontmatter or no `name:` (the
    references/ pool may hold arbitrary non-agent files; skip those
    silently rather than erroring)."""
    text = path.read_text()
    fm = _frontmatter(path)
    name = fm.get("name")
    if not name:
        return None
    description = _frontmatter_description(text) or ""
    domain = fm.get("domain", [])
    domain_tags = domain if isinstance(domain, list) else []
    return {
        "name": name,
        "source": source,
        "division": division,
        "description": description,
        "path": str(path.resolve()),
        "_domain_tags": domain_tags,
    }


def _search_pool(root: Path, source: str, require_division: bool) -> list[dict]:
    """All candidates under `root` for one source. A missing `root` yields
    an empty list, never an error — the starter roster and a home's
    references/ dir may both legitimately not exist yet."""
    if not root.is_dir():
        return []
    candidates = []
    for p in sorted(root.rglob("*.md")):
        division = _division_for(root, p)
        if require_division and division is None:
            continue  # root-level file (e.g. catalog's ATTRIBUTION.md), not a persona
        c = _search_candidate(p, source, division)
        if c:
            candidates.append(c)
    return candidates


def catalog_divisions() -> list[str]:
    """Division names (top-level directories) present in the vendored
    catalog, sorted. Used to populate search-candidates' zero-match
    "suggestions" regardless of whatever query/division/source filters
    produced the zero-match result."""
    root = _catalog_root()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def search_candidates(query: str, home: Path | None, division: str | None,
                       source: str) -> list[dict]:
    """Rank staffing candidates across the starter/catalog/references pools.

    `source` is one of "starter", "catalog", "references", "all". When
    "references" (or "all") is requested but `home` is None, the references
    pool simply contributes nothing — this is a pure function and never
    raises; the CLI (not this function) is responsible for treating an
    unusable `--source references` (no resolvable home) as an error
    (exit 2).

    `division` filters to candidates whose derived division matches
    case-insensitively (a candidate with no division — e.g. a flat starter
    roster entry — never matches a division filter).

    Returns only candidates with a nonzero term-overlap score, ranked by
    score descending, then source priority (starter > references >
    catalog), then name.
    """
    sources = SEARCH_SOURCES if source == "all" else (source,)

    candidates: list[dict] = []
    if "starter" in sources:
        candidates.extend(_search_pool(_starter_root(), "starter", require_division=False))
    if "catalog" in sources:
        candidates.extend(_search_pool(_catalog_root(), "catalog", require_division=True))
    if "references" in sources and home is not None:
        candidates.extend(_search_pool(home / "references", "references", require_division=False))

    if division is not None:
        want = division.lower()
        candidates = [c for c in candidates if (c["division"] or "").lower() == want]

    terms = [t for t in re.split(r"\s+", query.strip().lower()) if t]

    scored: list[dict] = []
    for c in candidates:
        haystack = " ".join(
            [c["name"], c["description"], " ".join(c["_domain_tags"])]).lower()
        score = sum(1 for t in terms if t in haystack)
        if score <= 0:
            continue
        entry = {k: v for k, v in c.items() if k != "_domain_tags"}
        entry["score"] = score
        scored.append(entry)

    scored.sort(key=lambda c: (-c["score"], _SOURCE_PRIORITY[c["source"]], c["name"]))
    return scored


def _resolve_factory_home_best_effort() -> Path:
    """Best-effort factory home, for callers that work even without one.

    validate-persona must still work outside any factory home (denylist
    falls back to registry-derived names only), and assemble-context takes
    an explicit --wiki-root/--persona pair rather than a --home flag — a
    sentinel path is used so lookups scoped under the returned home (e.g.
    build_denylist's `home / "instructions" / "project-names.txt"`) simply
    never resolve to a real file when no factory home is registered.
    """
    reg_path = resolve_wiki._default_registry_path()
    recorded = resolve_wiki.load_factory_home(reg_path)
    return Path(recorded) if recorded else Path("/nonexistent-factory-home")


def _cmd_validate_persona(path_str: str) -> int:
    path = Path(path_str)
    if not path.is_file():
        print(json.dumps({"ok": False, "errors": [f"persona file not found: {path}"],
                          "warnings": []}))
        return 2
    denylist = build_denylist(_resolve_factory_home_best_effort())
    result = validate_persona(path, denylist)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


def _cmd_upgrade_persona(path_str: str, description: str | None) -> int:
    path = Path(path_str)
    if not path.is_file():
        print(json.dumps({"changed": False, "added_description": False, "fenced": False,
                          "error": f"persona file not found: {path}"}))
        return 2
    result = upgrade_persona(path, description)
    print(json.dumps(result))
    return 0


def _cmd_assemble_context(wiki_root_str: str, persona_str: str) -> int:
    persona_file = Path(persona_str)
    if not persona_file.is_file():
        print(json.dumps({"error": f"persona file not found: {persona_file}"}))
        return 2
    wiki_root = Path(wiki_root_str)
    if not wiki_root.is_dir():
        print(json.dumps({"error": f"wiki root not found: {wiki_root}"}))
        return 2

    home = _resolve_factory_home_best_effort()
    result = assemble_context(home, wiki_root, persona_file)
    print(json.dumps(result))
    return 0


def _cmd_anchors_unchanged(original_str: str, edited_str: str) -> int:
    original = Path(original_str)
    edited = Path(edited_str)
    unreadable = [str(p) for p in (original, edited) if not p.is_file()]
    if unreadable:
        print(json.dumps({"ok": False,
                          "reason": f"unreadable path(s): {', '.join(unreadable)}"}))
        return 2
    try:
        result = anchors_unchanged(original, edited)
    except OSError as exc:
        # A path that exists but can't be read (e.g. permissions) is still an
        # unreadable path: exit 2, the same branch as a missing file — never
        # a traceback the /improve skill can't branch on.
        print(json.dumps({"ok": False, "reason": f"unreadable path(s): {exc}"}))
        return 2
    print(json.dumps(result))
    return 0 if result["ok"] else 1


def _cmd_search_candidates(query: str, division: str | None, source: str) -> int:
    reg_path = resolve_wiki._default_registry_path()
    recorded = resolve_wiki.load_factory_home(reg_path)
    home = Path(recorded) if recorded and resolve_wiki.is_factory_home(Path(recorded)) else None

    if source == "references" and home is None:
        print(json.dumps({
            "results": [],
            "error": ("factory home not registered or moved — the references "
                      "pool requires a resolvable factory home; run: "
                      "python3 resolve_wiki.py register-factory-home <path>"),
        }))
        return 2

    results = search_candidates(query, home, division, source)
    out: dict = {"results": results}
    if not results:
        out["suggestions"] = catalog_divisions()
    print(json.dumps(out))
    return 0


def _cmd_resolve_team(name: str) -> int:
    reg_path = resolve_wiki._default_registry_path()
    recorded = resolve_wiki.load_factory_home(reg_path)
    if not recorded or not resolve_wiki.is_factory_home(Path(recorded)):
        print(json.dumps({
            "status": "error",
            "hint": ("factory home not registered or moved — run: "
                     "python3 resolve_wiki.py register-factory-home <path>"),
        }))
        return 2

    try:
        result = resolve_team(Path(recorded), name)
    except TeamError as exc:
        print(json.dumps({"status": "error", "hint": str(exc)}))
        return 2

    print(json.dumps(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Team operations for AI Factory teams.")
    subparsers = parser.add_subparsers(dest="subcommand")

    resolve_p = subparsers.add_parser(
        "resolve-team", help="Resolve a team's members against the factory home.")
    resolve_p.add_argument("name", help="Team id (teams/<name>.yaml stem).")

    validate_p = subparsers.add_parser(
        "validate-persona", help="Validate a persona file's frontmatter and anchors.")
    validate_p.add_argument("path", help="Path to the persona .md file.")

    upgrade_p = subparsers.add_parser(
        "upgrade-persona",
        help="Idempotently upgrade a persona file (add description, fence anchors).")
    upgrade_p.add_argument("path", help="Path to the persona .md file.")
    upgrade_p.add_argument("--description", default=None,
                            help="Description text to insert if missing.")

    context_p = subparsers.add_parser(
        "assemble-context",
        help="Assemble budgeted per-persona context (orientation + prior positions).")
    context_p.add_argument("--wiki-root", required=True,
                            help="Path to the project root (contains a wiki/ directory).")
    context_p.add_argument("--persona", required=True, help="Path to the persona .md file.")

    anchors_p = subparsers.add_parser(
        "anchors-unchanged",
        help="Verify fenced Immutable Anchors are byte-identical between two persona files.")
    anchors_p.add_argument("original", help="Path to the original persona .md file.")
    anchors_p.add_argument("edited", help="Path to the edited persona .md file.")

    search_p = subparsers.add_parser(
        "search-candidates",
        help="Search starter/catalog/references pools for staffing candidates.")
    search_p.add_argument("--query", required=True, help="Search terms.")
    search_p.add_argument("--division", default=None,
                           help="Filter to a specific division (directory name).")
    search_p.add_argument("--source", default="all",
                           choices=["starter", "catalog", "references", "all"],
                           help="Which candidate pool(s) to search (default: all).")

    args = parser.parse_args(argv)

    if args.subcommand == "resolve-team":
        return _cmd_resolve_team(args.name)
    if args.subcommand == "validate-persona":
        return _cmd_validate_persona(args.path)
    if args.subcommand == "upgrade-persona":
        return _cmd_upgrade_persona(args.path, args.description)
    if args.subcommand == "assemble-context":
        return _cmd_assemble_context(args.wiki_root, args.persona)
    if args.subcommand == "anchors-unchanged":
        return _cmd_anchors_unchanged(args.original, args.edited)
    if args.subcommand == "search-candidates":
        return _cmd_search_candidates(args.query, args.division, args.source)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
