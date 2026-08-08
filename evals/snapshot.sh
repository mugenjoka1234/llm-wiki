#!/usr/bin/env bash
# Freeze a live wiki into an eval fixture. Usage: snapshot.sh <wiki-root> <dest-dir>
set -eu
SRC="${1:?usage: snapshot.sh <wiki-root> <dest-dir>}"
DEST="${2:?usage: snapshot.sh <wiki-root> <dest-dir>}"
[ -d "$SRC/wiki" ] || { echo "not a wiki root (no wiki/): $SRC"; exit 2; }
mkdir -p "$DEST"
rsync -a --delete --exclude '.git' --exclude 'fixture-manifest.json' "$SRC/" "$DEST/"

python3 - "$SRC" "$DEST" <<'PYEOF'
import hashlib, json, subprocess, sys, datetime
from pathlib import Path
src, dest = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()

# Lint FIRST — lint.py mutates its target (writes _health.md, regenerates
# catalogs, autofixes trust lines). Hashing before lint would record bytes the
# fixture no longer has the moment it's created.
r = subprocess.run([sys.executable, str(dest / "scripts" / "lint.py")],
                   cwd=dest, capture_output=True, text=True)
baseline = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()]

# Hash SECOND: sorted relative paths + file bytes, post-lint = the stable state
h = hashlib.sha256()
for p in sorted(dest.rglob("*")):
    if p.is_file() and p.name != "fixture-manifest.json":
        h.update(str(p.relative_to(dest)).encode())
        h.update(p.read_bytes())

manifest = {
    "frozen": datetime.date.today().isoformat(),
    "source": str(src),
    "content_hash": h.hexdigest(),
    "lint_baseline": baseline,
    "lint_exit": r.returncode,
}
(dest / "fixture-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(json.dumps({"content_hash": manifest["content_hash"][:12],
                  "lint_exit": r.returncode, "baseline_lines": len(baseline)}))
PYEOF
