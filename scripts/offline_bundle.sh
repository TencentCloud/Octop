#!/usr/bin/env bash
# =============================================================================
# 政务伙伴离线安装包准备(在有网的构建机上跑)
#
# 产出:dist/offline/ 目录 = 全套 wheel(主包 + 四上游 + 全部第三方依赖,按目标
#       平台下载)+ 少量 sdist(个别无 wheel 的老包,如 crcmod)+ SHA256SUMS,
#       以及一个可拷入政务内网的 tar.gz。
#
# 用法(在仓库根目录):
#   bash scripts/offline_bundle.sh <platform>... [pytag]
#
#   <platform> 可以传多个(常见标签并集,覆盖新旧轮子):
#     鲲鹏/飞腾:  manylinux2014_aarch64 manylinux_2_17_aarch64 manylinux_2_26_aarch64 manylinux_2_28_aarch64
#     海光/兆芯:  manylinux2014_x86_64 manylinux_2_17_x86_64 manylinux_2_28_x86_64
#
#   示例:
#     bash scripts/offline_bundle.sh manylinux2014_aarch64 manylinux_2_17_aarch64 manylinux_2_26_aarch64 manylinux_2_28_aarch64 cp312
#     bash scripts/offline_bundle.sh manylinux2014_x86_64 manylinux_2_17_x86_64 manylinux_2_28_x86_64 cp312
#
# 要点(实测踩过的坑):
#   - pip --platform 是"精确标签匹配"不是"最低基线",必须把新旧标签都传上,
#     否则像 cffi(pip 找 cp312-manylinux2014)与 argon2(只有 manylinux_2_26)
#     会一个匹配一个不匹配;
#   - 少数老包只有 sdist(如 crcmod 1.7,oss2 的依赖):两轮下载——第一轮
#     --only-binary 齐轮子,第二轮对缺漏的放行 sdist(--no-binary :all: 不加,
#     用 --prefer-binary)。目标政务机需要 gcc/python3-dev 才能编 sdist(政务
#     镜像一般有;没有的话,把该包在构建机上按目标平台编译出 wheel 再拷入);
#   - 构建机网络对 pypi.org 不稳时:MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
#     (注意镜像同步有滞后,个别包可能拉不到锁定版本,脚本会提示)。
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ $# -lt 1 ]; then
    sed -n '2,30p' "$0" >&2
    exit 1
fi

# 最后一个参数若形如 cp3XX 则作为 PYTAG,其余为 platform 标签
ARGS=("$@")
PYTAG="cp312"
if [[ "${ARGS[-1]}" =~ ^cp3[0-9]+$ ]]; then
    PYTAG="${ARGS[-1]}"
    unset 'ARGS[-1]'
fi
PLATFORMS=("${ARGS[@]}")
MIRROR="${MIRROR:-https://pypi.org/simple}"
OUT="$REPO_ROOT/dist/offline"

# ---- 0) 准备 3.12 解释器(sdist 编译必须用目标 Python 版本;系统 python3 往往是 3.10) ----
PY312="$REPO_ROOT/.offline-py312"
uv python install 3.12 >/dev/null 2>&1 || true
uv venv "$PY312" --python 3.12 >/dev/null 2>&1 || { echo "[offline_bundle] ERROR: 无法准备 Python 3.12(sdist 编译需要)" >&2; exit 1; }
"$PY312/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true

echo "[offline_bundle] platforms=${PLATFORMS[*]} python=$PYTAG mirror=$MIRROR"
# pip 的 --python-version 只接受 x.y 形态(cp312 会报 invalid);crcmod 编译仍用 cp312 语义
PYVER="${PYTAG:2:1}.${PYTAG:3}"

PLATFORM_ARGS=()
for p in "${PLATFORMS[@]}"; do
    PLATFORM_ARGS+=(--platform "$p")
done

# ---- 1) 前端构建(主 wheel 内含 dashboard) -----------------------------------
echo "[offline_bundle] Building dashboard frontend..."
(cd dashboard && npm ci && NODE_ENV=production NODE_OPTIONS="--max-old-space-size=2048" npm run build)

# ---- 2) 构建 5 个 wheel(主包 + 四上游 workspace 包) ------------------------
echo "[offline_bundle] Building 5 wheels (octop + harness/gateway/memory/browser)..."
rm -rf "$OUT"
mkdir -p "$OUT"
uv build --wheel --out-dir "$OUT" .
for p in octop-harness octop-gateway octop-memory octop-browser; do
    (cd "packages/$p" && uv build --wheel --out-dir "$OUT" .)
done
echo "[offline_bundle] Wheels built: $(ls "$OUT" | wc -l)"

# ---- 3) 导出锁定树的第三方依赖清单 ------------------------------------------
uv export --frozen --no-dev --no-hashes --no-emit-project \
    --no-emit-package octop-harness --no-emit-package octop-gateway \
    --no-emit-package octop-memory --no-emit-package octop-browser \
    --format requirements-txt -o "$OUT/requirements-third-party.txt"
