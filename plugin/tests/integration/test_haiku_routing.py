"""Integration tests for Haiku fast-path token threshold logic.

The analyze skill routes to haiku-3-5 for small files (< 5K tokens)
and to sonnet for larger ones. Token count is approximated as
len(content) // 4 (4 chars per token, GPT-style rough estimate).

These tests are pure-Python — no subprocess or wiki fixture needed.
"""

# Token threshold from analyze/SKILL.md
HAIKU_TOKEN_THRESHOLD = 5000
CHARS_PER_TOKEN = 4


def _route(content: str) -> str:
    """Mirror the routing logic from analyze/SKILL.md."""
    tokens = len(content) // CHARS_PER_TOKEN
    return "haiku" if tokens < HAIKU_TOKEN_THRESHOLD else "sonnet"


def test_empty_file_routes_to_haiku():
    """An empty file (0 tokens) should route to haiku."""
    assert _route("") == "haiku"


def test_small_file_under_threshold_routes_to_haiku():
    """A file just under the 5K token threshold should route to haiku."""
    # 19_999 chars = 4_999 tokens — just under the 5K limit
    content = "x" * (HAIKU_TOKEN_THRESHOLD * CHARS_PER_TOKEN - 1)
    tokens = len(content) // CHARS_PER_TOKEN
    assert tokens < HAIKU_TOKEN_THRESHOLD
    assert _route(content) == "haiku"


def test_file_at_threshold_routes_to_sonnet():
    """A file exactly at the 5K token threshold should route to sonnet."""
    content = "x" * (HAIKU_TOKEN_THRESHOLD * CHARS_PER_TOKEN)
    tokens = len(content) // CHARS_PER_TOKEN
    assert tokens == HAIKU_TOKEN_THRESHOLD
    assert _route(content) == "sonnet"


def test_large_file_over_threshold_routes_to_sonnet():
    """A file well above the 5K token threshold should route to sonnet."""
    # 20_001 chars = 5_000 tokens (integer division: 20_001 // 4 = 5_000)
    content = "x" * (HAIKU_TOKEN_THRESHOLD * CHARS_PER_TOKEN + 1)
    tokens = len(content) // CHARS_PER_TOKEN
    assert tokens >= HAIKU_TOKEN_THRESHOLD
    assert _route(content) == "sonnet"


def test_realistic_small_document_routes_to_haiku():
    """A realistic 1-page document (~500 words, ~3K chars) should route to haiku."""
    content = "This is a sentence with roughly ten words in it. " * 60  # ~3000 chars
    tokens = len(content) // CHARS_PER_TOKEN
    assert tokens < HAIKU_TOKEN_THRESHOLD
    assert _route(content) == "haiku"


def test_realistic_large_document_routes_to_sonnet():
    """A large research output (~25K chars) should route to sonnet."""
    content = "Research finding: the quick brown fox jumps over the lazy dog. " * 400  # ~25K chars
    tokens = len(content) // CHARS_PER_TOKEN
    assert tokens >= HAIKU_TOKEN_THRESHOLD
    assert _route(content) == "sonnet"
