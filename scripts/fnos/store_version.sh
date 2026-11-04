#!/usr/bin/env bash
# 飞牛商店版本映射。规则见 fnos/README.md「版本号映射」。
#   1.0.2b8 → 1.0.208
#   1.0.2   → 1.0.300

fnos_store_version() {
  local ver="${1:-}"
  local major minor patch num store_patch
  if [[ "$ver" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)b([0-9]+)$ ]]; then
    major="${BASH_REMATCH[1]}"
    minor="${BASH_REMATCH[2]}"
    patch="${BASH_REMATCH[3]}"
    num=$((10#${BASH_REMATCH[4]}))
    if [ "$num" -lt 1 ] || [ "$num" -gt 99 ]; then
      echo "飞牛商店版本无法编码 beta 序号: $ver" >&2
      return 1
    fi
    store_patch=$((patch * 100 + num))
  elif [[ "$ver" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    major="${BASH_REMATCH[1]}"
    minor="${BASH_REMATCH[2]}"
    patch="${BASH_REMATCH[3]}"
    store_patch=$((patch * 100 + 100))
  else
    echo "飞牛商店版本只接受 X.Y.Z 或 X.Y.ZbN，收到: $ver" >&2
    return 1
  fi
  printf '%s\n' "${major}.${minor}.${store_patch}"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  fnos_store_version "${1:-}"
fi
