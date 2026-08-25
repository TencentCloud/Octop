#!/usr/bin/env bash
# Cross-build a Linux green zip inside Docker (native ABI for C extensions).
#
# Usage:
#   bash scripts/green/package-linux-docker.sh
#   bash scripts/green/package-linux-docker.sh linux-arm64
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=scripts/green/_common.sh
source "${REPO_ROOT}/scripts/green/_common.sh"

PLAT="${1:-linux-amd64}"
case "$PLAT" in
  linux-amd64|linux-arm64) ;;
  *)
    echo "package-linux-docker.sh: expected linux-amd64 or linux-arm64, got ${PLAT}" >&2
    exit 1
    ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for Linux cross-builds" >&2
  exit 1
fi

IMAGE="${GREEN_LINUX_IMAGE:-python:3.12-bookworm}"
echo "[docker] image=${IMAGE} plat=${PLAT}" >&2

docker run --rm \
  -e GREEN_HOST_PLAT="$PLAT" \
  -e PBS_TAG="$PBS_TAG" \
  -e PBS_PY="$PBS_PY" \
  -e PBS_BASE_URL="${PBS_BASE_URL}" \
  -e OCTOP_GREEN_OFFLINE="${OCTOP_GREEN_OFFLINE:-0}" \
  -v "${REPO_ROOT}:/src" \
  -w /src \
  "$IMAGE" \
  bash -lc "
    set -euo pipefail
    apt-get update -qq
    apt-get install -y -qq curl zip ca-certificates >/dev/null
    if ! command -v uv >/dev/null 2>&1; then
      curl -LsSf https://astral.sh/uv/install.sh | sh
      export PATH=\"\$HOME/.local/bin:\$PATH\"
    fi
    bash scripts/green/bootstrap-runtime.sh '${PLAT}'
    bash scripts/green/package.sh '${PLAT}'
  "
