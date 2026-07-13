"""Tests for team_ops.py search_candidates and the search-candidates CLI.

Function-level tests patch `team_ops._catalog_root` / `team_ops._starter_root`
to point at temp fixture directories — those two functions are the sole
lookup points for the plugin-relative pools, so patching them isolates every
fixture test from the real (large, third-party) vendored catalog shipped in
this repo. The real catalog is still exercised, deliberately unpatched, in
TestRealCatalog below (read-only).

References-pool tests pass `home` directly (a real parameter of
search_candidates), no patching needed.

CLI-level exit-code tests drive the script via subprocess, mirroring
test_team_ops_integration.py's CLAUDE_PLUGIN_DATA isolation pattern.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import team_ops

SCRIPT = Path(__file__).parent.parent / "team_ops.py"

CATALOG_AGENT = """---
name: {name}
description: {description}
color: teal
---

# {name}

Body.
"""

STARTER_AGENT = """---
name: {name}
role: {role}
description: "{description}"
domain: [{domain}]
version: v1.0
---

# {name} — {role}

Body.
"""

REFERENCE_AGENT = """---
name: {name}
description: {description}
---

# {name}

Body.
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _env_with_registry(plugin_data_dir: Path) -> dict:
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_DATA"] = str(plugin_data_dir)
    return env


def _write_factory_home_registry(plugin_data_dir: Path, home: Path) -> Path:
    reg = plugin_data_dir / "registry.txt"
    reg.write_text(f"!factory_home|{home}\n")
    return reg


def _run(*args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )


