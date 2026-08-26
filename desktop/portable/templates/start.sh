#!/usr/bin/env bash
# Octop green portable launcher (macOS / Linux).
# Usage:
#   ./start.sh
#   ./start.sh --home /path/to/data
#   ./start.sh --home ./data --host 0.0.0.0 --port 8088
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export OCTOP_HOME="${OCTOP_HOME:-${ROOT}/data}"

HOST="127.0.0.1"
PORT="8088"
EXTRA=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --home)
      [[ $# -ge 2 ]] || { echo "start.sh: --home requires a path" >&2; exit 1; }
      OCTOP_HOME="$2"
      shift 2
      ;;
    --host)
      [[ $# -ge 2 ]] || { echo "start.sh: --host requires a value" >&2; exit 1; }
      HOST="$2"
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || { echo "start.sh: --port requires a value" >&2; exit 1; }
      PORT="$2"
      shift 2
      ;;
    -h|--help)
      cat <<EOF
Octop green portable launcher

Usage: ./start.sh [--home DIR] [--host HOST] [--port PORT] [octop run args...]

Defaults:
  OCTOP_HOME / --home   ${ROOT}/data
  --host                127.0.0.1
  --port                8088

Environment:
  OCTOP_HOME            User data directory (overridden by --home)
EOF
      exit 0
      ;;
    *)
      EXTRA+=("$1")
      shift
      ;;
  esac
done

export OCTOP_HOME
mkdir -p "$OCTOP_HOME"

PY=""
if [[ -x "${ROOT}/runtime/bin/python3" ]]; then
  PY="${ROOT}/runtime/bin/python3"
elif [[ -x "${ROOT}/runtime/bin/python" ]]; then
  PY="${ROOT}/runtime/bin/python"
else
  echo "start.sh: portable Python not found under ${ROOT}/runtime" >&2
  exit 1
fi

# launch.py adds packages/ via site.addsitedir (honours .pth / pywin32).
export PYTHONNOUSERSITE=1
unset PYTHONPATH || true

echo "[octop] home=${OCTOP_HOME}"
echo "[octop] http://${HOST}:${PORT}"
if [[ ${#EXTRA[@]} -gt 0 ]]; then
  exec "$PY" "${ROOT}/launch.py" run --host "$HOST" --port "$PORT" "${EXTRA[@]}"
else
  exec "$PY" "${ROOT}/launch.py" run --host "$HOST" --port "$PORT"
fi
