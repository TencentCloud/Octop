#!/usr/bin/env bash
# 飞牛应用中心比较 manifest version 时只保留开头的 x.y.z。
# 1.0.2b6 与 1.0.2b7 都会变成 1.0.2，商店判定「已安装相同或更高版本」。
# 这里把 PEP 440 编进 patch，只写进 FPK 的 manifest，不改 pyproject / 镜像标签：
#   1.0.2b8 → 1.0.208
#   1.0.2b10 → 1.0.210
#   1.0.2   → 1.0.300（高于 1.0.2 的全部 beta）
#   1.0.3b1 → 1.0.301
# 已装 1.0.2b6 的机器在商店侧被看成 1.0.2，因此能升到 1.0.208。
# beta 序号只接受 1–99。a / rc 没有对应槽位，遇到时直接失败，避免再打出无法比较的包。

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
