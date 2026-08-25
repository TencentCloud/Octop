#!/usr/bin/env bash
# =============================================================================
# 构建 Octop 飞牛 FnOS 安装包 (.fpk)
#
# 直接使用官方 fnpack CLI 打包（fnpack 在生成 .fpk 前会校验 manifest / cmd /
# config / wizard / app 等结构，确保产物与飞牛 fnOS 安装校验完全一致）。
#
# 用法（在仓库根目录执行):
#   bash scripts/build-fpk.sh docker      # 构建 Docker 版  -> dist/octop-<ver>.fpk
#   bash scripts/build-fpk.sh native      # 构建本地版(非Docker) -> dist/octop-native-<ver>.fpk
#   bash scripts/build-fpk.sh             # 两个都构建
#
# 环境变量：
#   FPK_NAME_PREFIX  输出文件名前缀，默认 "octop"
#                    例如 FPK_NAME_PREFIX=Fnos-octop 会生成 Fnos-octop-<ver>.fpk
#   FPK_ITER         迭代号，默认空
#                    例如 FPK_ITER=01 会生成 ...-<ver>-01.fpk
#
# 说明：
#   - Linux CI 下会自动下载 fnpack-1.2.3-linux-amd64；
#   - 本地若已存在 .verify/fnpack(.exe) 则直接复用，不再联网下载。
#   - 版本号同时来自仓库根 pyproject.toml，并注入到 manifest 的 version 字段
#     （manifest 采用 key=value 无空格格式，故用 `^version=` 匹配）。
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist"

# 使用仓库内的临时目录，避免 Windows 风格 TMPDIR 在 Git Bash 下被错误解析
TMP="$(mktemp -d "$ROOT/.buildtmp.XXXXXX")"
cleanup() { rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT

VER="$(grep -m1 '^version' "$ROOT/pyproject.toml" | sed -E 's/.*"([0-9][0-9.]*[0-9])".*/\1/')"
[ -n "$VER" ] || { echo "无法从 pyproject.toml 解析版本"; exit 1; }
echo "[build-fpk] Octop 版本: $VER"

# 输出文件名前缀与迭代号（由 CI 传入，实现 Fnos-octop-0.9.16-01.fpk 风格）
PREFIX="${FPK_NAME_PREFIX:-octop}"
ITER_SUFFIX=""
if [ -n "${FPK_ITER:-}" ]; then
  ITER_SUFFIX="-$FPK_ITER"
fi
echo "[build-fpk] 包名前缀: $PREFIX, 迭代后缀: ${ITER_SUFFIX:-<none>}"

# --- 获取 fnpack CLI ---
FNPACK=""
if [ -x "$ROOT/.verify/fnpack.exe" ]; then
  FNPACK="$ROOT/.verify/fnpack.exe"
elif [ -x "$ROOT/.verify/fnpack" ]; then
  FNPACK="$ROOT/.verify/fnpack"
else
  OS="$(uname -s)"
  case "$OS" in
    Linux)  FNPACK_URL="https://static2.fnnas.com/fnpack/fnpack-1.2.3-linux-amd64" ;;
    Darwin) FNPACK_URL="https://static2.fnnas.com/fnpack/fnpack-1.2.3-darwin-amd64" ;;
    *)      FNPACK_URL="https://static2.fnnas.com/fnpack/fnpack-1.2.3-windows-amd64" ;;
  esac
  FNPACK="$TMP/fnpack"
  echo "[build-fpk] 下载 fnpack: $FNPACK_URL"
  curl -fsSL -o "$FNPACK" "$FNPACK_URL"
  chmod +x "$FNPACK"
fi
echo "[build-fpk] 使用 fnpack: $FNPACK"

mkdir -p "$OUT"

build_one() {
  local KIND="$1" PKG OUTNAME
  case "$KIND" in
    docker)
      PKG="$ROOT/fnos"
      OUTNAME="${PREFIX}-${VER}${ITER_SUFFIX}.fpk"
      ;;
    native)
      PKG="$ROOT/fnos-native"
      OUTNAME="${PREFIX}-native-${VER}${ITER_SUFFIX}.fpk"
      ;;
    *) echo "未知类型: $KIND"; return 1 ;;
  esac

  local BUILD="$TMP/$KIND"
  rm -rf "$BUILD"; mkdir -p "$BUILD"

  # 复制整个包目录（manifest / cmd / config / wizard / app / ICON* / LICENSE）
  cp -r "$PKG/." "$BUILD/"

  # 注入版本号到 manifest（manifest 为 key=value 无空格格式）
  sed -i.bak "s/^version=.*/version=$VER/" "$BUILD/manifest" && rm -f "$BUILD/manifest.bak"

  echo "[build-fpk] fnpack 校验并打包 $KIND ..."
  # fnpack 校验 manifest/cmd/config/wizard/app 后在当前目录生成 <appname>.fpk
  # Windows 版 fnpack.exe 无法解析 Git-Bash 的 /c/... 路径，需转换为 Windows 原生路径。
  local DIR="$BUILD"
  case "$FNPACK" in
    *.exe) DIR="$(cygpath -w -m "$BUILD")" ;;
  esac
  ( cd "$BUILD" && "$FNPACK" build --directory "$DIR" )

  local SRC
  SRC="$(ls "$BUILD"/*.fpk 2>/dev/null | head -1)"
  [ -n "$SRC" ] || { echo "[build-fpk] 未找到 fnpack 产物"; return 1; }

  mv "$SRC" "$OUT/$OUTNAME"
  echo "[build-fpk] 产物: $OUT/$OUTNAME ($(stat -c%s "$OUT/$OUTNAME") bytes)"
  echo "[build-fpk] 外层内容:"
  tar -tzf "$OUT/$OUTNAME"
}

if [ $# -eq 0 ]; then
  build_one docker
  build_one native
else
  for k in "$@"; do build_one "$k"; done
fi
