#!/usr/bin/env bash
# Octop green portable launcher (macOS / Linux).
# Usage:
#   ./start.sh
#   ./start.sh --home /path/to/data
#   ./start.sh --home ./data --host 0.0.0.0 --port 8088
#
# When --host/--port are omitted, the bind address comes from config.json
# (default 127.0.0.1:8088), so hand-edited bind_host values are preserved.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export OCTOP_HOME="${OCTOP_HOME:-${ROOT}/data}"

HOST="127.0.0.1"
PORT="8088"
HOST_ARG=""
PORT_ARG=""
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
      HOST_ARG="$2"
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || { echo "start.sh: --port requires a value" >&2; exit 1; }
      PORT="$2"
      PORT_ARG="$2"
      shift 2
      ;;
    -h|--help)
      cat <<EOF
Octop green portable launcher

Usage: ./start.sh [--home DIR] [--host HOST] [--port PORT] [octop run args...]

Defaults:
  OCTOP_HOME / --home   ${ROOT}/data
  --host                127.0.0.1 (only forwarded when given; otherwise config.json decides)
  --port                8088 (only forwarded when given; otherwise config.json decides)

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

RUN_ARGS=()
if [[ -n "$HOST_ARG" ]]; then
  RUN_ARGS+=(--host "$HOST_ARG")
fi
if [[ -n "$PORT_ARG" ]]; then
  RUN_ARGS+=(--port "$PORT_ARG")
fi

echo "[octop] home=${OCTOP_HOME}"
echo "[octop] http://${HOST}:${PORT}"
if [[ ${#EXTRA[@]} -gt 0 ]]; then
  exec "$PY" "${ROOT}/launch.py" run "${RUN_ARGS[@]}" "${EXTRA[@]}"
else
  exec "$PY" "${ROOT}/launch.py" run "${RUN_ARGS[@]}"
fi
