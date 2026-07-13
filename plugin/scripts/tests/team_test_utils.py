"""Fixture builders for team_ops tests. Stdlib only."""
import hashlib
import tempfile
from pathlib import Path

PERSONA_BODY = """---
name: {name}
role: {role}
version: v1.0
---

# {name} — {role}

## Identity
{name} is a test persona.

## Immutable Anchors (cannot change)

- Never fabricates data
- **Always attribute claims.** Every claim must carry a source tag per `CITATION_STANDARD.md`.

## Mutable Instructions (can evolve)

- Output format
"""

PERSONA_WITH_DESCRIPTION = """---
name: {name}
role: {role}
description: {description}
version: v1.0
---

# {name} — {role}

## Identity
{name} is a test persona.

## Immutable Anchors (cannot change)

- Never fabricates data
- **Always attribute claims.** Every claim must carry a source tag per `CITATION_STANDARD.md`.

## Mutable Instructions (can evolve)

- Output format
"""

PERSONA_MISSING_CITATION = """---
name: {name}
role: {role}
description: {description}
version: v1.0
---

# {name} — {role}

## Identity
{name} is a test persona with no citation requirement mentioned anywhere in this body.

## Immutable Anchors (cannot change)

- Never fabricates data

## Mutable Instructions (can evolve)

- Output format
"""

PERSONA_DENYLIST_HIT = """---
name: {name}
role: {role}
description: {description}
version: v1.0
---

# {name} — {role}

## Identity
{name} was staffed on the acme-launch project and knows it well.

## Immutable Anchors (cannot change)

- Never fabricates data
- **Always attribute claims.** Every claim must carry a source tag per `CITATION_STANDARD.md`.

## Mutable Instructions (can evolve)

- Output format
"""

PERSONA_FENCED = """---
name: {name}
role: {role}
version: v1.0
---

# {name} — {role}

## Identity
{name} is a test persona.

## Immutable Anchors (cannot change)

<!-- IMMUTABLE:BEGIN -->
- Never fabricates data
- **Always attribute claims.** Every claim must carry a source tag per `CITATION_STANDARD.md`.
<!-- IMMUTABLE:END -->

## Mutable Instructions (can evolve)

- Output format: {note}
"""

PERSONA_TWO_FENCES = """---
name: {name}
role: {role}
version: v1.0
---

# {name} — {role}

## Identity
{name} is a test persona.

## Immutable Anchors A (cannot change)

<!-- IMMUTABLE:BEGIN -->
- First anchor: never fabricates data
<!-- IMMUTABLE:END -->

## Immutable Anchors B (cannot change)

<!-- IMMUTABLE:BEGIN -->
- Second anchor: {second_anchor_text}
<!-- IMMUTABLE:END -->

## Mutable Instructions (can evolve)

- Output format
"""

TEAM_YAML = """id: demo-team
name: "Demo Team"
purpose: "Testing: parser handles colons — and dashes"
project: "~/nowhere"
members:
  - agent: ada
    role: Lead Tester
    model: claude-sonnet-5
    effort: deep
  - agent: bo
    role: Missing Member
    invocation: "on-demand — only when: needed"
framework: claude-code-agents
"""


# --- Layered-resolution fixtures (project-copy personas, --wiki-root) ------

PERSONA_PROJECT_COPY = """---
name: {name}
role: {role}
description: {description}
base-slug: {base_slug}
forked: {forked}
base-hash: {base_hash}
version: v1.0
---

# {name} — {role}

## Identity
{name} was staffed on the {project} project and knows it well.

## Immutable Anchors (cannot change)

<!-- IMMUTABLE:BEGIN -->
- Never fabricates data
- **Always attribute claims.** Every claim must carry a source tag per `CITATION_STANDARD.md`.
<!-- IMMUTABLE:END -->

## Mutable Instructions (can evolve)

- Output format
"""


def sha256_text(text: str) -> str:
    """sha256 hex digest of `text`'s UTF-8 bytes — mirrors how team_ops
    hashes a persona file's bytes (`path.read_bytes()`), for fixtures that
    build the expected hash from a string template rather than a file."""
    return hashlib.sha256(text.encode()).hexdigest()


def make_project_copy(wiki_root: Path, slug: str, text: str) -> Path:
    """Write a project-copy persona to `<wiki_root>/personas/<slug>.md`,
    creating the `personas/` directory if needed. Returns the written path."""
    personas_dir = wiki_root / "personas"
    personas_dir.mkdir(parents=True, exist_ok=True)
    path = personas_dir / f"{slug}.md"
    path.write_text(text)
    return path


