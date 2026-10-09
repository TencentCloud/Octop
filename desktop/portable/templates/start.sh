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

HOST="127.0.0.1"
PORT="8088"
HOST_SET=""
PORT_SET=""
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
      HOST_SET=1
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || { echo "start.sh: --port requires a value" >&2; exit 1; }
      PORT="$2"
      PORT_SET=1
      shift 2
      ;;
    -h|--help)
      cat <<EOF
Octop green portable launcher

Usage: ./start.sh [--home DIR] [--host HOST] [--port PORT] [octop run args...]

Defaults:
  OCTOP_HOME / --home   ${ROOT}/data
  --host / --port       config.json (fresh install: 127.0.0.1:8088)
                        --host/--port are only saved to config.json when passed

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

# Only forward --host/--port the user passed explicitly: `octop run` persists
# CLI overrides into config.json, so unconditionally passing the launcher
# defaults rewrote hand-edited bind settings on every start (issue #1816).
BIND_ARGS=()
if [[ -n "$HOST_SET" ]]; then
  BIND_ARGS+=(--host "$HOST")
fi
if [[ -n "$PORT_SET" ]]; then
  BIND_ARGS+=(--port "$PORT")
fi

echo "[octop] home=${OCTOP_HOME}"
if [[ -n "$HOST_SET" && -n "$PORT_SET" ]]; then
  echo "[octop] http://${HOST}:${PORT}"
elif [[ -n "$HOST_SET" ]]; then
  echo "[octop] host ${HOST} from --host, port from config.json"
elif [[ -n "$PORT_SET" ]]; then
  echo "[octop] http://127.0.0.1:${PORT} - host from config.json"
else
  echo "[octop] bind host/port come from config.json"
fi
# Guarded expansions keep the optional argv empty-safe under bash 3.2 + set -u.
exec "$PY" "${ROOT}/launch.py" run ${BIND_ARGS[@]+"${BIND_ARGS[@]}"} ${EXTRA[@]+"${EXTRA[@]}"}
