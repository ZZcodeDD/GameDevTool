#!/usr/bin/env bash
# Sync local HowToLiveBetter mirror from upstream main.
# Usage: knowledge/how-to-live-better/sync.sh [--force]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE="$ROOT/SYNC.json"
UPSTREAM_URL="https://github.com/eternity4719/HowToLiveBetter.git"
UPSTREAM_API="https://api.github.com/repos/eternity4719/HowToLiveBetter/commits/main"
TMP="${TMPDIR:-/tmp}/hltb-sync-$$"
FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

need_sync() {
  if [[ "$FORCE" -eq 1 ]]; then return 0; fi
  if [[ ! -f "$STATE" ]]; then return 0; fi
  python3 - "$STATE" <<'PY'
import json, sys
from datetime import datetime, timezone, timedelta
path = sys.argv[1]
with open(path) as f:
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

git clone --depth 50 --filter=blob:none --sparse "$UPSTREAM_URL" "$TMP/repo" >/dev/null 2>&1
(
  cd "$TMP/repo"
  git sparse-checkout set book docs skills
)
curl -fsSL -o "$TMP/repo/LICENSE" "https://raw.githubusercontent.com/eternity4719/HowToLiveBetter/main/LICENSE"
curl -fsSL -o "$TMP/repo/README.md" "https://raw.githubusercontent.com/eternity4719/HowToLiveBetter/main/README.md"
curl -fsSL -o "$TMP/repo/AGENTS.md" "https://raw.githubusercontent.com/eternity4719/HowToLiveBetter/main/AGENTS.md"
curl -fsSL -o "$TMP/repo/index.html" "https://raw.githubusercontent.com/eternity4719/HowToLiveBetter/main/index.html"

NEW_SHA="$(cd "$TMP/repo" && git rev-parse HEAD)"
NEW_DATE="$(cd "$TMP/repo" && git show -s --format=%cI HEAD)"
NEW_MSG="$(cd "$TMP/repo" && git show -s --format=%s HEAD)"

# Capture file-level diff before overwrite (book + docs + skills + root docs)
DIFF_OUT="$TMP/diff.txt"
{
  echo "## Upstream tip"
  echo "- sha: $NEW_SHA"
  echo "- date: $NEW_DATE"
  echo "- message: $NEW_MSG"
  echo
  if [[ -n "$OLD_SHA" && "$OLD_SHA" != "$NEW_SHA" ]]; then
    echo "## Commits since last sync ($OLD_SHA → $NEW_SHA)"
    (cd "$TMP/repo" && git log --oneline "${OLD_SHA}..${NEW_SHA}" 2>/dev/null) || \
      (cd "$TMP/repo" && git log --oneline -20)
    echo
  elif [[ -z "$OLD_SHA" ]]; then
    echo "## Commits (first sync baseline, last 10)"
    (cd "$TMP/repo" && git log --oneline -10)
    echo
  else
    echo "## Commits"
    echo "(already at $NEW_SHA)"
    echo
  fi
  echo "## Changed paths (local mirror vs upstream)"
} > "$DIFF_OUT"

# Path-level compare against current mirror
python3 - "$ROOT" "$TMP/repo" "$DIFF_OUT" <<'PY'
import hashlib, os, sys
from pathlib import Path

root = Path(sys.argv[1])
src = Path(sys.argv[2])
out = Path(sys.argv[3])
tracked = ["book", "docs", "skills", "LICENSE", "README.md", "AGENTS.md", "index.html"]

def files_under(base: Path, rel: str):
    p = base / rel
    if p.is_file():
        return [p]
    if not p.exists():
        return []
    return [f for f in p.rglob("*") if f.is_file() and ".git" not in f.parts]

def digest(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()

old_map, new_map = {}, {}
for rel in tracked:
    for f in files_under(root, rel):
        old_map[str(f.relative_to(root))] = digest(f)
    for f in files_under(src, rel):
        new_map[str(f.relative_to(src))] = digest(f)

added = sorted(set(new_map) - set(old_map))
removed = sorted(set(old_map) - set(new_map))
changed = sorted(k for k in set(old_map) & set(new_map) if old_map[k] != new_map[k])

with out.open("a", encoding="utf-8") as fh:
    fh.write(f"- added: {len(added)}\n")
    fh.write(f"- removed: {len(removed)}\n")
    fh.write(f"- modified: {len(changed)}\n\n")
    for label, items in (("Added", added), ("Removed", removed), ("Modified", changed)):
        if not items:
            continue
        fh.write(f"### {label}\n")
        for i in items[:80]:
            fh.write(f"- {i}\n")
        if len(items) > 80:
            fh.write(f"- … and {len(items) - 80} more\n")
        fh.write("\n")
    if not added and not removed and not changed:
        fh.write("(no file content changes)\n")

# expose counts for JSON
Path(os.environ.get("TMPDIR", "/tmp")).joinpath("hltb-sync-counts.txt").write_text(
    f"{len(added)} {len(removed)} {len(changed)}\n"
)
PY

# Preserve local-only files, replace mirrored trees/files
for name in book docs skills; do
  rm -rf "$ROOT/$name"
  cp -a "$TMP/repo/$name" "$ROOT/$name"
done
for name in LICENSE README.md AGENTS.md index.html; do
  cp -a "$TMP/repo/$name" "$ROOT/$name"
done

ENTRY_COUNT="$(grep -rhc '^### ' "$ROOT/book" | awk '{s+=$1} END{print s+0}')"
SYNCED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
COUNTS="$(cat "${TMPDIR:-/tmp}/hltb-sync-counts.txt" 2>/dev/null || echo "0 0 0")"
read -r ADDED REMOVED MODIFIED <<<"$COUNTS"

python3 - "$STATE" "$NEW_SHA" "$NEW_DATE" "$NEW_MSG" "$SYNCED_AT" "$ENTRY_COUNT" "$ADDED" "$REMOVED" "$MODIFIED" "$OLD_SHA" <<'PY'
import json, sys
path, sha, udate, umsg, synced, entries, added, removed, modified, old = sys.argv[1:]
state = {
    "upstream": "https://github.com/eternity4719/HowToLiveBetter",
    "upstream_ref": "main",
    "upstream_sha": sha,
    "upstream_commit_date": udate,
    "upstream_commit_message": umsg,
    "previous_upstream_sha": old or None,
    "synced_at": synced,
    "entry_count": int(entries),
    "last_diff": {
        "added": int(added),
        "removed": int(removed),
        "modified": int(modified),
    },
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY

cp "$DIFF_OUT" "$ROOT/LAST_SYNC_REPORT.md"
echo "SYNCED"
cat "$STATE"
echo
echo "----- CHANGE REPORT -----"
cat "$DIFF_OUT"