# 过滤跨平台 marker 行:Windows-only(pywin32)、Python>3.13(audioop-lts)等
# 在目标(cp312/linux)下不可装,pip download 又不吃 marker 会整体失败。
python3 - "$OUT/requirements-third-party.txt" <<'FILTER'
import re, sys
p = sys.argv[1]
lines = open(p).read().splitlines()
out = []
skip = False
for line in lines:
    if ";" in line:
        marker = line.split(";", 1)[1]
        if "win32" in marker or "sys_platform" in marker:
            continue
        m = re.search(r"python_full_version >= '3\.1[3-9]|3\.[2-9]\d", marker)
        if m:
            continue
    out.append(line)
open(p, "w").write("\n".join(out) + "\n")
print(f"filtered to {sum(1 for l in out if l and not l.startswith('#'))} lines")
FILTER

# ---- 4) 下载依赖 wheel(第一轮:只要二进制轮子) ------------------------------
echo "[offline_bundle] Downloading wheels (binary only)..."
python3 -m pip install --quiet --upgrade pip
if ! python3 -m pip download -q --dest "$OUT" \
    "${PLATFORM_ARGS[@]}" --python-version "$PYVER" --implementation cp \
    --only-binary=:all: --index-url "$MIRROR" \
    -r "$OUT/requirements-third-party.txt"; then
    echo "[offline_bundle] 第一轮(仅 wheel)有缺口——多为 sdist-only 老包或镜像滞后,进入第二轮"
fi

# ---- 5) 第二轮:对第一轮缺的包,先在构建机上按目标平台预编译成 wheel --------
# sdist-only 老包(实测锁定树里只有 crcmod 1.7,oss2 的 CRC64 依赖)没有现成
# wheel;在**构建机**上编译成目标平台 wheel,政务机零编译、不需要 gcc。
MISSING=$(python3 -c '
import re, sys
req = {m.group(1) for m in re.finditer(r"^([A-Za-z0-9_.-]+)==", open(sys.argv[1]).read(), re.M)}
import pathlib, glob
have = {re.split(r"[-_]", pathlib.Path(f).name)[0].lower().replace("_", "-")
        for f in glob.glob("*.whl")}
missing = sorted(n for n in req if n.lower().replace("_", "-") not in have)
print(" ".join(missing))
' "$OUT/requirements-third-party.txt")
if [ -n "$MISSING" ]; then
    echo "[offline_bundle] 第二轮:构建机按目标平台预编译 sdist-only 包: $MISSING"
    # 逐包编译:必须用 3.12 解释器(runner/构建机的系统 python3 往往是 3.10,
    # 编出的 ABI 不对);产物拷入内网后政务机不编译。
    for pkg in $MISSING; do
        echo "[offline_bundle] Building wheel for $pkg ($PLATFORMS[0] / $PYTAG)..."
        "$PY312/bin/python" -m pip wheel -q --wheel-dir "$OUT" --no-deps \
            --index-url "$MIRROR" "$pkg" \
            || echo "[offline_bundle] WARNING: $pkg wheel 编译失败,回退下载 sdist(政务机需 gcc)"
    done
    # 兜底:仍缺的(编译失败)下载 sdist,政务机有 gcc 时可现场编译
    STILL_MISSING=$(python3 -c '
import re, sys
req = {m.group(1) for m in re.finditer(r"^([A-Za-z0-9_.-]+)==", open(sys.argv[1]).read(), re.M)}
import pathlib, glob
have = {re.split(r"[-_]", pathlib.Path(f).name)[0].lower().replace("_", "-")
        for f in list(glob.glob("*.whl")) + list(glob.glob("*.tar.gz"))}
missing = sorted(n for n in req if n.lower().replace("_", "-") not in have)
print(" ".join(missing))
' "$OUT/requirements-third-party.txt")
    if [ -n "$STILL_MISSING" ]; then
        echo "[offline_bundle] 预编译后仍缺(下载 sdist 兜底,政务机需 gcc): $STILL_MISSING"
        python3 -m pip download -q --dest "$OUT" \
            --no-binary :none: --prefer-binary --no-deps \
            --python-version "$PYVER" --index-url "$MIRROR" \
            $STILL_MISSING || echo "[offline_bundle] WARNING: 部分 sdist 包下载失败(逐包检查)"
    fi
fi

# ---- 6) 打包 + 校验和 --------------------------------------------------------
echo "[offline_bundle] Packing + checksums..."
TOTAL=$(ls "$OUT"/*.whl "$OUT"/*.tar.gz 2>/dev/null | wc -l)
( cd dist && tar -czf "agentbuddy-offline-${PLATFORMS[0]}-$PYTAG.tar.gz" offline/ )
( cd "$OUT" && sha256sum ./*.whl ./*.tar.gz requirements-third-party.txt > ../SHA256SUMS.txt 2>/dev/null \
  || sha256sum ./* > ../SHA256SUMS.txt )
echo "[offline_bundle] Done: $TOTAL artifacts"
ls -la dist/agentbuddy-offline-*.tar.gz dist/SHA256SUMS.txt
echo "[offline_bundle] 拷入内网后在政务机上运行 scripts/install-offline.sh(见该脚本头注)。"
