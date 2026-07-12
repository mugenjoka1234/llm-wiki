"""Integration tests for wiki-forget skill logic via resolve_wiki.py --compact.

The forget skill uses --compact to deduplicate registry entries and prune
stale paths. These tests verify the compaction behavior in isolation.
"""
import os
import subprocess
from pathlib import Path
from conftest import RESOLVE, _scaffold_wiki


def test_compact_removes_duplicates(tmp_path, tmp_registry):
    """--compact should deduplicate registry entries, keeping latest per path."""
    wiki_path = tmp_path / "test-wiki"
    wiki_path.mkdir()
    _scaffold_wiki(wiki_path, "test", "Test")

    registry = tmp_registry / "registry.txt"
    # Two entries for the same path — later date should win
    registry.write_text(
        f"{wiki_path}|test|2026-01-01|2026-01-01\n"
        f"{wiki_path}|test|2026-01-01|2026-01-02\n"
    )

    env = os.environ.copy()
    env["CLAUDE_PLUGIN_DATA"] = str(tmp_registry)
    result = subprocess.run(
        ["python3", str(RESOLVE), "--compact"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, f"--compact failed.\nstderr: {result.stderr}"

    lines = [l for l in registry.read_text().splitlines() if l.strip()]
    assert len(lines) == 1, f"Expected 1 line after compaction, got {len(lines)}: {lines}"
    assert "2026-01-02" in lines[0], "Expected later date to survive"


def test_compact_preserves_multiple_distinct_paths(tmp_path, tmp_registry):
    """--compact should keep one entry per distinct path."""
    wiki_a = tmp_path / "wiki-a"
    wiki_b = tmp_path / "wiki-b"
    wiki_a.mkdir()
    wiki_b.mkdir()
    _scaffold_wiki(wiki_a, "a", "Wiki A")
    _scaffold_wiki(wiki_b, "b", "Wiki B")

    registry = tmp_registry / "registry.txt"
    registry.write_text(
        f"{wiki_a}|a|2026-01-01|2026-01-01\n"
        f"{wiki_b}|b|2026-01-01|2026-01-01\n"
        f"{wiki_a}|a|2026-01-01|2026-05-01\n"  # duplicate of wiki_a, later date
    )

    env = os.environ.copy()
    env["CLAUDE_PLUGIN_DATA"] = str(tmp_registry)
    result = subprocess.run(
        ["python3", str(RESOLVE), "--compact"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, f"--compact failed.\nstderr: {result.stderr}"

    lines = [l for l in registry.read_text().splitlines() if l.strip()]
    assert len(lines) == 2, f"Expected 2 lines after compaction, got {len(lines)}: {lines}"

    paths_in_registry = [l.split("|")[0] for l in lines]
    assert str(wiki_a) in paths_in_registry
    assert str(wiki_b) in paths_in_registry


def test_compact_empty_registry_leaves_empty_file(tmp_path, tmp_registry):
    """--compact on an empty registry file should leave it empty (not error)."""
    registry = tmp_registry / "registry.txt"
    registry.write_text("")

    env = os.environ.copy()
    env["CLAUDE_PLUGIN_DATA"] = str(tmp_registry)
    result = subprocess.run(
        ["python3", str(RESOLVE), "--compact"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, f"--compact on empty registry failed.\nstderr: {result.stderr}"
    assert registry.read_text() == ""
