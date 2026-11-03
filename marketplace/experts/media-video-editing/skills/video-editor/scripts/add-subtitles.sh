#!/bin/bash
# Add subtitles to video
# Usage: add-subtitles.sh <input> <subtitles.srt> --out <output>

set -e

INPUT=""
SUBTITLES=""
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
      elif [[ -z "$SUBTITLES" ]]; then
        SUBTITLES="$1"
      else
        echo "Unexpected argument: $1"
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$INPUT" ]] || [[ -z "$SUBTITLES" ]] || [[ -z "$OUTPUT" ]]; then
  echo "Usage: add-subtitles.sh <input> <subtitles.srt> --out <output>"
  exit 1
fi

# Add subtitles (burn into video)
ffmpeg -i "$INPUT" -vf "subtitles='$SUBTITLES'" -c:a copy "$OUTPUT"

echo "Subtitles added: $OUTPUT"
