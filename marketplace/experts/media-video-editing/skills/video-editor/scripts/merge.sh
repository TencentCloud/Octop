#!/bin/bash
# Merge multiple videos
# Usage: merge.sh <video1> <video2> [video3...] --out <output>

set -e

VIDEOS=()
OUTPUT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --out)
      OUTPUT="$2"
      shift 2
      ;;
    -*)
      echo "Unknown option: $1"
      exit 1
      ;;
    *)
      VIDEOS+=("$1")
      shift
      ;;
  esac
done

if [[ ${#VIDEOS[@]} -lt 2 ]] || [[ -z "$OUTPUT" ]]; then
  echo "Usage: merge.sh <video1> <video2> [video3...] --out <output>"
  exit 1
fi

# Create temp file list
TEMP_LIST=$(mktemp)
trap "rm -f $TEMP_LIST" EXIT

for video in "${VIDEOS[@]}"; do
  echo "file '$(realpath "$video")'" >> "$TEMP_LIST"
done

# Merge videos
ffmpeg -f concat -safe 0 -i "$TEMP_LIST" -c copy "$OUTPUT"

echo "Merge complete: $OUTPUT"
