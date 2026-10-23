#!/usr/bin/env bash
# =============================================================================
# 政务伙伴离线安装(在政务内网机上跑,配套 offline_bundle.sh 的产物)
#
# 用法:
#   tar -xzf agentbuddy-offline-<platform>-<pytag>.tar.gz
#   bash offline/../scripts/install-offline.sh <解包目录>/offline/
#
#   也可以指定安装目录(默认 ~/.agentbuddy)与 Python:
#   AGENTBUDDY_HOME=/data/agentbuddy bash install-offline.sh ./offline/
#
# 行为:
#   1. 校验 SHA256SUMS(产物自带);
#   2. glibc 预检:本机 glibc 低于包内 wheel 最高基线时硬失败,指路 legacy 包
#      (银河麒麟 glibc 2.23 等老机器请用 agentbuddy-offline-legacy-*);
#   3. 建/复用 Python 3.12 venv(AGENTBUDDY_VENV 可覆盖);
#   4. 纯 --no-index 安装:主包 octop + 四上游(harness/gateway/memory/browser)
#      + 全部第三方依赖,全部来自本地 wheels,不出网;
#   5. SQLite 兼容:系统 SQLite < 3.35(octop 迁移 SQL 需要窗口函数/RETURNING)
#      且包内带预编译 libsqlite3.so.0 时,装到 $AGENTBUDDY_HOME/sqlite3-new/
#      并把 venv 的 octop 入口包成 wrapper 注入 LD_LIBRARY_PATH——前台 octop run
#      与 systemd(ExecStart 指向同一 bin)统一生效,产品代码零改动;
#   6. octop init 初始化本地数据目录;
#   7. 打印启动命令(octop run)。
#
# 前提:政务机已有 Python 3.12+(系统 Python 或离线装的 Miniconda 均可)。
# =============================================================================
set -euo pipefail

BUNDLE_DIR="${1:?用法: install-offline.sh <offline 解包目录>}"
BUNDLE_DIR="$(cd "$BUNDLE_DIR" && pwd)"
AGENTBUDDY_HOME="${AGENTBUDDY_HOME:-$HOME/.agentbuddy}"
AGENTBUDDY_VENV="${AGENTBUDDY_VENV:-$AGENTBUDDY_HOME/venv}"

echo "[install-offline] bundle=$BUNDLE_DIR home=$AGENTBUDDY_HOME venv=$AGENTBUDDY_VENV"

# ---- 1) 校验和 ----------------------------------------------------------------
# 校验和文件带变体后缀(SHA256SUMS-standard.txt / SHA256SUMS-legacy.txt),
# 兼容旧产物名 SHA256SUMS.txt。
SUMS_FILE=""
if [ -f "$BUNDLE_DIR/../SHA256SUMS-standard.txt" ]; then
    SUMS_FILE="../SHA256SUMS-standard.txt"
fi
if [ -f "$BUNDLE_DIR/../SHA256SUMS-legacy.txt" ] && [[ "$(basename "$BUNDLE_DIR")" == offline-legacy ]]; then
    SUMS_FILE="../SHA256SUMS-legacy.txt"
fi
if [ -z "$SUMS_FILE" ] && [ -f "$BUNDLE_DIR/../SHA256SUMS.txt" ]; then
    SUMS_FILE="../SHA256SUMS.txt"
fi
if [ -n "$SUMS_FILE" ]; then
    echo "[install-offline] Verifying SHA256SUMS..."
    ( cd "$BUNDLE_DIR" && sha256sum -c "$SUMS_FILE" --quiet ) \
        || { echo "[install-offline] ERROR: checksum mismatch, 拒绝安装" >&2; exit 1; }
    echo "[install-offline] Checksums OK"
else
    echo "[install-offline] WARNING: 无 SHA256SUMS(产物不完整?),跳过校验继续"
fi

