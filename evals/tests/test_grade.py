import json, os, subprocess, sys, tempfile, unittest
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

    def test_canon(self):
        self.assertEqual(grade.canon("digests/foo"), "foo")
        self.assertEqual(grade.canon("questions/bar"), "bar")
        self.assertEqual(grade.canon("foo"), "foo")

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
        self.assertFalse(out["is_error"])
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


class TestCLI(unittest.TestCase):
    def _fixture(self, d):
        fx = os.path.join(d, "fx"); os.makedirs(os.path.join(fx, "wiki"))
        open(os.path.join(fx, "wiki", "page-a.md"), "w").write("a")
        json.dump({"pages": {}, "entities": {}},
                  open(os.path.join(fx, "wiki", "_graph.json"), "w"))
        json.dump({"content_hash": "h" * 64, "lint_baseline": [], "lint_exit": 0},
                  open(os.path.join(fx, "fixture-manifest.json"), "w"))
        lb = os.path.join(d, "labels"); os.makedirs(lb)
        json.dump({"fixture_hash": "h" * 64,
                   "query": {"q01": {"relevant": ["page-a"], "primary": ["page-a"]}}},
                  open(os.path.join(lb, "ground-truth.json"), "w"))
        sb = os.path.join(d, "sb"); os.makedirs(os.path.join(sb, "wiki"))
        open(os.path.join(sb, "wiki", "page-a.md"), "w").write("a")
        return fx, lb, sb

    def test_query_pass_and_hash_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            fx, lb, sb = self._fixture(d)
            tr = os.path.join(d, "t.jsonl")
            with open(tr, "w") as f:
                f.write(json.dumps({"type": "result", "subtype": "success",
                    "result": "Answer.\nSOURCES (most relevant first): [[page-a]]",
                    "usage": {"input_tokens": 1}, "total_cost_usd": 0.01,
                    "num_turns": 1}))
            out = os.path.join(d, "g.json")
            base = [sys.executable, os.path.join(os.path.dirname(__file__), "..", "grade.py"),
                    "--case-id", "q01", "--case-type", "query", "--sandbox", sb,
                    "--fixture", fx, "--labels", lb, "--transcript", tr, "--out", out]
            r = subprocess.run(base, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            g = json.load(open(out))
            self.assertTrue(g["pass"]); self.assertEqual(g["metrics"]["mrr"], 1.0)
            # twin rep id aliases to the paired query labels
            r_twin = subprocess.run([x if x != "q01" else "twin01-rep2" for x in
                                     [y if y != "query" else "twin" for y in base]],
                                    capture_output=True, text=True)
            self.assertEqual(r_twin.returncode, 0, r_twin.stdout + r_twin.stderr)
            # hash refusal
            json.dump({"fixture_hash": "x" * 64, "query": {}},
                      open(os.path.join(lb, "ground-truth.json"), "w"))
            r2 = subprocess.run(base, capture_output=True, text=True)
            self.assertEqual(r2.returncode, 2)

if __name__ == "__main__":
    unittest.main()
