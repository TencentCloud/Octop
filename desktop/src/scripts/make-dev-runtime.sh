#!/usr/bin/env bash
# Build a local dev "portable runtime" that reuses the repo's uv venv, so you can
# launch the Electron shell without shipping a green zip. The shell still spawns
# `<dir>/runtime/bin/python3 <dir>/launch.py run`, matching the packaged contract.
#
# Usage:  bash desktop/src/scripts/make-dev-runtime.sh
#         (prints the two env vars to export)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHELL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SHELL_DIR/../.." && pwd)"
VENV="$REPO_ROOT/.venv"
DEV="$SHELL_DIR/.dev-runtime"

if [[ ! -x "$VENV/bin/python3" ]]; then
  echo "missing $VENV/bin/python3 — run 'uv sync' in $REPO_ROOT first" >&2
  exit 1
fi

rm -rf "$DEV"
mkdir -p "$DEV/runtime/bin" "$DEV/packages"

# Wrapper (not a symlink) so CPython resolves sys.prefix to the real venv.
cat > "$DEV/runtime/bin/python3" <<PY
#!/bin/sh
exec "$VENV/bin/python3" "\$@"
PY
chmod +x "$DEV/runtime/bin/python3"

# launch.py requires packages/ to exist; an empty dir is fine because the venv
# already has octop installed.
cp "$REPO_ROOT/desktop/portable/templates/launch.py" "$DEV/launch.py"

# Same source of truth as CI: the shell, the Dashboard and the runtime ship as one
# release, so the dev runtime must report the real product version. The shell reads
# this for update release selection and for the expected portable zip name, so a
# placeholder here makes every release look newer than the running install.
APP_VERSION="$(sed -nE 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' "$REPO_ROOT/pyproject.toml" | head -1)"
if [[ -z "$APP_VERSION" ]]; then
  echo "[dev] cannot read version from $REPO_ROOT/pyproject.toml, using 0.0.0-dev" >&2
  APP_VERSION="0.0.0-dev"
fi
printf '{ "version": "%s" }\n' "$APP_VERSION" > "$DEV/version.json"

echo "dev runtime ready: $DEV"
echo "export OCTOP_PORTABLE_DIR=\"$DEV\""
echo "export OCTOP_DASHBOARD_DIR=\"$REPO_ROOT/src/octop/dashboard\""
