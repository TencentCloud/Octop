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
SUPERVISED=0
EXTRA_ARGS=()
ORIGINAL_ARGS=("$@")

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) BUILD=0; shift ;;
    --no-sandbox) SANDBOX=0; shift ;;
    --supervised) SUPERVISED=1; shift ;;
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

# Hand the build and the launched app to the supervisor, which owns shutdown.
# This runs after option parsing so `--help` / bad flags never need a process
# table. The re-exec keeps the public shell PID as the signal recipient.
if ((!SUPERVISED)); then
  exec node "$SCRIPT_DIR/dev-process.mjs" bash "$SCRIPT_DIR/run-dev.sh" --supervised "${ORIGINAL_ARGS[@]}"
fi

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

# Replace the build shell so the supervisor owns the actual Electron PID.
# No background shell/watchdog: the supervisor waits for the entire observed
# tree, including Python's detached group, on signals and unexpected exits.
exec env OCTOP_PORTABLE_DIR="$DEV_RUNTIME" \
  OCTOP_DASHBOARD_DIR="$DASHBOARD_DIR" \
  "${launch[@]}"
