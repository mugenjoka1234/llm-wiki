"""Pure-Python tests for fetch_sources.py — no network, no Firecrawl CLI."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import fetch_sources as fs


def test_extract_main_content_strips_chrome_keeps_body():
    html = """<html><head><title>My Page</title></head><body>
        <nav>HOME ABOUT CONTACT</nav>
        <header>site header junk</header>
        <article><p>The real content sentence one.</p><p>Sentence two.</p></article>
        <footer>copyright boilerplate 2026</footer>
        <script>var x = 1;</script>
    </body></html>"""
    title, text = fs.extract_main_content(html)
    assert title == "My Page"
    assert "real content sentence one" in text
    assert "Sentence two" in text
    assert "HOME ABOUT CONTACT" not in text
    assert "site header junk" not in text
    assert "copyright boilerplate" not in text
    assert "var x" not in text


def test_build_frontblock_records_exact_source_url_with_query():
    fb = fs.build_frontblock(
        source_url="https://ex.com/path?q=1&r=2",
        final_url="https://ex.com/path",
        title="T",
        backend="free",
        captured="2026-07-03",
    )
    assert fb.startswith("---\n")
    assert "source_url: https://ex.com/path?q=1&r=2" in fb
    assert "final_url: https://ex.com/path" in fb
    assert "backend: free" in fb
    assert "captured: 2026-07-03" in fb
    assert fb.rstrip().endswith("---")


import json


def test_url_to_slug_is_safe_and_dated():
    slug = fs.url_to_slug("https://ex.com/a/b?q=1", "Hello, World!", "2026-07-03")
    assert slug == "hello-world-2026-07-03"


def test_freefetcher_ok_writes_snapshot_with_frontblock(tmp_path):
    html = "<html><head><title>Doc</title></head><body><article>" \
           + "<p>" + ("plenty of real body content here. " * 40) + "</p>" \
           + "</article></body></html>"
    fetcher = fs.FreeFetcher(opener=lambda u: ("https://ex.com/final", html))
    res = fetcher.fetch("https://ex.com/orig?q=1")
    assert res.status == "ok"
    assert res.backend == "free"
    fname = fs.write_snapshot(res, tmp_path, "2026-07-03")
    written = (tmp_path / fname).read_text()
    assert written.startswith("---\n")
    assert "source_url: https://ex.com/orig?q=1" in written
    assert "plenty of real body content" in written


def test_freefetcher_thin_content_flagged_failed():
    fetcher = fs.FreeFetcher(opener=lambda u: ("https://ex.com/x", "<html><body>hi</body></html>"))
    res = fetcher.fetch("https://ex.com/x")
    assert res.status == "failed:thin"


def test_write_manifest_shape(tmp_path):
    r_ok = fs.FetchResult("https://a.com", "https://a.com", "A", "body", "ok", "free")
    r_bad = fs.FetchResult("https://b.com", "https://b.com", "", "", "failed:http-403", "free")
    fs.write_manifest([r_ok, r_bad], tmp_path, {"https://a.com": "a-2026-07-03.md"})
    data = json.loads((tmp_path / "fetch-manifest.json").read_text())
    assert data[0] == {"original_url": "https://a.com", "title": "A",
                       "file": "a-2026-07-03.md", "status": "ok", "backend": "free"}
    assert data[1]["status"] == "failed:http-403"
    assert data[1]["file"] is None


try:
    import pytest
except ImportError:
    pytest = None


def _fc_scrape_ok(cmd):
    payload = json.dumps({"markdown": "clean firecrawl body " * 30,
                          "metadata": {"title": "FC Title", "sourceURL": "https://ex.com/o"}})
    return 0, payload


def test_firecrawl_fetch_ok_parses_json():
    f = fs.FirecrawlFetcher(runner=_fc_scrape_ok)
    res = f.fetch("https://ex.com/o")
    assert res.status == "ok"
    assert res.backend == "firecrawl"
    assert res.title == "FC Title"
    assert "clean firecrawl body" in res.markdown


def test_firecrawl_fetch_uses_required_flags():
    seen = {}
    def runner(cmd):
        seen["cmd"] = cmd
        return _fc_scrape_ok(cmd)
    fs.FirecrawlFetcher(runner=runner).fetch("https://ex.com/o")
    joined = " ".join(seen["cmd"])
    assert "scrape" in joined
    assert "--only-main-content" in joined
    assert "--format markdown" in joined or "--format" in seen["cmd"]
    assert "--redact-pii" in joined


def test_firecrawl_nonzero_raises_unavailable_not_failed_result():
    f = fs.FirecrawlFetcher(runner=lambda cmd: (1, "credit exhausted"))
    with pytest.raises(fs.FirecrawlUnavailable):
        f.fetch("https://ex.com/o")


def test_firecrawl_available_requires_key_and_cli():
    ok = fs.firecrawl_available({"FIRECRAWL_API_KEY": "k"}, runner=lambda cmd: (0, "v1"))
    assert ok is True
    assert fs.firecrawl_available({}, runner=lambda cmd: (0, "v1")) is False
    assert fs.firecrawl_available({"FIRECRAWL_API_KEY": "k"},
                                  runner=lambda cmd: (127, "not found")) is False


def _good_html():
    return "<html><head><title>T</title></head><body><article><p>" \
           + ("body " * 200) + "</p></article></body></html>"


def test_run_free_writes_files_and_manifest(tmp_path):
    plan = [{"url": "https://a.com/x", "recency": None}]
    free = fs.FreeFetcher(opener=lambda u: (u, _good_html()))
    rc = fs.run(plan, tmp_path, backend="free", env={}, today="2026-07-03",
                free_fetcher=free)
    assert rc == 0
    manifest = json.loads((tmp_path / "fetch-manifest.json").read_text())
    assert manifest[0]["status"] == "ok"
    assert (tmp_path / manifest[0]["file"]).exists()


def test_run_free_all_failed_returns_1(tmp_path):
    plan = [{"url": "https://a.com/x", "recency": None}]
    free = fs.FreeFetcher(opener=lambda u: (_ for _ in ()).throw(OSError("boom")))
    rc = fs.run(plan, tmp_path, backend="free", env={}, today="2026-07-03",
                free_fetcher=free)
    assert rc == 1


def test_run_firecrawl_requested_but_unavailable_returns_3(tmp_path):
    plan = [{"url": "https://a.com/x", "recency": None}]
    # firecrawl_available will be False because env lacks the key
    rc = fs.run(plan, tmp_path, backend="firecrawl", env={}, today="2026-07-03")
    assert rc == 3


def test_run_firecrawl_failure_midrun_returns_3(tmp_path):
    plan = [{"url": "https://a.com/x", "recency": None}]
    fc = fs.FirecrawlFetcher(runner=lambda cmd: (1, "credit exhausted"))
    rc = fs.run(plan, tmp_path, backend="firecrawl",
                env={"FIRECRAWL_API_KEY": "k"}, today="2026-07-03",
                fc_fetcher=fc)
    assert rc == 3


def test_freefetcher_escalates_to_js_opener_on_thin():
    thin = "<html><body>hi</body></html>"
    rich = "<html><head><title>JS</title></head><body><article><p>" \
           + ("rendered " * 200) + "</p></article></body></html>"
    fetcher = fs.FreeFetcher(
        opener=lambda u: (u, thin),
        js_opener=lambda u: (u, rich),
    )
    res = fetcher.fetch("https://spa.example/app")
    assert res.status == "ok"
    assert "rendered" in res.markdown


def test_freefetcher_still_thin_after_js_stays_failed():
    thin = "<html><body>hi</body></html>"
    fetcher = fs.FreeFetcher(opener=lambda u: (u, thin), js_opener=lambda u: (u, thin))
    res = fetcher.fetch("https://spa.example/app")
    assert res.status == "failed:thin"
