#!/bin/bash
# Cut/trim video segment
# Usage: cut.sh <input> --start <time> [--end <time> | --duration <seconds>] --out <output>

set -e

INPUT=""
START=""
END=""
DURATION=""
OUTPUT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --start)
      START="$2"
      shift 2
      ;;
    --end)
      END="$2"
      shift 2
      ;;
    --duration)
      DURATION="$2"
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

if [[ -z "$INPUT" ]] || [[ -z "$START" ]] || [[ -z "$OUTPUT" ]]; then
  echo "Usage: cut.sh <input> --start <time> [--end <time> | --duration <seconds>] --out <output>"
  echo "Time format: HH:MM:SS or seconds"
  exit 1
fi

if [[ -z "$END" ]] && [[ -z "$DURATION" ]]; then
  echo "Error: Must specify either --end or --duration"
  exit 1
fi

# Build ffmpeg command
if [[ -n "$DURATION" ]]; then
  ffmpeg -i "$INPUT" -ss "$START" -t "$DURATION" -c copy -avoid_negative_ts make_zero "$OUTPUT"
else
  ffmpeg -i "$INPUT" -ss "$START" -to "$END" -c copy -avoid_negative_ts make_zero "$OUTPUT"
fi

echo "Cut complete: $OUTPUT"