def make_factory_home(tmp: Path, personas=("ada",), team_yaml=TEAM_YAML) -> Path:
    home = tmp / "factory-home"
    (home / "agents").mkdir(parents=True)
    (home / "teams").mkdir()
    for p in personas:
        (home / "agents" / f"{p}.md").write_text(
            PERSONA_BODY.format(name=p.title(), role="Lead Tester"))
    (home / "teams" / "demo-team.yaml").write_text(team_yaml)
    return home


# --- assemble_context fixtures -----------------------------------------------

WIKI_INDEX = """---
type: synthesis
status: active
last-updated: 2026-06-10
as-of: 2026-06-10
quarter: 2026-Q3
okr: []
confidence: high
sources: []
related: []
tags: [index]
---
# Index

Minimal fixture index.
"""

WIKI_OVERVIEW = """---
type: synthesis
status: active
last-updated: 2026-06-10
as-of: 2026-06-10
quarter: 2026-Q3
okr: []
confidence: high
sources: []
related: []
tags: []
summary: ""
---
# Overview

Minimal fixture overview.
"""

FOCUS_ENTITY_PAGE = """---
type: competitor
status: active
last-updated: {date}
quarter: 2026-Q3
okr: []
confidence: medium
author: []
sources: []
related: []
external-ref: ""
tags: [pricing]
summary: "Entity page {n} for focus-tag testing."
---
# Entity {n}

Body content for entity {n}.
"""

DECISION_WITH_POSITION = """---
type: decision
status: active
last-updated: {date}
quarter: 2026-Q3
okr: []
confidence: high
author: [{author}]
decided-by: "{author}"
superseded-by: ""
sources: []
related: []
external-ref: ""
tags: []
summary: "Decision {n} summary."
---
# {date} — Decision {n}

## Bottom line
Decision {n} bottom line.

## Positions
- **{author}**: position {n}

## Trade-offs accepted
"""

DECISION_NO_POSITION = """---
type: decision
status: active
last-updated: {date}
quarter: 2026-Q3
okr: []
confidence: medium
author: [{author}]
decided-by: ""
superseded-by: ""
sources: []
related: []
external-ref: ""
tags: []
summary: "{summary}"
---
# {date} — Decision without a recorded position

## Bottom line
No self-authored position was recorded for this decision.

## Positions
<!-- none recorded -->

## Trade-offs accepted
"""

SESSION_WITH_POSITION = """---
type: session
status: active
last-updated: {date}
quarter: 2026-Q3
okr: []
confidence: medium
author: [{author}]
sources: []
related: []
external-ref: ""
tags: [session]
summary: "Session summary."
---
# {date} — Session

## TL;DR
- did a thing

## Work units
- **{author}**: shipped the api scaffold

## Bookkeeping
"""


def make_wiki_with_positions(tmp: Path) -> Path:
    """Build a minimal wiki fixture for assemble_context tests.

    Returns the project root (the directory containing `wiki/`). Layout:
      - wiki/index.md, wiki/overview.md (type: synthesis)
      - 7 top-level entity pages (entity-1.md..entity-7.md) tagged `pricing`
        with staggered last-updated dates 2026-06-01..2026-06-07 (entity-7
        newest)
      - 12 decision pages (decision-01.md..decision-12.md) authored [Ada],
        each with a `## Positions` line `- **Ada**: position N`, dated
        2026-05-01..2026-05-12 (decision-12 newest of these)
      - decision-13.md: authored [Ada], dated 2026-05-13, WITHOUT a
        `## Positions` line (fallback-to-summary case)
      - session-01.md: type session, authored [ada] (lowercase — case-
        insensitive author-match case), dated 2026-05-14 (newest of the
        whole author-Ada pool), with a `## Work units` position line
    """
    project = tmp / "wiki-project"
    wiki_dir = project / "wiki"
    wiki_dir.mkdir(parents=True)

    (wiki_dir / "index.md").write_text(WIKI_INDEX)
    (wiki_dir / "overview.md").write_text(WIKI_OVERVIEW)

    for n in range(1, 8):
        date = f"2026-06-{n:02d}"
        (wiki_dir / f"entity-{n}.md").write_text(
            FOCUS_ENTITY_PAGE.format(n=n, date=date))

    for n in range(1, 13):
        date = f"2026-05-{n:02d}"
        (wiki_dir / f"decision-{n:02d}.md").write_text(
            DECISION_WITH_POSITION.format(n=n, date=date, author="Ada"))

    (wiki_dir / "decision-13.md").write_text(
        DECISION_NO_POSITION.format(
            date="2026-05-13", author="Ada",
            summary="Pricing bands finalized without a recorded position."))

    (wiki_dir / "session-01.md").write_text(
        SESSION_WITH_POSITION.format(date="2026-05-14", author="ada"))

    return project
