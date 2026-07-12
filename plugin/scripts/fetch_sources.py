#!/usr/bin/env python3
"""Fetch research source URLs once and store clean markdown snapshots.

Pluggable backends: FreeFetcher (default, stdlib) and FirecrawlFetcher (opt-in CLI).
Reads a plan JSON of URLs, writes raw/snapshots/<slug>-<date>.md files each with a
YAML front-block, and emits a fetch-manifest.json.

Exit codes:
  0 = at least one URL fetched successfully
  1 = every URL failed (free path) OR usage error
  3 = firecrawl requested but unavailable/failed (FC-16 — caller must ask the user)
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

THIN_THRESHOLD = 500  # chars of extracted content below which free fetch is "thin"

_BLOCK_TAGS = r"(?:br|p|div|h[1-6]|li|tr|article|section)"
_DROP_TAGS = ["script", "style", "nav", "header", "footer", "aside"]


def extract_main_content(html: str) -> tuple[str, str]:
    """Return (title, clean_markdown_text) from raw HTML.

    Strips chrome (nav/header/footer/aside) and non-content (script/style),
    keeps the body text. Title comes from <title>.
    """
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""

    text = html
    for tag in _DROP_TAGS:
        text = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", " ", text,
                      flags=re.DOTALL | re.IGNORECASE)
    # Block elements -> newlines so paragraphs survive tag stripping.
    text = re.sub(rf"<{_BLOCK_TAGS}[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)  # strip remaining tags
    text = (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                .replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'"))
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return title, text.strip()


def build_frontblock(source_url: str, final_url: str, title: str,
                     backend: str, captured: str) -> str:
    """YAML front-block recording the exact original URL for citation integrity."""
    return (
        "---\n"
        f"source_url: {source_url}\n"
        f"final_url: {final_url}\n"
        f"title: {title}\n"
        f"backend: {backend}\n"
        f"captured: {captured}\n"
        "---\n"
    )


def url_to_slug(url: str, title: str, today: str) -> str:
    base = title if title else url
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:60]
    return f"{slug}-{today}"


@dataclass
class FetchResult:
    original_url: str
    final_url: str
    title: str
    markdown: str
    status: str  # "ok" or "failed:<reason>"
    backend: str


class FreeFetcher:
    """Stdlib fetcher with injectable openers for testing and JS escalation."""

    backend = "free"

    def __init__(self, opener=None, js_opener=None):
        self._opener = opener or _default_opener
        self._js_opener = js_opener

    def fetch(self, url: str, recency: str | None = None) -> FetchResult:
        try:
            final_url, html = self._opener(url)
        except Exception as e:  # noqa: BLE001 — record reason, keep run going
            return FetchResult(url, url, "", "", f"failed:{type(e).__name__}", self.backend)
        title, text = extract_main_content(html)
        if len(text) < THIN_THRESHOLD and self._js_opener is not None:
            try:
                final_url, html = self._js_opener(url)
                title, text = extract_main_content(html)
            except Exception:  # noqa: BLE001 — escalation is best-effort
                pass
        if len(text) < THIN_THRESHOLD:
            return FetchResult(url, final_url, title, text, "failed:thin", self.backend)
        return FetchResult(url, final_url, title, text, "ok", self.backend)


def _default_opener(url: str) -> tuple[str, str]:
    """Real network opener. Returns (final_url, raw_html)."""
    import urllib.request
    ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=15) as resp:
        final_url = resp.geturl()
        raw = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        enc = "utf-8"
        if "charset=" in ctype:
            enc = ctype.split("charset=")[-1].split(";")[0].strip()
        try:
            html = raw.decode(enc, errors="replace")
        except LookupError:
            html = raw.decode("utf-8", errors="replace")
        return final_url, html


def write_snapshot(result: FetchResult, snapshots_dir: Path, today: str) -> str:
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    fname = url_to_slug(result.original_url, result.title, today) + ".md"
    fb = build_frontblock(result.original_url, result.final_url, result.title,
                          result.backend, today)
    (snapshots_dir / fname).write_text(fb + "\n" + result.markdown + "\n")
    return fname


def write_manifest(results: list[FetchResult], snapshots_dir: Path,
                   files: dict[str, str]) -> None:
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    entries = [{
        "original_url": r.original_url,
        "title": r.title,
        "file": files.get(r.original_url),
        "status": r.status,
        "backend": r.backend,
    } for r in results]
    (snapshots_dir / "fetch-manifest.json").write_text(json.dumps(entries, indent=2))


class FirecrawlUnavailable(RuntimeError):
    """Firecrawl was explicitly requested but is missing/failed. Caller must ask the user."""


def _default_runner(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout


def firecrawl_available(env: dict, runner=None) -> bool:
    runner = runner or _default_runner
    if not env.get("FIRECRAWL_API_KEY"):
        return False
    try:
        rc, _ = runner(["firecrawl", "--version"])
    except Exception:  # noqa: BLE001
        return False
    return rc == 0


class FirecrawlFetcher:
    """Backed by the Firecrawl CLI, matching Firecrawl's published skill contract."""

    backend = "firecrawl"

    def __init__(self, runner=None):
        self._runner = runner or _default_runner

    def fetch(self, url: str, recency: str | None = None) -> FetchResult:
        cmd = ["firecrawl", "scrape", url, "--only-main-content",
               "--format", "markdown", "--redact-pii", "--json"]
        try:
            rc, out = self._runner(cmd)
        except Exception as e:  # noqa: BLE001
            raise FirecrawlUnavailable(f"firecrawl CLI error: {e}") from e
        if rc != 0:
            raise FirecrawlUnavailable(f"firecrawl exited {rc}: {out[:200]}")
        data = json.loads(out)
        meta = data.get("metadata", {})
        markdown = data.get("markdown", "")
        final_url = meta.get("sourceURL", url)
        title = meta.get("title", "")
        status = "ok" if len(markdown) >= THIN_THRESHOLD else "failed:thin"
        return FetchResult(url, final_url, title, markdown, status, self.backend)


