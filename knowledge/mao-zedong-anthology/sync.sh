#!/usr/bin/env bash
# Sync MaoZeDongAnthology volumes from upstream main.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE="$ROOT/SYNC.json"
UPSTREAM_URL="https://github.com/NpTIme/MaoZeDongAnthology.git"
TMP="${TMPDIR:-/tmp}/mao-sync-$$"
FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

need_sync() {
  if [[ "$FORCE" -eq 1 ]]; then return 0; fi
  if [[ ! -f "$STATE" ]]; then return 0; fi
  python3 - "$STATE" <<'PY'
import json, sys
from datetime import datetime, timezone, timedelta
with open(sys.argv[1]) as f:
    st = json.load(f)
raw = st.get("synced_at") or ""
try:
    synced = datetime.fromisoformat(raw.replace("Z", "+00:00"))
except Exception:
    sys.exit(0)
age = datetime.now(timezone.utc) - synced.astimezone(timezone.utc)
sys.exit(0 if age >= timedelta(days=7) else 1)
PY
}

if ! need_sync; then
  echo "SKIP: last sync younger than 7 days (use --force to sync anyway)"
  cat "$STATE"
  exit 0
fi

mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT
OLD_SHA=""
[[ -f "$STATE" ]] && OLD_SHA="$(python3 -c "import json;print(json.load(open('$STATE')).get('upstream_sha',''))")"

git clone --depth 30 "$UPSTREAM_URL" "$TMP/repo" >/dev/null 2>&1
NEW_SHA="$(cd "$TMP/repo" && git rev-parse HEAD)"
NEW_DATE="$(cd "$TMP/repo" && git show -s --format=%cI HEAD)"
NEW_MSG="$(cd "$TMP/repo" && git show -s --format=%s HEAD)"

REPORT="$TMP/report.md"
{
  echo "## Upstream tip"
  echo "- sha: $NEW_SHA"
  echo "- date: $NEW_DATE"
  echo "- message: $NEW_MSG"
  echo
  if [[ -n "$OLD_SHA" && "$OLD_SHA" != "$NEW_SHA" ]]; then
    echo "## Commits since last sync"
    (cd "$TMP/repo" && git log --oneline "${OLD_SHA}..${NEW_SHA}" 2>/dev/null) || true
  else
    echo "## Commits (recent)"
    (cd "$TMP/repo" && git log --oneline -8)
  fi
  echo
  echo "## Changed paths"
} > "$REPORT"

python3 - "$ROOT/volumes" "$TMP/repo" "$REPORT" <<'PY'
import hashlib, sys
from pathlib import Path
dst, src, report = map(Path, sys.argv[1:])

def digest_tree(base: Path):
    out = {}
    if not base.exists():
        return out
    for f in base.rglob("*.md"):
        rel = str(f.relative_to(base))
        out[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out

# Compare only volume dirs 001-007
vol_dirs = sorted([p for p in src.iterdir() if p.is_dir() and p.name[:3].isdigit()], key=lambda p: p.name)
old = digest_tree(dst)
# Build temp combined view of new vols
new = {}
for vd in vol_dirs:
    for f in vd.rglob("*.md"):
        rel = f"{vd.name}/{f.relative_to(vd)}"
        # normalize to match dst layout: volumes/<vol>/...
        new[str(Path(vd.name) / f.relative_to(vd))] = hashlib.sha256(f.read_bytes()).hexdigest()

# dst keys are relative to volumes/
added = sorted(set(new) - set(old))
removed = sorted(set(old) - set(new))
changed = sorted(k for k in set(old) & set(new) if old[k] != new[k])
with report.open("a", encoding="utf-8") as fh:
    fh.write(f"- added: {len(added)}\n- removed: {len(removed)}\n- modified: {len(changed)}\n\n")
    for label, items in (("Added", added), ("Removed", removed), ("Modified", changed)):
        if not items:
            continue
        fh.write(f"### {label}\n")
        for i in items[:60]:
            fh.write(f"- {i}\n")
        if len(items) > 60:
            fh.write(f"- … and {len(items)-60} more\n")
        fh.write("\n")
Path("/tmp/mao-sync-counts.txt").write_text(f"{len(added)} {len(removed)} {len(changed)}\n")
PY

rm -rf "$ROOT/volumes"
mkdir -p "$ROOT/volumes"
for d in "$TMP/repo"/00*; do
  cp -a "$d" "$ROOT/volumes/"
done
cp "$TMP/repo/README.md" "$ROOT/UPSTREAM_README.md"

# Rebuild reader
python3 "$ROOT/tools/build_reader.py"

ENTRY_COUNT="$(find "$ROOT/volumes" -name '*.md' | wc -l)"
SYNCED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
read -r ADDED REMOVED MODIFIED < /tmp/mao-sync-counts.txt

python3 - "$STATE" "$NEW_SHA" "$NEW_DATE" "$NEW_MSG" "$SYNCED_AT" "$ENTRY_COUNT" "$ADDED" "$REMOVED" "$MODIFIED" "$OLD_SHA" <<'PY'
import json, sys
path, sha, udate, umsg, synced, entries, added, removed, modified, old = sys.argv[1:]
state = {
    "upstream": "https://github.com/NpTIme/MaoZeDongAnthology",
    "upstream_ref": "main",
    "upstream_sha": sha,
    "upstream_commit_date": udate,
    "upstream_commit_message": umsg,
    "previous_upstream_sha": old or None,
    "synced_at": synced,
    "article_count": int(entries),
    "last_diff": {"added": int(added), "removed": int(removed), "modified": int(modified)},
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
cp "$REPORT" "$ROOT/LAST_SYNC_REPORT.md"
echo "SYNCED"
cat "$STATE"
echo
echo "----- CHANGE REPORT -----"
cat "$REPORT"
