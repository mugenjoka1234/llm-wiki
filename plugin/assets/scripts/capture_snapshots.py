#!/usr/bin/env python3
"""Capture verbatim page text from research file source URLs.

Usage:
  capture_snapshots.py <research-file-path> <snapshots-dir> [--update-source]

Reads ## Sources section from the research markdown file,
fetches each URL, saves verbatim text as <snapshots-dir>/<site-slug>-YYYY-MM-DD.txt

With --update-source: also appends a ## Snapshots section to the research file
listing all captured files with clickable relative links.

Exit codes: 0 = all captured, 1 = some failed (partial success), 2 = no sources found
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

# Browser-like User-Agent to avoid Cloudflare / bot blocks on support docs
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT = 15  # seconds per URL


def extract_sources(research_file: Path) -> list[dict]:
    """Parse ## Sources section — returns [{title, url}]."""
    text = research_file.read_text()
    m = re.search(r"^## Sources\s*\n(.*?)(?:^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not m:
        return []
    section = m.group(1)
    sources = []
    # Format: - [Title](https://url) — any trailing text
    for match in re.finditer(r"-\s+\[([^\]]+)\]\((https?://[^\)]+)\)", section):
        title, url = match.group(1).strip(), match.group(2).strip()
        sources.append({"title": title, "url": url})
    return sources


def url_to_slug(url: str, title: str) -> str:
    """Convert URL + title to a filesystem-safe slug."""
    # Use the title for readability, fall back to URL domain+path
    base = title if title else url
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower())
    slug = slug.strip("-")[:60]
    today = date.today().isoformat()
    return f"{slug}-{today}"


def fetch_url(url: str) -> str | None:
    """Fetch URL text content. Returns text or None on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            # Detect encoding
            encoding = "utf-8"
            if "charset=" in content_type:
                encoding = content_type.split("charset=")[-1].split(";")[0].strip()
            try:
                text = raw.decode(encoding, errors="replace")
            except (LookupError, UnicodeDecodeError):
                text = raw.decode("utf-8", errors="replace")
            # Strip HTML tags for plain-text representation
            # Remove scripts and styles first
            text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            # Convert block elements to newlines
            text = re.sub(r"<(?:br|p|div|h[1-6]|li|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
            # Strip remaining tags
            text = re.sub(r"<[^>]+>", " ", text)
            # Decode HTML entities
            text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            text = text.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
            # Collapse whitespace
            text = re.sub(r" {2,}", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
        return None


def update_source_file(research_file: Path, snapshots_dir: Path,
                       captured: list[dict]) -> None:
    """Append ## Snapshots section to the research file if not already present."""
    text = research_file.read_text()
    if "## Snapshots" in text:
        return  # already has the section

    # Compute relative path from research_file's parent to snapshots_dir
    try:
        rel = snapshots_dir.relative_to(research_file.parent)
        prefix = str(rel)
    except ValueError:
        prefix = str(snapshots_dir)

    lines = ["", "## Snapshots", ""]
    for item in captured:
        fname = item["file"]
        fpath = snapshots_dir / fname
        title = fname.rsplit("-2026-", 1)[0].replace("-", " ").title()
        if fpath.exists():
            header_text = fpath.read_text()[:200]
            title_match = re.search(r"^Title: (.+)$", header_text, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()
        lines.append(f"- [{title}]({prefix}/{fname})")

    research_file.write_text(text.rstrip() + "\n" + "\n".join(lines) + "\n")


def main() -> int:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <research-file> <snapshots-dir> [--update-source]",
              file=sys.stderr)
        return 2

    research_file = Path(sys.argv[1])
    snapshots_dir = Path(sys.argv[2])
    update_source = "--update-source" in sys.argv

    if not research_file.is_file():
        print(f"error: {research_file} not found", file=sys.stderr)
        return 2

    sources = extract_sources(research_file)
    if not sources:
        print(json.dumps({"status": "no_sources", "captured": 0, "failed": 0}))
        return 2

    snapshots_dir.mkdir(parents=True, exist_ok=True)

    captured, failed, results = [], [], []

    for source in sources:
        url, title = source["url"], source["title"]
        slug = url_to_slug(url, title)
        out_path = snapshots_dir / f"{slug}.txt"

        print(f"Fetching: {url}", flush=True)
        text = fetch_url(url)

        if text and len(text) > 100:
            header = (
                f"Source: {url}\n"
                f"Title: {title}\n"
                f"Captured: {date.today().isoformat()}\n"
                f"{'='*60}\n\n"
            )
            out_path.write_text(header + text)
            captured.append({"url": url, "file": out_path.name})
            print(f"  → saved {out_path.name} ({len(text)} chars)", flush=True)
        else:
            msg = "empty response" if text is not None else "fetch failed"
            failed.append({"url": url, "reason": msg})
            print(f"  → failed ({msg})", flush=True)

    if update_source and captured:
        update_source_file(research_file, snapshots_dir, captured)
        print(f"  → updated {research_file.name} with ## Snapshots section", flush=True)

    summary = {
        "status": "done",
        "captured": len(captured),
        "failed": len(failed),
        "files": [r["file"] for r in captured],
    }
    print(json.dumps(summary))
    return 0 if failed == [] else 1


if __name__ == "__main__":
    sys.exit(main())
