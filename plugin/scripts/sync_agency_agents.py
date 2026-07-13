#!/usr/bin/env python3
"""Maintainer-only sync of the agency-agents persona catalog.

Pulls `msitarzewski/agency-agents` via `gh api` (the tarball endpoint — a
single HTTP request) and vendors only the division-directory persona `.md`
files into `plugin/assets/agency-agents/`, preserving relative paths. Non-
division content is skipped: `examples/`, `scripts/`, `integrations/`,
`strategy/`, `.github/`, and root-level files (README, LICENSE, etc. — the
license text is instead embedded verbatim in the generated ATTRIBUTION.md).

The sync is idempotent: the new tree is built in a temp directory and then
swapped into place atomically (old dest renamed aside, new dest renamed in,
old dest removed) — a re-run fully replaces the previous vendored content.

The vendored files are third-party content. This script is the only writer;
do not hand-edit anything under the destination directory.

Usage:
    python3 sync_agency_agents.py [--ref main] [--dest DIR]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import date, timezone
from pathlib import Path

SOURCE_OWNER = "msitarzewski"
SOURCE_REPO = "agency-agents"
SOURCE_URL = f"https://github.com/{SOURCE_OWNER}/{SOURCE_REPO}"

# Non-division top-level content: skipped entirely.
EXCLUDED_TOP_LEVEL = {"examples", "scripts", "integrations", "strategy"}

DEFAULT_DEST = Path(__file__).resolve().parent.parent / "assets" / "agency-agents"


def fetch_tarball(ref: str, dest_path: Path) -> None:
    """Fetch the repo tarball at `ref` via `gh api` into dest_path.

    A single HTTP request (`gh api` follows the redirect and streams the
    tarball bytes) — deliberately gentler than a tree call + per-file blob
    fetches.
    """
    with dest_path.open("wb") as f:
        subprocess.run(
            ["gh", "api", f"repos/{SOURCE_OWNER}/{SOURCE_REPO}/tarball/{ref}"],
            stdout=f,
            check=True,
        )


def extract_tarball(tarball_path: Path, extract_to: Path) -> Path:
    """Extract tarball, return the path to its single top-level source dir."""
    with tarfile.open(tarball_path, "r:gz") as tar:
        tar.extractall(extract_to, filter="data")
    entries = [p for p in extract_to.iterdir() if p.is_dir()]
    if len(entries) != 1:
        raise RuntimeError(
            f"expected exactly one top-level dir in tarball, found {entries}"
        )
    return entries[0]


def resolved_sha_from_dirname(dirname: str) -> str:
    """GitHub tarball's top-level dir is named '{owner}-{repo}-{short_sha}'."""
    prefix = f"{SOURCE_OWNER}-{SOURCE_REPO}-"
    if not dirname.startswith(prefix):
        raise RuntimeError(f"unexpected tarball directory name: {dirname!r}")
    return dirname[len(prefix):]


def is_division_dir(name: str) -> bool:
    return name not in EXCLUDED_TOP_LEVEL and not name.startswith(".")


def collect_division_md_files(source_root: Path) -> list[Path]:
    """Relative paths (under source_root) of persona .md files to vendor."""
    files = []
    for top in sorted(p for p in source_root.iterdir() if p.is_dir()):
        if not is_division_dir(top.name):
            continue
        for md in sorted(top.rglob("*.md")):
            files.append(md.relative_to(source_root))
    return files


def build_attribution(ref: str, sha: str, license_text: str) -> str:
    sync_date = date.today().isoformat()
    return f"""# Attribution

The agent persona files vendored under this directory (`agency-agents/`,
excluding this file) are sourced from a third-party catalog and are **not**
original work of this plugin. Do not hand-edit them — re-run
`plugin/scripts/sync_agency_agents.py` to refresh.

- Source repository: {SOURCE_URL}
- Synced ref: `{ref}`
- Synced commit: `{sha}`
- Sync date: {sync_date}

In-file credits, author notes, and any other attribution text embedded
within individual persona files are preserved verbatim as vendored — do not
strip or rewrite them.

## License (MIT, from the source repository)

```
{license_text.strip()}
```
"""


def sync(ref: str, dest: Path) -> dict:
    """Run the sync. Returns stats: {"sha": ..., "divisions": {name: count}, "total": N}."""
    with tempfile.TemporaryDirectory(prefix="agency-agents-sync-") as tmp:
        tmp_path = Path(tmp)
        tarball_path = tmp_path / "source.tar.gz"
        fetch_tarball(ref, tarball_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        source_root = extract_tarball(tarball_path, extract_dir)
        sha = resolved_sha_from_dirname(source_root.name)

        license_path = source_root / "LICENSE"
        license_text = (
            license_path.read_text(encoding="utf-8")
            if license_path.is_file()
            else ""
        )

        new_dest = tmp_path / "new_dest"
        new_dest.mkdir()

        divisions: dict[str, int] = {}
        for rel in collect_division_md_files(source_root):
            division = rel.parts[0]
            divisions[division] = divisions.get(division, 0) + 1
            target = new_dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_root / rel, target)

        (new_dest / "ATTRIBUTION.md").write_text(
            build_attribution(ref, sha, license_text), encoding="utf-8"
        )

        # Atomic-ish swap: build done above; now replace dest with new_dest.
        dest.parent.mkdir(parents=True, exist_ok=True)
        old_dest = None
        if dest.exists():
            old_dest = dest.with_name(dest.name + ".old-sync-tmp")
            if old_dest.exists():
                shutil.rmtree(old_dest)
            dest.rename(old_dest)
        try:
            new_dest.rename(dest)
        except Exception:
            if old_dest is not None:
                old_dest.rename(dest)
            raise
        if old_dest is not None:
            shutil.rmtree(old_dest)

        total = sum(divisions.values())
        return {"sha": sha, "divisions": divisions, "total": total}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="main", help="git ref to sync (default: main)")
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help="destination directory (default: plugin/assets/agency-agents)",
    )
    args = parser.parse_args(argv)

    stats = sync(args.ref, args.dest)

    print(f"Synced {SOURCE_URL} @ {args.ref} (commit {stats['sha']}) -> {args.dest}")
    print(f"Total persona files: {stats['total']}")
    for division in sorted(stats["divisions"]):
        print(f"  {division}: {stats['divisions'][division]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
