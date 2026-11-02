#!/usr/bin/env bash
# check_memory_freshness.sh
#
# Daily 0:00 reconciliation: detect when MEMORY.md index is older than any
# topical file under memory/child/. Run from the parenting-companion scene
# at midnight via HEARTBEAT.
#
# Exit codes:
#   0  — index is fresh, nothing to do
#   1  — fatal error (missing files, bad workspace)
#   2  — found N file(s) newer than MEMORY.md (caller should sync)
#
# This script never modifies any file. It only reports — the agent does
# the actual sync via edit_file in the same heartbeat turn.

set -euo pipefail

WORKSPACE="${OCTOP_WORKSPACE:-$HOME/.octop/workspace}"
MEMORY_INDEX="$WORKSPACE/MEMORY.md"
CHILD_DIR="$WORKSPACE/memory/child"

if [ ! -d "$WORKSPACE" ]; then
    echo "ERROR: workspace not found at $WORKSPACE"
    exit 1
fi

if [ ! -f "$MEMORY_INDEX" ]; then
    echo "ERROR: MEMORY.md not found at $MEMORY_INDEX"
    exit 1
fi

if [ ! -d "$CHILD_DIR" ]; then
    echo "INFO: $CHILD_DIR does not exist yet — nothing to check"
    exit 0
fi

# stat(1) is BSD-style on macOS, GNU-style on Linux. Probe once.
if stat -f %m "$MEMORY_INDEX" >/dev/null 2>&1; then
    STAT_FMT='-f %m'
else
    STAT_FMT='-c %Y'
fi

# shellcheck disable=SC2086
INDEX_MTIME=$(stat $STAT_FMT "$MEMORY_INDEX")

# Cross-platform date formatting
fmt_ts() {
    if date -r "$1" '+%Y-%m-%d %H:%M' >/dev/null 2>&1; then
        date -r "$1" '+%Y-%m-%d %H:%M'
    else
        date -d "@$1" '+%Y-%m-%d %H:%M'
    fi
}

echo "MEMORY.md last modified: $(fmt_ts "$INDEX_MTIME")"
echo ""

NEWER_COUNT=0
NEWER_FILES=()

while IFS= read -r -d '' file; do
    # shellcheck disable=SC2086
    FILE_MTIME=$(stat $STAT_FMT "$file")
    if [ "$FILE_MTIME" -gt "$INDEX_MTIME" ]; then
        NEWER_COUNT=$((NEWER_COUNT + 1))
        REL_PATH="${file#"$WORKSPACE/"}"
        NEWER_FILES+=("$REL_PATH ($(fmt_ts "$FILE_MTIME"))")
    fi
done < <(find "$CHILD_DIR" -type f -name '*.md' -print0)

if [ "$NEWER_COUNT" -eq 0 ]; then
    echo "✅ All memory files in sync"
    exit 0
fi

echo "⚠️  Found $NEWER_COUNT file(s) newer than MEMORY.md:"
for f in "${NEWER_FILES[@]}"; do
    echo "  - $f"
done
exit 2