def run(plan: list[dict], snapshots_dir: Path, backend: str, env: dict,
        today: str, free_fetcher=None, fc_fetcher=None) -> int:
    if backend == "firecrawl":
        if fc_fetcher is None and not firecrawl_available(env):
            print(json.dumps({"status": "firecrawl_unavailable",
                              "reason": "missing FIRECRAWL_API_KEY or CLI"}))
            return 3
        fetcher = fc_fetcher or FirecrawlFetcher()
    else:
        fetcher = free_fetcher or FreeFetcher()

    results: list[FetchResult] = []
    files: dict[str, str] = {}
    for item in plan:
        url = item["url"]
        try:
            res = fetcher.fetch(url, recency=item.get("recency"))
        except FirecrawlUnavailable as e:
            print(json.dumps({"status": "firecrawl_unavailable", "reason": str(e)}))
            return 3
        results.append(res)
        if res.status == "ok":
            files[url] = write_snapshot(res, snapshots_dir, today)

    write_manifest(results, snapshots_dir, files)
    any_ok = any(r.status == "ok" for r in results)
    print(json.dumps({"status": "done", "ok": len(files),
                      "failed": len(results) - len(files)}))
    return 0 if any_ok else 1


def main(argv: list[str] | None = None) -> int:
    import argparse
    import os
    from datetime import date
    p = argparse.ArgumentParser(description="Fetch plan URLs into snapshots.")
    p.add_argument("--plan", required=True, help="Path to plan JSON [{url, recency}].")
    p.add_argument("--snapshots-dir", required=True)
    p.add_argument("--fetcher", default="free", choices=["free", "firecrawl"])
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text())
    return run(plan, Path(args.snapshots_dir), backend=args.fetcher,
               env=dict(os.environ), today=date.today().isoformat())


if __name__ == "__main__":
    import sys
    sys.exit(main())
