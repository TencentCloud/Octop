#!/bin/bash
# Crop video region
# Usage: crop.sh <input> --x <x> --y <y> --width <w> --height <h> --out <output>

set -e

INPUT=""
X=""
Y=""
WIDTH=""
HEIGHT=""
OUTPUT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --x)
      X="$2"
      shift 2
      ;;
    --y)
      Y="$2"
      shift 2
      ;;
    --width)
      WIDTH="$2"
      shift 2
      ;;
    --height)
      HEIGHT="$2"
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

if [[ -z "$INPUT" ]] || [[ -z "$X" ]] || [[ -z "$Y" ]] || [[ -z "$WIDTH" ]] || [[ -z "$HEIGHT" ]] || [[ -z "$OUTPUT" ]]; then
  echo "Usage: crop.sh <input> --x <x> --y <y> --width <w> --height <h> --out <output>"
  exit 1
fi

# Crop video
ffmpeg -i "$INPUT" -vf "crop=$WIDTH:$HEIGHT:$X:$Y" -c:a copy "$OUTPUT"

echo "Crop complete: $OUTPUT"
