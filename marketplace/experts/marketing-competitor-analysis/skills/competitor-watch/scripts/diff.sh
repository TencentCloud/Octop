#!/bin/bash
# competitor-watch/scripts/diff.sh — Compare two snapshots and score changes

set -euo pipefail

# --- Config ---
CONFIG_DIR="${CW_CONFIG_DIR:-$HOME/.config/competitor-watch}"
CONFIG_FILE="$CONFIG_DIR/config.json"

# --- Arguments ---
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <old_snapshot_file> <new_snapshot_file>"
    exit 1
fi
OLD_FILE="$1"
NEW_FILE="$2"

# --- Validation ---
if ! command -v jq &> /dev/null; then echo "jq not installed"; exit 1; fi
if [ ! -f "$OLD_FILE" ] || [ ! -f "$NEW_FILE" ]; then echo "Snapshot file not found"; exit 1; fi

# --- Pre-processing: Filter noise ---
IGNORE_PATTERNS=$(jq -r '.diffing.ignore_patterns | join("|")' "$CONFIG_FILE")
MIN_CHANGE_CHARS=$(jq -r '.diffing.min_change_chars' "$CONFIG_FILE")
SIMILARITY_THRESHOLD=$(jq -r '.diffing.similarity_threshold' "$CONFIG_FILE")

# Use temp files for cleaned content
OLD_CLEAN=$(mktemp)
NEW_CLEAN=$(mktemp)
trap 'rm -f "$OLD_CLEAN" "$NEW_CLEAN"' EXIT

# This is a simple grep-based filter. More complex filtering could use sed.
grep -Eiv "$IGNORE_PATTERNS" "$OLD_FILE" > "$OLD_CLEAN"
grep -Eiv "$IGNORE_PATTERNS" "$NEW_FILE" > "$NEW_CLEAN"

# --- Diff Calculation ---
# Use diff with a unified format for better parsing
RAW_DIFF=$(diff -u "$OLD_CLEAN" "$NEW_CLEAN" || true)

if [ -z "$RAW_DIFF" ]; then
    # No changes at all, exit successfully
    exit 0
fi

LINES_ADDED=$(echo "$RAW_DIFF" | grep -c '^+' || true)
LINES_REMOVED=$(echo "$RAW_DIFF" | grep -c '^-' || true)
# Subtract the file headers from the count
LINES_ADDED=$((LINES_ADDED - 1))
LINES_REMOVED=$((LINES_REMOVED - 1))

TOTAL_CHANGES=$((LINES_ADDED + LINES_REMOVED))
TOTAL_LINES=$(wc -l < "$NEW_CLEAN")

# Avoid division by zero
if [ "$TOTAL_LINES" -eq 0 ]; then
    CHANGE_PERCENT=0
else
    CHANGE_PERCENT=$(awk "BEGIN {printf \"%.4f\", $TOTAL_CHANGES / $TOTAL_LINES}")
fi

# --- Scoring ---
# This is a simplistic scoring model. It could be expanded significantly.
# We'll use the percentage change as a base score.
SCORE=$CHANGE_PERCENT

# Boost score based on keywords
KEYWORDS_CONFIG=$(jq -c '.diffing.keyword_weights' "$CONFIG_FILE")
echo "$KEYWORDS_CONFIG" | jq -c 'to_entries[]' | while IFS= read -r entry; do
    group_name=$(echo "$entry" | jq -r '.key')
    keywords=$(echo "$entry" | jq -r '.value.keywords | join("|")')
    weight=$(echo "$entry" | jq -r '.value.weight')

    # Count keyword matches in added lines
    matches=$(echo "$RAW_DIFF" | grep -E '^\+' | grep -Eic "($keywords)" || true)
    
    if [ "$matches" -gt 0 ]; then
        boost=$(awk "BEGIN {printf \"%.4f\", $matches * $weight * 0.1}")
        SCORE=$(awk "BEGIN {printf \"%.4f\", $SCORE + $boost}")
    fi
done

# --- Decision ---
# Compare score to 1 minus the similarity threshold
SIGNIFICANCE_THRESHOLD=$(awk "BEGIN {printf \"%.4f\", 1 - $SIMILARITY_THRESHOLD}")

# Create summary
SUMMARY_ADDED=$(echo "$RAW_DIFF" | grep '^\+' | sed 's/^+//' | head -n 5 | sed 's/^/• /')
SUMMARY_REMOVED=$(echo "$RAW_DIFF" | grep '^-' | sed 's/^-//' | head -n 5 | sed 's/^/• /')

# --- Output JSON ---
# This structured output is consumed by check.sh
jq -n \
    --argjson score "$SCORE" \
    --argjson changes "$TOTAL_CHANGES" \
    --argjson added "$LINES_ADDED" \
    --argjson removed "$LINES_REMOVED" \
    --argjson percent "$CHANGE_PERCENT" \
    --arg diff "$RAW_DIFF" \
    --arg summary_added "$SUMMARY_ADDED" \
    --arg summary_removed "$SUMMARY_REMOVED" \
    '{
        score: $score,
        total_changes: $changes,
        lines_added: $added,
        lines_removed: $removed,
        change_percentage: $percent,
        summary: {
            added: $summary_added,
            removed: $summary_removed
        },
        raw_diff: $diff
    }'

# --- Exit Code ---
# Exit with 1 if change is significant, 0 otherwise
if (( $(awk "BEGIN {print ($SCORE > $SIGNIFICANCE_THRESHOLD)}") )); then
    exit 1
else
    exit 0
fi
