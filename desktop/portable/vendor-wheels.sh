#!/usr/bin/env bash
# Prefetch wheels for OCTOP_GREEN_OFFLINE=1 packaging.
#
# Usage:
#   bash desktop/portable/vendor-wheels.sh              # host platform
#   bash desktop/portable/vendor-wheels.sh windows-amd64
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=desktop/portable/_common.sh
source "${REPO_ROOT}/desktop/portable/_common.sh"

require_uv

vendor_one() {
  local plat="$1"
  local pyplat wheel_dir req_file override_file
  pyplat="$(uv_platform "$plat")" || {
    echo "unknown platform: $plat" >&2
    exit 1
  }
  wheel_dir="${GREEN_WHEELS}/${plat}"
  mkdir -p "$wheel_dir" "$GREEN_ROOT"

  req_file="${GREEN_ROOT}/requirements-${plat}.txt"
  echo "[wheels] ${plat}: exporting frozen deps → ${req_file}" >&2
  uv export --frozen --no-dev --no-emit-project --no-hashes -o "$req_file" >/dev/null

  override_file="$(write_green_overrides "$plat" || true)"
  local extra=()
  if [[ -n "$override_file" ]]; then
    extra+=( --overrides "$override_file" )
  fi

  echo "[wheels] ${plat}: downloading → ${wheel_dir}" >&2
  uv pip download \
    --dest "$wheel_dir" \
    --python-platform "$pyplat" \
    --python-version 3.12 \
    --only-binary cryptography \
    "${extra[@]}" \
    -r "$req_file"

  echo "[wheels] ${plat}: done ($(find "$wheel_dir" -maxdepth 1 -type f -name '*.whl' | wc -l | tr -d ' ') wheels)"
}

main() {
  local plat="${1:-}"
  if [[ -z "$plat" ]]; then
    plat="$(host_plat)"
  fi
  if ! is_known_plat "$plat"; then
    echo "unknown platform: $plat (known: ${ALL_PLATS[*]})" >&2
    exit 1
  fi
  vendor_one "$plat"
}

main "${1:-}"
