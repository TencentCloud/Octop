#!/bin/bash
# Adjust video speed
# Usage: speed.sh <input> --rate <speed> --out <output>
# speed: 2.0 = 2x faster, 0.5 = half speed

set -e

INPUT=""
RATE=""
OUTPUT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --rate)
      RATE="$2"
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

if [[ -z "$INPUT" ]] || [[ -z "$RATE" ]] || [[ -z "$OUTPUT" ]]; then
  echo "Usage: speed.sh <input> --rate <speed> --out <output>"
  echo "speed: 2.0 = 2x faster, 0.5 = half speed"
  exit 1
fi

# Adjust speed using setpts for video and atempo for audio
# atempo only works between 0.5 and 2.0, so we may need to chain filters
if (( $(echo "$RATE >= 0.5 && $RATE <= 2.0" | bc -l) )); then
  ffmpeg -i "$INPUT" -filter_complex "[0:v]setpts=PTS/$RATE[v];[0:a]atempo=$RATE[a]" -map "[v]" -map "[a]" "$OUTPUT"
else
  echo "Warning: Speed rate outside 0.5-2.0 range may require multiple filter passes"
  ffmpeg -i "$INPUT" -filter_complex "[0:v]setpts=PTS/$RATE[v]" -map "[v]" -an "$OUTPUT"
fi

echo "Speed adjustment complete: $OUTPUT"
