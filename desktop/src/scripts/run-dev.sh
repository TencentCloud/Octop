#!/usr/bin/env bash
# Launch the Electron shell locally against repo source (no green zip needed).
#
# Usage:
#   bash scripts/run-dev.sh               build everything, then launch
#   bash scripts/run-dev.sh --no-build    launch the existing out/ bundle as-is
#   bash scripts/run-dev.sh --no-sandbox  drop the Chromium sandbox and the GPU
#                                         process (containers, CI, no-display
#                                         hosts — see "Why the flags" in README)
#   bash scripts/run-dev.sh -- <args>     extra args passed to the Electron binary
#
# Requires: `uv sync` in the repo, `npm install` in dashboard/, and
# `pnpm install` in desktop/src/ (pnpm via `corepack enable pnpm`).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHELL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SHELL_DIR/../.." && pwd)"
DEV_RUNTIME="$SHELL_DIR/.dev-runtime"
DASHBOARD_DIR="$REPO_ROOT/src/octop/dashboard"

BUILD=1
SANDBOX=1
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) BUILD=0; shift ;;
    --no-sandbox) SANDBOX=0; shift ;;
    -h | --help)
      sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    --)
      shift
      EXTRA_ARGS=("$@")
      break
      ;;
    *)
      echo "[dev] unknown option: $1 (try --help)" >&2
      exit 2
      ;;
  esac
done

if ((BUILD)); then
  if ! command -v pnpm >/dev/null 2>&1; then
    echo "[dev] pnpm not found. Enable it with: corepack enable pnpm" >&2
    exit 1
  fi

  bash "$SCRIPT_DIR/make-dev-runtime.sh" >/dev/null

  # Build the Dashboard into the Python static dir when it is absent *or stale*.
  # The shell serves that directory (OCTOP_DASHBOARD_DIR), so a bundle left over
  # from an earlier checkout silently hides Dashboard changes — the old window
  # chrome kept showing up next to the native one exactly that way.
  # The Dashboard is still npm-managed (its own package-lock.json).
  dashboard_stale() {
    local built="$DASHBOARD_DIR/index.html"
    [[ -f "$built" ]] || return 0
    [[ -n "$(find "$REPO_ROOT/dashboard/src" \
      "$REPO_ROOT/dashboard/index.html" \
      "$REPO_ROOT/dashboard/vite.config.ts" \
      -newer "$built" -print -quit 2>/dev/null)" ]]
  }

  if dashboard_stale; then
    echo "[dev] building dashboard…"
    ( cd "$REPO_ROOT/dashboard" && npm run build )
  fi

  # Build the Electron main/preload/renderer bundles.
  echo "[dev] building electron shell…"
  ( cd "$SHELL_DIR" && pnpm run build )
else
  # --no-build: fail with the fix instead of launching a stale/absent bundle
  # and letting the splash sit on "正在启动 Octop…" forever.
  if [[ ! -f "$SHELL_DIR/out/main/index.js" ]]; then
    echo "[dev] out/main/index.js missing — run 'pnpm build' first (or drop --no-build)" >&2
    exit 1
  fi
  if [[ ! -x "$DEV_RUNTIME/runtime/bin/python3" ]]; then
    echo "[dev] $DEV_RUNTIME missing — run 'pnpm dev:runtime' first (or drop --no-build)" >&2
    exit 1
  fi
  if [[ ! -f "$DASHBOARD_DIR/index.html" ]]; then
    echo "[dev] $DASHBOARD_DIR/index.html missing — run 'npm run build' in dashboard/ first" >&2
    exit 1
  fi
  # The shell reports this file's version as the product version (update
  # selection, portable zip name). A stale placeholder here shows up as a wrong
  # version in the update dialogs, so point at the fix instead of failing.
  dev_version="$(sed -nE 's/.*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$DEV_RUNTIME/version.json" 2>/dev/null | head -1)"
  if [[ -z "$dev_version" || "$dev_version" == "0.0.0-dev" ]]; then
    echo "[dev] warning: $DEV_RUNTIME/version.json has no real version — run 'pnpm dev:runtime'" >&2
  fi
fi

ELECTRON_BIN="$SHELL_DIR/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
if [[ ! -x "$ELECTRON_BIN" ]]; then
  ELECTRON_BIN="$SHELL_DIR/node_modules/electron/dist/electron"
fi

# Electron starts as plain `node` (no `app`, no `BrowserWindow`, no `protocol`)
# whenever ELECTRON_RUN_AS_NODE is set — some shells and CI images export it
# globally. Launching the app never wants it, so drop it for this command only.
unset ELECTRON_RUN_AS_NODE

launch=("$ELECTRON_BIN" "$SHELL_DIR")
if ((!SANDBOX)); then
  # Chromium's setuid sandbox cannot initialise in containers / restricted
  # sandboxes, and the GPU process usually dies with it. Dev host only — never
  # ship these switches in a packaged build.
  launch+=("--no-sandbox" "--disable-gpu")
fi
if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
  launch+=("${EXTRA_ARGS[@]}")
fi

echo "[dev] launching (port from OS, loopback only)…"

# Own the shutdown. Chromium puts the browser process in its own session, so
# Ctrl+C in this terminal can reach the script while missing Electron — and a
# signal that only kills the shell leaves the detached Python sidecar (§3.1)
# running with the app's database open. Forward the signal explicitly, with a
# hard bound so a hung app can never wedge the terminal again.
electron_pid=""
shutdown() {
  local code="${1:-0}"
  if [[ -n "$electron_pid" ]] && kill -0 "$electron_pid" 2>/dev/null; then
    echo "[dev] stopping the shell (and its Python sidecar)…" >&2
    # Electron handles SIGTERM by stopping Python first: allow its 5s grace
    # window, then stop being polite.
    ( sleep 8 && kill -KILL "$electron_pid" 2>/dev/null ) &
    local watchdog=$!
    kill -TERM "$electron_pid" 2>/dev/null || true
    wait "$electron_pid" 2>/dev/null || true
    kill "$watchdog" 2>/dev/null || true
  fi
  exit "$code"
}
trap 'shutdown 0' INT TERM HUP

env OCTOP_PORTABLE_DIR="$DEV_RUNTIME" \
  OCTOP_DASHBOARD_DIR="$DASHBOARD_DIR" \
  "${launch[@]}" &
electron_pid=$!

status=0
wait "$electron_pid" || status=$?
exit "$status"
