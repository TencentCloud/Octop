#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$DIR/toolkit.py" "$@"