# ---- 2) glibc 预检 ----------------------------------------------------------------
# 包内 wheel 的最高 glibc 基线决定了本机可装的门槛(manylinux_2_26 → glibc 2.26)。
# pip 报 "not a supported wheel" 前先在这里拦截,现场少走一步。
HOST_GLIBC="$(ldd --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+$' | head -1 || true)"
if [ -n "$HOST_GLIBC" ]; then
    MAX_BASELINE=$(python3 - <<'PY'
import glob, re
best = (0, 0)
for whl in glob.glob("*.whl"):
    parts = whl.split("-")
    if len(parts) < 5:
        continue
    for tag in parts[-1].split("."):
        m = re.match(r"manylinux_(\d+)_(\d+)", tag)
        if m:
            v = (int(m.group(1)), int(m.group(2)))
            if v > best:
                best = v
print("%d.%d" % best if best != (0, 0) else "")
PY
)
    if [ -n "$MAX_BASELINE" ]; then
        LOWEST=$(( $(echo "$HOST_GLIBC" | cut -d. -f1) * 100 + $(echo "$HOST_GLIBC" | cut -d. -f2) ))
        HIGHEST=$(( $(echo "$MAX_BASELINE" | cut -d. -f1) * 100 + $(echo "$MAX_BASELINE" | cut -d. -f2) ))
        if [ "$LOWEST" -lt "$HIGHEST" ]; then
            echo "[install-offline] ERROR: 本机 glibc $HOST_GLIBC 低于包内 wheel 基线 $MAX_BASELINE," >&2
            echo "                 pip 安装必然失败。请改用 legacy 兼容包:" >&2
            echo "                 agentbuddy-offline-legacy-<platform>-*.tar.gz(2014/glibc 2.17 基线," >&2
            echo "                 见 docs/kylin-legacy-deploy.md)" >&2
            exit 1
        fi
        echo "[install-offline] glibc check OK (host=$HOST_GLIBC >= bundle baseline=$MAX_BASELINE)"
    fi
else
    echo "[install-offline] WARNING: 无法读取本机 glibc 版本(ldd --version 失败),跳过预检"
fi

# ---- 3) Python 环境 ------------------------------------------------------------
PY=python3.12
command -v "$PY" >/dev/null 2>&1 || PY=python3
"$PY" -c 'import sys; assert sys.version_info >= (3, 12), "需要 Python 3.12+"' \
    || { echo "[install-offline] ERROR: 需要 Python 3.12+,当前 $($PY -V)" >&2; exit 1; }
echo "[install-offline] Using $($PY -V)"

mkdir -p "$AGENTBUDDY_HOME"
[ -d "$AGENTBUDDY_VENV" ] || "$PY" -m venv "$AGENTBUDDY_VENV"