class TestRanking(unittest.TestCase):
    """Ranking respects term overlap: more matching terms scores higher."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.catalog_root = Path(self.tmp.name) / "agency-agents"
        _write(self.catalog_root / "gis" / "gis-analyst.md",
               CATALOG_AGENT.format(
                   name="GIS Analyst",
                   description="Creates maps and manages spatial layers."))
        _write(self.catalog_root / "gis" / "gis-cartographer.md",
               CATALOG_AGENT.format(
                   name="Cartographer",
                   description="Designs maps for print and web."))
        _write(self.catalog_root / "product" / "product-manager.md",
               CATALOG_AGENT.format(
                   name="Product Manager",
                   description="Owns roadmap and prioritization."))
        self.patcher = mock.patch.object(
            team_ops, "_catalog_root", return_value=self.catalog_root)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_more_term_overlap_ranks_higher(self):
        results = team_ops.search_candidates(
            "maps spatial", home=None, division=None, source="catalog")
        names = [r["name"] for r in results]
        # "GIS Analyst" hits both "maps" and "spatial" (score 2);
        # "Cartographer" hits only "maps" (score 1); "Product Manager" 0 (excluded).
        self.assertEqual(names, ["GIS Analyst", "Cartographer"])
        self.assertEqual(results[0]["score"], 2)
        self.assertEqual(results[1]["score"], 1)

    def test_zero_overlap_excluded_from_results(self):
        results = team_ops.search_candidates(
            "maps spatial", home=None, division=None, source="catalog")
        self.assertNotIn("Product Manager", [r["name"] for r in results])

    def test_division_derived_from_first_directory_component(self):
        results = team_ops.search_candidates(
            "roadmap", home=None, division=None, source="catalog")
        self.assertEqual(results[0]["division"], "product")


class TestTieBreak(unittest.TestCase):
    """Exact tie-break chain: same score -> starter > references > catalog,
    then name."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)

        self.catalog_root = root / "agency-agents"
        self.starter_root = root / "starter-roster"
        self.home = root / "factory-home"

        # All three candidates below hit exactly one term ("wren") -> tied score.
        _write(self.catalog_root / "misc" / "wren-catalog.md",
               CATALOG_AGENT.format(name="Wren Catalog", description="wren candidate"))
        _write(self.starter_root / "wren-starter.md",
               STARTER_AGENT.format(name="Wren Starter", role="Lead",
                                     description="wren candidate", domain=""))
        _write(self.home / "references" / "wren-ref.md",
               REFERENCE_AGENT.format(name="Wren Reference", description="wren candidate"))

        self.patchers = [
            mock.patch.object(team_ops, "_catalog_root", return_value=self.catalog_root),
            mock.patch.object(team_ops, "_starter_root", return_value=self.starter_root),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_three_way_tie_orders_starter_then_references_then_catalog(self):
        results = team_ops.search_candidates(
            "wren", home=self.home, division=None, source="all")
        self.assertEqual(len(results), 3)
        self.assertEqual([r["score"] for r in results], [1, 1, 1])
        self.assertEqual(
            [r["source"] for r in results],
            ["starter", "references", "catalog"])

    def test_name_is_final_tiebreak_within_same_source(self):
        # Two same-source, same-score candidates: alphabetical by name wins.
        _write(self.catalog_root / "misc" / "aaa-catalog.md",
               CATALOG_AGENT.format(name="AAA Catalog", description="wren candidate"))
        results = team_ops.search_candidates(
            "wren", home=None, division=None, source="catalog")
        catalog_names = [r["name"] for r in results]
        self.assertEqual(catalog_names, sorted(catalog_names))
        self.assertEqual(catalog_names[0], "AAA Catalog")


class TestDivisionFilter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.catalog_root = Path(self.tmp.name) / "agency-agents"
        _write(self.catalog_root / "gis" / "gis-analyst.md",
               CATALOG_AGENT.format(name="GIS Analyst", description="maps and layers"))
        _write(self.catalog_root / "product" / "product-manager.md",
               CATALOG_AGENT.format(name="Product Manager", description="maps out roadmaps"))
        self.patcher = mock.patch.object(
            team_ops, "_catalog_root", return_value=self.catalog_root)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_division_filter_restricts_results(self):
        results = team_ops.search_candidates(
            "maps", home=None, division="gis", source="catalog")
        self.assertEqual([r["name"] for r in results], ["GIS Analyst"])

    def test_division_filter_case_insensitive(self):
        results = team_ops.search_candidates(
            "maps", home=None, division="GIS", source="catalog")
        self.assertEqual([r["name"] for r in results], ["GIS Analyst"])


class TestSourceFilter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.catalog_root = root / "agency-agents"
        self.starter_root = root / "starter-roster"
        _write(self.catalog_root / "misc" / "echo-catalog.md",
               CATALOG_AGENT.format(name="Echo Catalog", description="echo term"))
        _write(self.starter_root / "echo-starter.md",
               STARTER_AGENT.format(name="Echo Starter", role="Lead",
                                     description="echo term", domain=""))
        self.patchers = [
            mock.patch.object(team_ops, "_catalog_root", return_value=self.catalog_root),
            mock.patch.object(team_ops, "_starter_root", return_value=self.starter_root),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        self.tmp.cleanup()

    def test_source_all_finds_both(self):
        results = team_ops.search_candidates(
            "echo", home=None, division=None, source="all")
        self.assertEqual(sorted(r["source"] for r in results), ["catalog", "starter"])

    def test_source_starter_only(self):
        results = team_ops.search_candidates(
            "echo", home=None, division=None, source="starter")
        self.assertEqual([r["source"] for r in results], ["starter"])

    def test_source_catalog_only(self):
        results = team_ops.search_candidates(
            "echo", home=None, division=None, source="catalog")
        self.assertEqual([r["source"] for r in results], ["catalog"])


class TestStarterAbsent(unittest.TestCase):
    """Starter roster directory absent -> empty candidates, never an error
    (Plan 3 hasn't authored plugin/assets/starter-roster/ yet)."""

    def test_missing_starter_dir_returns_empty_not_error(self):
        with tempfile.TemporaryDirectory() as td:
            nonexistent = Path(td) / "no-such-starter-roster"
            with mock.patch.object(team_ops, "_starter_root", return_value=nonexistent):
                results = team_ops.search_candidates(
                    "anything", home=None, division=None, source="starter")
        self.assertEqual(results, [])


class TestReferencesPool(unittest.TestCase):
    def test_references_requires_home_object_but_function_never_raises(self):
        results = team_ops.search_candidates(
            "anything", home=None, division=None, source="references")
        self.assertEqual(results, [])

    def test_references_reads_recursive_frontmatter_files(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "factory-home"
            _write(home / "references" / "vendors" / "acme.md",
                   REFERENCE_AGENT.format(name="Acme Advisor", description="vendor advisor"))
            # Non-frontmatter file under references/ must be skipped, not error.
            _write(home / "references" / "notes.md", "just some notes, no frontmatter\n")

            results = team_ops.search_candidates(
                "vendor", home=home, division=None, source="references")
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["name"], "Acme Advisor")
            self.assertEqual(results[0]["source"], "references")


class TestZeroMatchSuggestions(unittest.TestCase):
    """Suggestions surface catalog division names, independent of the
    filters that produced the zero-match result."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.catalog_root = Path(self.tmp.name) / "agency-agents"
        _write(self.catalog_root / "gis" / "gis-analyst.md",
               CATALOG_AGENT.format(name="GIS Analyst", description="maps"))
        _write(self.catalog_root / "finance" / "bookkeeper.md",
               CATALOG_AGENT.format(name="Bookkeeper", description="ledgers"))
        self.patcher = mock.patch.object(
            team_ops, "_catalog_root", return_value=self.catalog_root)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_catalog_divisions_helper(self):
        self.assertEqual(team_ops.catalog_divisions(), ["finance", "gis"])

    def test_suggestions_unaffected_by_division_filter(self):
        # A division filter that matches nothing still surfaces ALL catalog
        # divisions as suggestions (not just the filtered-out one) — the
        # function itself only returns the ranked list; catalog_divisions()
        # is what the CLI wrapper calls to build "suggestions".
        results = team_ops.search_candidates(
            "maps", home=None, division="nonexistent-division", source="catalog")
        self.assertEqual(results, [])
        self.assertEqual(team_ops.catalog_divisions(), ["finance", "gis"])


class TestScoringSemantics(unittest.TestCase):
    """Term dedupe, word-boundary matching, and the short-term floor."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.catalog_root = Path(self.tmp.name) / "agency-agents"
        _write(self.catalog_root / "misc" / "manager.md",
               CATALOG_AGENT.format(
                   name="Ops Manager",
                   description="Keeps the studio running."))
        self.patcher = mock.patch.object(
            team_ops, "_catalog_root", return_value=self.catalog_root)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_duplicate_terms_score_once(self):
        once = team_ops.search_candidates(
            "manager", home=None, division=None, source="catalog")
        thrice = team_ops.search_candidates(
            "manager manager manager", home=None, division=None, source="catalog")
        self.assertEqual(len(once), 1)
        self.assertEqual(len(thrice), 1)
        self.assertEqual(once[0]["score"], thrice[0]["score"])

    def test_word_boundary_no_prefix_match(self):
        # "manage" must NOT match "manager" — whole-word semantics, not
        # prefix/substring. (Deliberate trade-off, pinned here: no stemming;
        # a user searching "manage" will not surface "manager" roles.)
        results = team_ops.search_candidates(
            "manage", home=None, division=None, source="catalog")
        self.assertEqual(results, [])

    def test_word_boundary_no_infix_match(self):
        # "age" sits inside "Manager" but is not a word in the haystack.
        results = team_ops.search_candidates(
            "age", home=None, division=None, source="catalog")
        self.assertEqual(results, [])

    def test_terms_shorter_than_three_chars_dropped(self):
        # "Ops" is a word in the name, but a 2-char query term never scores
        # (stopword floor).
        results = team_ops.search_candidates(
            "op", home=None, division=None, source="catalog")
        self.assertEqual(results, [])

    def test_three_char_term_still_scores(self):
        results = team_ops.search_candidates(
            "ops", home=None, division=None, source="catalog")
        self.assertEqual([r["name"] for r in results], ["Ops Manager"])

    def test_the_matches_whole_word_only(self):
        # "the" (3 chars, survives the floor) matches only where it appears
        # as a whole word — "Keeps the studio running." hits; a description
        # containing only "theater" does not.
        _write(self.catalog_root / "misc" / "stagehand.md",
               CATALOG_AGENT.format(
                   name="Stagehand",
                   description="Runs theater productions."))
        results = team_ops.search_candidates(
            "the", home=None, division=None, source="catalog")
        self.assertEqual([r["name"] for r in results], ["Ops Manager"])


class TestFoldedScalarDescription(unittest.TestCase):
    """A catalog file using a YAML folded block scalar (`description: >-`)
    must still yield its full description text — searchable and free of the
    `>-` indicator. _frontmatter_description alone returns the indicator
    plus raw continuation lines for block scalars (verified empirically);
    the unfold fallback on top of it is what this class exercises."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.catalog_root = Path(self.tmp.name) / "agency-agents"
        _write(self.catalog_root / "misc" / "folded.md",
               "---\n"
               "name: Folded Desc\n"
               "description: >-\n"
               "  Senior orchestration specialist for\n"
               "  multi-agent pipelines.\n"
               "color: blue\n"
               "---\n"
               "\n"
               "# Folded Desc\n")
        self.patcher = mock.patch.object(
            team_ops, "_catalog_root", return_value=self.catalog_root)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_folded_description_unfolded_and_fully_searchable(self):
        # One term from each folded line: both must hit (continuation text
        # is in the scored haystack, not just the first line).
        results = team_ops.search_candidates(
            "orchestration pipelines", home=None, division=None, source="catalog")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["score"], 2)
        self.assertEqual(
            results[0]["description"],
            "Senior orchestration specialist for multi-agent pipelines.")


class TestCliSearchCandidates(unittest.TestCase):
    """CLI-level behavior: wrapper object shape, exit codes."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_zero_match_wrapper_has_suggestions_from_real_catalog(self):
        env = _env_with_registry(self.root)
        result = _run("search-candidates", "--query", "zzzznonexistentqueryxyz",
                       "--source", "catalog", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["results"], [])
        self.assertIn("suggestions", payload)
        self.assertGreater(len(payload["suggestions"]), 0)

    def test_nonzero_match_wrapper_has_no_suggestions_key(self):
        env = _env_with_registry(self.root)
        result = _run("search-candidates", "--query", "product manager",
                       "--source", "catalog", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertGreater(len(payload["results"]), 0)
        self.assertNotIn("suggestions", payload)

    def test_references_without_resolvable_home_exits_2(self):
        # No registry.txt written under this isolated CLAUDE_PLUGIN_DATA —
        # load_factory_home() returns None.
        env = _env_with_registry(self.root)
        result = _run("search-candidates", "--query", "anything",
                       "--source", "references", env=env)
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["results"], [])

    def test_references_with_resolvable_home_but_no_dir_exits_0_empty(self):
        home = self.root / "factory-home"
        (home / "agents").mkdir(parents=True)
        (home / "teams").mkdir()
        _write_factory_home_registry(self.root, home)
        env = _env_with_registry(self.root)

        result = _run("search-candidates", "--query", "anything",
                       "--source", "references", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["results"], [])
        self.assertIn("suggestions", payload)

    def test_all_source_with_no_home_degrades_gracefully_exit_0(self):
        # source=all (not references specifically): unresolvable home must
        # NOT be an error, per the brief's "exit 2 only for unusable
        # --source references" rule.
        env = _env_with_registry(self.root)
        result = _run("search-candidates", "--query", "product manager", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertGreater(len(payload["results"]), 0)


class TestRealCatalog(unittest.TestCase):
    """Read-only test against the REAL vendored catalog that ships with the
    repo (plugin/assets/agency-agents/), not a fixture. Proves the
    _frontmatter_description fallback and division derivation work against
    the actual vendored files."""

    def test_common_query_returns_at_least_one_real_result(self):
        results = team_ops.search_candidates(
            "product manager", home=None, division=None, source="catalog")
        self.assertGreater(len(results), 0)
        names = [r["name"] for r in results]
        self.assertIn("Product Manager", names)
        top = results[0]
        self.assertEqual(top["name"], "Product Manager")
        self.assertEqual(top["division"], "product")
        self.assertTrue(top["description"])
        self.assertEqual(top["score"], 2)  # "product" and "manager" both hit

    def test_the_hits_are_whole_word_not_substring(self):
        # Regression for substring inflation: unanchored containment let
        # "the" match dozens of catalog files through "theater"/"theory"/
        # "aesthetic" etc. Every hit must now genuinely contain "the" as a
        # standalone word in its scored haystack (name + description; the
        # catalog carries no domain: tags), and the word-boundary count
        # must be strictly below the old substring count.
        results = team_ops.search_candidates(
            "the", home=None, division=None, source="catalog")
        word_re = re.compile(r"\bthe\b")
        for r in results:
            haystack = f'{r["name"]} {r["description"]}'.lower()
            self.assertRegex(haystack, word_re, r["path"])

        substring_count = 0
        for p in Path(team_ops._catalog_root()).rglob("*.md"):
            fm = team_ops._frontmatter(p)
            if not fm.get("name"):
                continue
            desc = team_ops._frontmatter_description(p.read_text()) or ""
            if "the" in f'{fm["name"]} {desc}'.lower():
                substring_count += 1
        self.assertLess(len(results), substring_count)

    def test_two_char_query_empty_with_suggestions_via_cli(self):
        # Both query terms fall under the 3-char floor -> zero matches ->
        # the CLI wrapper adds division-derived suggestions.
        with tempfile.TemporaryDirectory() as td:
            env = _env_with_registry(Path(td))
            result = _run("search-candidates", "--query", "ai ml",
                           "--source", "catalog", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["results"], [])
        self.assertGreater(len(payload["suggestions"]), 0)


if __name__ == "__main__":
    unittest.main()
