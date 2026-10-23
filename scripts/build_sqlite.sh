#!/bin/bash
# =============================================================
# 编译新版 SQLite(libsqlite3.so.0),解决系统 SQLite < 3.35
# 缺窗口函数(ROW_NUMBER() OVER)/RETURNING 的问题(octop 迁移 SQL 依赖)。
#
# 两种用法:
#   1) 政务机现场兜底(源目录:~/ 下放 sqlite-amalgamation-3540100.zip):
#        bash build_sqlite.sh
#      产物:~/agentbuddy/sqlite3-new/libsqlite3.so.0,配合
#      LD_LIBRARY_PATH 或 install-offline.sh 的 wrapper 使用。
#   2) CI 预编译(在 manylinux2014 容器内,glibc 2.17 构建 → 2.23 可用):
#        SQLITE_OUT=<输出目录> SQLITE_SRC_ZIP=<zip 路径> bash build_sqlite.sh
#      产物:$SQLITE_OUT/libsqlite3.so.0(供 offline_bundle.sh 打包)。
# =============================================================
set -e

if [ -n "${SQLITE_OUT:-}" ] && [ -n "${SQLITE_SRC_ZIP:-}" ]; then
    MODE=ci
else
    MODE=host
fi

if [ "$MODE" = "ci" ]; then
    OUT_DIR="$SQLITE_OUT"
    SRC_ZIP="$SQLITE_SRC_ZIP"
    WORK_DIR="$(mktemp -d)"
else
    echo "==> 0. 检查 gcc"
    if ! command -v gcc >/dev/null 2>&1; then
        echo "错误：未找到 gcc。请先安装：apt install gcc 或 yum install gcc"; exit 1
    fi
    gcc --version | head -1
    OUT_DIR="$HOME/agentbuddy/sqlite3-new"
    SRC_ZIP="$HOME/sqlite-amalgamation-3540100.zip"
    WORK_DIR="$HOME"
fi

if [ ! -f "$SRC_ZIP" ]; then
    echo "错误：未找到 SQLite 源码包 $SRC_ZIP" >&2
    exit 1
fi
if ! command -v gcc >/dev/null 2>&1; then
    echo "错误：未找到 gcc" >&2
    exit 1
fi

echo "==> 1. 解压 SQLite 源码"
cd "$WORK_DIR"
unzip -oq "$SRC_ZIP"
SRC_DIR=$(find "$WORK_DIR" -maxdepth 1 -type d -name "sqlite-amalgamation-*" | head -1)
[ -n "$SRC_DIR" ] || { echo "错误：解压后未找到 sqlite-amalgamation-* 目录" >&2; exit 1; }

echo "==> 2. 编译 libsqlite3.so.0（约 1~2 分钟）"
cd "$SRC_DIR"
mkdir -p "$OUT_DIR"
gcc -O2 -fPIC -shared \
    -DSQLITE_ENABLE_FTS5 \
    -DSQLITE_ENABLE_RTREE \
    -DSQLITE_ENABLE_COLUMN_METADATA \
    -DSQLITE_ENABLE_MATH_FUNCTIONS \
    -DSQLITE_ENABLE_DBSTAT_VTAB \
    -DSQLITE_THREADSAFE=1 \
    sqlite3.c -o "$OUT_DIR/libsqlite3.so.0" \
    -Wl,-soname,libsqlite3.so.0 -lpthread -ldl -lm
ls -lh "$OUT_DIR/libsqlite3.so.0"

echo "==> 3. 验证版本切换"
if [ "$MODE" = "host" ]; then
    PY=${PYTHON:-python3.12}
    command -v "$PY" >/dev/null 2>&1 || PY=python3
    "$PY" -c "import sqlite3; print('默认（旧）SQLite:', sqlite3.sqlite_version)"
    export LD_LIBRARY_PATH="$OUT_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    "$PY" -c "
import sqlite3
v = sqlite3.sqlite_version
print('切换后 SQLite:', v)
assert v.startswith('3.54'), '新库未生效，请检查 LD_LIBRARY_PATH'
# 窗口函数验证（octop 迁移依赖的特性）
con = sqlite3.connect(':memory:')
con.execute('select row_number() over (order by 1) from (select 1) t').fetchall()
print('窗口函数 OVER 可用 ✓')
"
    echo "==> 完成。之后运行 octop 前保持："
    echo "    export LD_LIBRARY_PATH=$OUT_DIR\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
    echo "    (或重跑 scripts/install-offline.sh,它会自动把 venv 的 octop 入口包成 wrapper)"
else
    echo "==> CI 模式完成: $OUT_DIR/libsqlite3.so.0"
    file "$OUT_DIR/libsqlite3.so.0"
fi