# ---- 4) 编译工具链检测(少数 sdist-only 老包需要;政务镜像一般自带) ------------
if ! command -v gcc >/dev/null 2>&1 && ls "$BUNDLE_DIR"/*.tar.gz >/dev/null 2>&1; then
    echo "[install-offline] WARNING: 产物里有 sdist 包(如 crcmod)但本机无 gcc——"
    echo "                 安装会失败。先安装编译工具链(apt install build-essential python3-dev)"
    echo "                 或在构建机上按本机平台编译出 wheel 再拷入。"
fi

# ---- 5) 纯离线安装 --------------------------------------------------------------
# --no-deps 全量装 bundle 内所有 wheel(kylin-fix 实战验证的模式):不做依赖解析——
# 主包 extras(harness[all] 的 deepagents-backends/langchain-aws 等)在 legacy 包被
# 剔除,带解析会失败;wheel 集合源自同一 uv.lock + 闸门保证与清单一致,自洽。
echo "[install-offline] Installing (no network, no-deps full set)..."
"$AGENTBUDDY_VENV/bin/python" -m pip install --quiet --upgrade pip \
    --no-index --find-links "$BUNDLE_DIR" pip || {
    # pip 自身可能不在 wheels 里;venv 自带 ensurepip 兜底
    "$AGENTBUDDY_VENV/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
}
"$AGENTBUDDY_VENV/bin/python" -m pip install --no-index --no-deps \
    "$BUNDLE_DIR"/*.whl \
    || { echo "[install-offline] ERROR: pip install failed(缺 wheel / 平台不匹配?对照 SHA256SUMS)" >&2; exit 1; }
echo "[install-offline] Installed: $("$AGENTBUDDY_VENV/bin/octop" --version)"

# ---- 6) SQLite 兼容(系统 SQLite < 3.35 时启用预编译 .so) ------------------------
# octop 迁移 SQL 用了窗口函数(ROW_NUMBER() OVER)与 RETURNING,需要 SQLite >= 3.35。
# 包内 sqlite3/<arch>/libsqlite3.so.0 由 CI 在 manylinux2014 容器预编译(glibc 2.17
# 构建 → 2.23 可用);本机没有 .so 时提示用源码兜底编译(sqlite3/build_sqlite.sh)。
SYS_SQLITE=$("$AGENTBUDDY_VENV/bin/python" -c "import sqlite3; print(sqlite3.sqlite_version)" 2>/dev/null || echo "0")
ARCH="$(uname -m)"
SO_SRC="$BUNDLE_DIR/sqlite3/$ARCH/libsqlite3.so.0"
SQLITE_NEEDS_FIX=0
if [ "$(python3 -c "print(1 if tuple(int(x) for x in '$SYS_SQLITE'.split('.')[:3]) < (3,35,0) else 0)")" = "1" ]; then
    SQLITE_NEEDS_FIX=1
fi
if [ "$SQLITE_NEEDS_FIX" = "1" ]; then
    echo "[install-offline] 系统 SQLite $SYS_SQLITE < 3.35(缺窗口函数),启用包内兼容库"
    if [ -f "$SO_SRC" ]; then
        SQLITEREF_DIR="$AGENTBUDDY_HOME/sqlite3-new"
        mkdir -p "$SQLITEREF_DIR"
        cp "$SO_SRC" "$SQLITEREF_DIR/libsqlite3.so.0"
        OCTOP_BIN="$AGENTBUDDY_VENV/bin/octop"
        if [ ! -f "$OCTOP_BIN.real" ]; then
            mv "$OCTOP_BIN" "$OCTOP_BIN.real"
        fi
        cat > "$OCTOP_BIN" <<WRAPPER
#!/bin/sh
LD_LIBRARY_PATH="$SQLITEREF_DIR\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}" exec "$OCTOP_BIN.real" "\$@"
WRAPPER
        chmod +x "$OCTOP_BIN"
        echo "[install-offline] SQLite 兼容库已启用: $SQLITEREF_DIR (venv octop 入口已包 wrapper)"
        echo "[install-offline] 验证: $($OCTOP_BIN --version)"
    else
        echo "[install-offline] WARNING: 包内没有本架构($ARCH)的 libsqlite3.so.0——"
        echo "                 octop init 会因 SQLite 过老而失败(near \"OVER\": syntax error)。"
        echo "                 兜底:用包内 sqlite3/sqlite-amalgamation*.zip + build_sqlite.sh 现场编译"
        echo "                 (需要 gcc),编译产物放到 $AGENTBUDDY_HOME/sqlite3-new/,再重跑本脚本。"
    fi
fi

# ---- 7) 初始化 ------------------------------------------------------------------
echo "[install-offline] Init local data dir..."
"$AGENTBUDDY_VENV/bin/octop" init --yes || echo "[install-offline] (init 提示已存在,跳过)"

cat <<EOF

[install-offline] 完成。
  启动:  $AGENTBUDDY_VENV/bin/octop run
  数据:  $AGENTBUDDY_HOME
  首次打开 Web 控制台走设置向导(口令见 $AGENTBUDDY_HOME/octop-login.txt)。
EOF
if [ "$SQLITE_NEEDS_FIX" = "1" ] && [ -f "$AGENTBUDDY_HOME/sqlite3-new/libsqlite3.so.0" ]; then
    cat <<EOF
  SQLite 兼容库已注入 venv octop 入口,systemd 与前台共用,无需额外配置。
EOF
fi
echo ""
