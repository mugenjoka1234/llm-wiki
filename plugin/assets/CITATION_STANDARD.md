# Citation Standard

The canonical claim-tag taxonomy for llm-wiki content and factory personas.
`lint.py`'s numeric-claim gate and `team_ops.py`'s persona validator both
enforce this taxonomy mechanically; this file documents the semantics.

## The tags

- **`[internal::file]`** — traces to a specific file in this project (a doc,
  a spec, a data export). Cite the file, not just the tag.
- **`[internal::data]`** — traces to internal measured data (an analytics
  query, a dashboard, a client-provided number). State whether the number is
  a **target** or a **measured baseline** — conflating them is a common
  failure mode.
- **`[external::claude-knowledge]`** — from the model's training knowledge,
  not a fetched source. Use sparingly; prefer a real citation when available.
- **`[external::web-search]`** — from a web search/fetch performed this
  session. A bare URL also satisfies this.
- **`[hypothesis]`** / **`[hypothesis: ...]`** — plausible but unverified.
  Carries an obligation, not just a label — see below.
- **`[verified: YYYY-MM-DD]`** — a hypothesis checked and confirmed true as
  of that date. Supersedes `[hypothesis]` on the same claim.
- **`[REFUTED]`** / **`[REFUTED: ...]`** — a hypothesis checked and found
  false. Keep the claim tagged rather than deleting it — refuted history is
  useful.
- **`%%[no-claim]%%`** — explicit suppression marker (Obsidian comment
  syntax: invisible in reading view, greppable in source). Use when a number
  looks like a claim but isn't (an example, a placeholder, a UI label).

A `[[wikilink]]` or a bare `https://` URL also counts as coverage — both are
citations in their own right.

## Unattributed claims are invalid

Every statistic, number, behavioral assertion, or external fact must carry
one of the tags above (or a wikilink/URL). A claim with none of these is an
invalid output, not a style nit — this is what the numeric-claim gate below
checks mechanically for wiki pages; the same rule governs persona output
that never touches the wiki, where the author is the sole enforcement.

## Hypothesis must reach open items

Every `[hypothesis]`-tagged claim must have a matching entry in the relevant
`wiki/questions/` page (or, in a factory session, the session's
`open_items`) stating concrete validation criteria — what would need to be
true, or what test would need to run, to move it to
`[verified: YYYY-MM-DD]` or `[REFUTED]`. A `[hypothesis]` with no matching
open item is a claim nobody is tracking to resolution.

## Paragraph coverage (numeric-claim gate)

`lint.py` scans each prose paragraph for a numeric claim — currency
(`$1,200`), percentages (`14%`), magnitudes (`3.2M`, `2 billion`),
multipliers (`4.5x`), or a standalone integer of 3+ digits. Bare 1-2 digit
integers ("3 options") are not claims. Dates, quarters, version strings, and
bare 4-digit years are allow-listed.

A paragraph is **covered** if it contains any tag above, a wikilink, or a
URL anywhere in the paragraph — coverage is paragraph-scoped, not
sentence-scoped: one citation covers every claim in that paragraph, but
does not carry across a paragraph break. An uncovered paragraph with a
numeric claim is a SCHEMA ERROR. `synthesis` and `question` page types are
exempt (they summarize claims made elsewhere, not new ones).
