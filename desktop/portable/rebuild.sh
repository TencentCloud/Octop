#!/usr/bin/env bash
# Local one-shot: rebuild dashboard and the host-platform green zip.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [[ -f "${HOME}/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.nvm/nvm.sh"
  nvm use 24
fi

rm -rf src/octop/dashboard
rm -rf green/

make build-frontend
make -f desktop/portable/Makefile green
