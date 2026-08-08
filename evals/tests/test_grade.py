import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import grade

class TestLinks(unittest.TestCase):
    def test_strip_alias_anchor(self):
        self.assertEqual(grade.strip_link("[[a-page|nice name]]"), "a-page")
        self.assertEqual(grade.strip_link("[[a-page#section]]"), "a-page")
        self.assertEqual(grade.strip_link("[[a-page]]"), "a-page")
        self.assertEqual(grade.strip_link("a-page"), "a-page")

    def test_footer_parse(self):
        t = "prose [[x]] more\nSOURCES (most relevant first): [[a]], [[b|B]], [[c#s]]\n"
        self.assertEqual(grade.parse_sources_footer(t), ["a", "b", "c"])
        self.assertEqual(grade.parse_sources_footer("no footer here"), [])

    def test_footer_ignores_prose_words(self):
        t = "SOURCES (most relevant first): [[a]], and also [[b]] plus raw/snapshots/x.md"
        self.assertEqual(grade.parse_sources_footer(t), ["a", "b", "raw/snapshots/x.md"])

    def test_resolver_file_pages_entities(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "wiki"))
            graph = {"pages": {"graph-page": {"path": "wiki/graph-page.md"}},
                     "entities": {"embedded-entity": [{"path": "wiki/host.md"}]}}
            sb = os.path.join(d, "sb")
            os.makedirs(os.path.join(sb, "wiki"))
            # a file present only in the FIXTURE does not resolve — files are
            # checked in the sandbox (what the agent cited against)
            open(os.path.join(d, "wiki", "fixture-only.md"), "w").write("x")
            self.assertFalse(grade.resolve_link("fixture-only", d, sb, graph))
            open(os.path.join(sb, "wiki", "real-page.md"), "w").write("x")
            self.assertTrue(grade.resolve_link("real-page", d, sb, graph))
            self.assertTrue(grade.resolve_link("graph-page", d, sb, graph))
            self.assertTrue(grade.resolve_link("embedded-entity", d, sb, graph))
            self.assertFalse(grade.resolve_link("fabricated", d, sb, graph))

class TestMetrics(unittest.TestCase):
    def test_short_footer_denominator(self):
        m = grade.precision_recall_mrr(["a", "b", "c"], {"a", "b", "z"}, ["z"])
        self.assertAlmostEqual(m["p_at_5"], 2 / 3)      # min(5, 3) denominator
        self.assertAlmostEqual(m["r_at_5"], 2 / 3)      # 2 of 3 relevant found
        self.assertEqual(m["mrr"], 0.0)                  # primary 'z' never cited

    def test_mrr_first_primary(self):
        m = grade.precision_recall_mrr(["x", "p1", "p2"], {"p1"}, ["p1", "p2"])
        self.assertAlmostEqual(m["mrr"], 1 / 2)          # first primary at rank 2

    def test_empty_footer(self):
        m = grade.precision_recall_mrr([], {"a"}, ["a"])
        self.assertEqual((m["p_at_5"], m["r_at_5"], m["mrr"]), (0.0, 0.0, 0.0))

class TestStreamJson(unittest.TestCase):
    def test_parse(self):
        lines = [
            {"type": "system", "subtype": "init"},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": "/sb/wiki/a.md"}}]}},
            {"type": "result", "subtype": "success", "result": "answer text",
             "usage": {"input_tokens": 10, "output_tokens": 20,
                       "cache_creation_input_tokens": 100,
                       "cache_read_input_tokens": 1000},
             "total_cost_usd": 0.05, "num_turns": 3},
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write("\n".join(json.dumps(l) for l in lines)); p = f.name
        out = grade.parse_stream_json(p); os.unlink(p)
        self.assertEqual(out["result_text"], "answer text")
        self.assertEqual(out["reads"], ["/sb/wiki/a.md"])
        self.assertAlmostEqual(out["total_cost_usd"], 0.05)
        self.assertAlmostEqual(grade.weighted_tokens(out["usage"]),
                               10 + 1.25 * 100 + 0.1 * 1000 + 5 * 20)

class TestIngestChecks(unittest.TestCase):
    def test_url_extraction_and_lint_delta(self):
        s = "see https://eval-fixture.invalid/a. and (https://x.test/b),"
        self.assertEqual(grade.extract_urls(s),
                         {"https://eval-fixture.invalid/a", "https://x.test/b"})
        self.assertEqual(grade.lint_delta(["w1", "w2"], ["w1"]), ["w2"])

if __name__ == "__main__":
    unittest.main()
