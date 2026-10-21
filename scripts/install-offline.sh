#!/usr/bin/env bash
# =============================================================================
# 政务伙伴离线安装(在政务内网机上跑,配套 offline_bundle.sh 的产物)
#
# 用法:
#   tar -xzf agentbuddy-offline-<platform>-<pytag>.tar.gz
#   bash offline/../scripts/install-offline.sh <解包目录>/offline/
#
#   也可以指定安装目录(默认 ~/.octop)与 Python:
#   OCTOP_HOME=/data/agentbuddy bash install-offline.sh ./offline/
#
# 行为:
#   1. 校验 SHA256SUMS(产物自带);
#   2. 建/复用 Python 3.12 venv(OCTOP_VENV 可覆盖);
#   3. 纯 --no-index 安装:主包 octop + 四上游(harness/gateway/memory/browser)
#      + 全部第三方依赖,全部来自本地 wheels,不出网;
#   4. octop init 初始化本地数据目录;
#   5. 打印启动命令(octop run)。
#
# 前提:政务机已有 Python 3.12+(系统 Python 或离线装的 Miniconda 均可)。
# =============================================================================
set -euo pipefail

BUNDLE_DIR="${1:?用法: install-offline.sh <offline 解包目录>}"
BUNDLE_DIR="$(cd "$BUNDLE_DIR" && pwd)"
OCTOP_HOME="${OCTOP_HOME:-$HOME/.octop}"
OCTOP_VENV="${OCTOP_VENV:-$OCTOP_HOME/venv}"

echo "[install-offline] bundle=$BUNDLE_DIR home=$OCTOP_HOME venv=$OCTOP_VENV"

# ---- 1) 校验和 ----------------------------------------------------------------
if [ -f "$BUNDLE_DIR/../SHA256SUMS.txt" ]; then
    echo "[install-offline] Verifying SHA256SUMS..."
    ( cd "$BUNDLE_DIR" && sha256sum -c ../SHA256SUMS.txt --quiet ) \
        || { echo "[install-offline] ERROR: checksum mismatch, 拒绝安装" >&2; exit 1; }
    echo "[install-offline] Checksums OK"
else
    echo "[install-offline] WARNING: 无 SHA256SUMS(产物不完整?),跳过校验继续"
fi

# ---- 2) Python 环境 ------------------------------------------------------------
PY=python3.12
command -v "$PY" >/dev/null 2>&1 || PY=python3
"$PY" -c 'import sys; assert sys.version_info >= (3, 12), "需要 Python 3.12+"' \
    || { echo "[install-offline] ERROR: 需要 Python 3.12+,当前 $($PY -V)" >&2; exit 1; }
echo "[install-offline] Using $($PY -V)"

mkdir -p "$OCTOP_HOME"
[ -d "$OCTOP_VENV" ] || "$PY" -m venv "$OCTOP_VENV"

# ---- 3) 编译工具链检测(少数 sdist-only 老包需要;政务镜像一般自带) ------------
if ! command -v gcc >/dev/null 2>&1 && ls "$BUNDLE_DIR"/*.tar.gz >/dev/null 2>&1; then
    echo "[install-offline] WARNING: 产物里有 sdist 包(如 crcmod)但本机无 gcc——"
    echo "                 安装会失败。先安装编译工具链(apt install build-essential python3-dev)"
    echo "                 或在构建机上按本机平台编译出 wheel 再拷入。"
fi

# ---- 4) 纯离线安装 --------------------------------------------------------------
echo "[install-offline] Installing (no network)..."
"$OCTOP_VENV/bin/python" -m pip install --quiet --upgrade pip \
    --no-index --find-links "$BUNDLE_DIR" pip || {
    # pip 自身可能不在 wheels 里;venv 自带 ensurepip 兜底
    "$OCTOP_VENV/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
}
"$OCTOP_VENV/bin/python" -m pip install --no-index --find-links "$BUNDLE_DIR" \
    octop \
    || { echo "[install-offline] ERROR: pip install failed(缺 wheel / 平台不匹配 / sdist 缺编译工具链?对照 SHA256SUMS)" >&2; exit 1; }
echo "[install-offline] Installed: $("$OCTOP_VENV/bin/octop" --version)"

# ---- 5) 初始化 ------------------------------------------------------------------
echo "[install-offline] Init local data dir..."
"$OCTOP_VENV/bin/octop" init || echo "[install-offline] (init 提示已存在,跳过)"

cat <<EOF

[install-offline] 完成。
  启动:  $OCTOP_VENV/bin/octop run
  数据:  $OCTOP_HOME
  首次打开 Web 控制台走设置向导(口令见 $OCTOP_HOME/octop-login.txt)。

EOF
