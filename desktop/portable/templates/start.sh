#!/usr/bin/env bash
# Octop green portable launcher (macOS / Linux).
# Usage:
#   ./start.sh
#   ./start.sh --home /path/to/data
#   ./start.sh --home ./data --host 0.0.0.0 --port 8088
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export OCTOP_HOME="${OCTOP_HOME:-${ROOT}/data}"
export OCTOP_GREEN_PACKAGES="${ROOT}/packages"

HOST=""
PORT=""
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
  bind_host / port      config.json (127.0.0.1:8088 when unset)

--host and --port override config.json and are saved back to it.
Pass them only when you want to change the saved listen address.

Environment:
  OCTOP_HOME            User data directory (overridden by --home)
  OCTOP_BIND_HOST       Listen address for this process (not saved)
  OCTOP_PORT            Listen port for this process (not saved)
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
args=(run)
if [[ -n "$HOST" ]]; then
  args+=(--host "$HOST")
fi
if [[ -n "$PORT" ]]; then
  args+=(--port "$PORT")
fi
if [[ -n "$HOST" && -n "$PORT" ]]; then
  echo "[octop] http://${HOST}:${PORT}"
elif [[ -n "$HOST" ]]; then
  echo "[octop] host=${HOST} (port from config.json)"
elif [[ -n "$PORT" ]]; then
  echo "[octop] port=${PORT} (host from config.json)"
else
  echo "[octop] bind from config.json"
fi
if [[ ${#EXTRA[@]} -gt 0 ]]; then
  exec "$PY" "${ROOT}/launch.py" "${args[@]}" "${EXTRA[@]}"
else
  exec "$PY" "${ROOT}/launch.py" "${args[@]}"
fi
