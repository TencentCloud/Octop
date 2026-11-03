#!/bin/bash
# Extract audio from video
# Usage: extract-audio.sh <input> --out <output.mp3|aac|wav>

set -e

INPUT=""
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
      if [[ -z "$INPUT" ]]; then
        INPUT="$1"
      else
        echo "Unexpected argument: $1"
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$INPUT" ]] || [[ -z "$OUTPUT" ]]; then
  echo "Usage: extract-audio.sh <input> --out <output.mp3|aac|wav>"
  exit 1
fi

# Determine codec from extension
EXT="${OUTPUT##*.}"
case "$EXT" in
  mp3)
    CODEC="libmp3lame"
    ;;
  aac|m4a)
    CODEC="aac"
    ;;
  wav)
    CODEC="pcm_s16le"
    ;;
  flac)
    CODEC="flac"
    ;;
  *)
    CODEC="copy"
    ;;
esac

# Extract audio
ffmpeg -i "$INPUT" -vn -c:a "$CODEC" "$OUTPUT"

echo "Audio extraction complete: $OUTPUT"
