#!/bin/bash
# Resize video
# Usage: resize.sh <input> [--width <w> --height <h> | --scale <height>] --out <output>

set -e

INPUT=""
WIDTH=""
HEIGHT=""
SCALE=""
OUTPUT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --width)
      WIDTH="$2"
      shift 2
      ;;
    --height)
      HEIGHT="$2"
      shift 2
      ;;
    --scale)
      SCALE="$2"
      shift 2
      ;;
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
  echo "Usage: resize.sh <input> [--width <w> --height <h> | --scale <height>] --out <output>"
  exit 1
fi

if [[ -n "$SCALE" ]]; then
  # Scale proportionally to height
  ffmpeg -i "$INPUT" -vf "scale=-2:$SCALE" -c:a copy "$OUTPUT"
elif [[ -n "$WIDTH" ]] && [[ -n "$HEIGHT" ]]; then
  # Exact dimensions
  ffmpeg -i "$INPUT" -vf "scale=$WIDTH:$HEIGHT" -c:a copy "$OUTPUT"
else
  echo "Error: Must specify either --scale or both --width and --height"
  exit 1
fi

echo "Resize complete: $OUTPUT"
