"""Integration tests for resolve_wiki.py — registry, link, resolve-uri.

resolve_wiki.py reads its registry from the path given by --registry flag,
or falls back to $CLAUDE_PLUGIN_DATA/registry.txt when no flag is passed.
The tmp_registry fixture sets CLAUDE_PLUGIN_DATA so all subprocess calls
pick up the isolated registry automatically.
"""
import json
import os
import subprocess
import pytest
from pathlib import Path
from conftest import run_resolve, RESOLVE, _scaffold_wiki


def test_resolve_from_cwd(wiki, tmp_registry):
    """When cwd is a wiki root, source should be 'cwd'."""
    code, out = run_resolve(wiki, "--cwd", str(wiki))
    assert code == 0, f"resolve_wiki.py failed. output: {out}"
    data = json.loads(out)
    assert Path(data["wiki_path"]).resolve() == wiki.resolve()
    assert data["source"] == "cwd"


def test_registry_unique_resolution(wiki, tmp_registry):
    """From a non-wiki cwd with one registry entry, source should be 'registry-unique'."""
    other_dir = wiki.parent / "other"
    other_dir.mkdir()
    code, out = run_resolve(wiki, "--cwd", str(other_dir))
    assert code == 0
    data = json.loads(out)
    assert data["source"] == "registry-unique"
    assert Path(data["wiki_path"]).resolve() == wiki.resolve()


def test_link_sets_parent_field(tmp_path, tmp_registry):
    """link subcommand should write the 5th pipe-delimited field on the child entry."""
    parent = tmp_path / "parent-wiki"
    child = tmp_path / "child-wiki"
    parent.mkdir()
    child.mkdir()
    _scaffold_wiki(parent, "parent", "Parent wiki")
    _scaffold_wiki(child, "child", "Child wiki")

    registry = tmp_registry / "registry.txt"
    registry.write_text(
        f"{parent}|parent|2026-01-01|2026-01-01\n"
        f"{child}|child|2026-01-01|2026-01-01\n"
    )

    env = os.environ.copy()
    env["CLAUDE_PLUGIN_DATA"] = str(tmp_registry)
    result = subprocess.run(
        ["python3", str(RESOLVE), "link", str(child), str(parent)],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, f"link failed.\nstderr: {result.stderr}"

    # 5th field on the child entry should be the resolved parent path
    lines = registry.read_text().splitlines()
    child_line = next(l for l in lines if str(child) in l)
    fields = child_line.split("|")
    assert len(fields) == 5, f"Expected 5 fields, got {len(fields)}: {child_line}"
    assert fields[4] == str(parent.resolve()), (
        f"Expected 5th field to be parent path '{parent.resolve()}', "
        f"got '{fields[4]}'"
    )


def test_resolve_uri(tmp_path, tmp_registry):
    """resolve-uri wiki://domain/slug should print the absolute file path and exit 0."""
    research = tmp_path / "research"
    research.mkdir()
    _scaffold_wiki(research, "research", "Research wiki")
    (research / "wiki/lightspeed-competitor.md").write_text("# Lightspeed\n")

    registry = tmp_registry / "registry.txt"
    registry.write_text(f"{research}|research|2026-01-01|2026-01-01\n")

    env = os.environ.copy()
    env["CLAUDE_PLUGIN_DATA"] = str(tmp_registry)
    result = subprocess.run(
        ["python3", str(RESOLVE), "resolve-uri", "wiki://research/lightspeed-competitor"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, f"resolve-uri failed.\nstderr: {result.stderr}"
    assert "lightspeed-competitor.md" in result.stdout


def test_resolve_uri_unknown_domain_fails(tmp_path, tmp_registry):
    """resolve-uri with an unknown domain should exit non-zero."""
    registry = tmp_registry / "registry.txt"
    registry.write_text("")

    env = os.environ.copy()
    env["CLAUDE_PLUGIN_DATA"] = str(tmp_registry)
    result = subprocess.run(
        ["python3", str(RESOLVE), "resolve-uri", "wiki://unknown/some-page"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0, "Expected non-zero exit for unknown domain"
