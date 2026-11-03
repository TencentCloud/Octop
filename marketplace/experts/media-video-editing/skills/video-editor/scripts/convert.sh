#!/bin/bash
# Convert video format
# Usage: convert.sh <input> --format <mp4|mov|avi|mkv|webm> --out <output>

set -e

INPUT=""
FORMAT=""
OUTPUT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --format)
      FORMAT="$2"
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
  echo "Usage: convert.sh <input> --format <mp4|mov|avi|mkv|webm> --out <output>"
  exit 1
fi

# Convert video
ffmpeg -i "$INPUT" -c:v libx264 -c:a aac -pix_fmt yuv420p "$OUTPUT"

echo "Conversion complete: $OUTPUT"
