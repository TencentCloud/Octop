#!/usr/bin/env bash
# =============================================================================
# 政务伙伴离线安装包准备(在有网的构建机上跑)
#
# 产出:dist/offline/ 目录 = 全套 wheel(主包 + 四上游 + 全部第三方依赖,按目标
#       平台下载)+ 少量 sdist(个别无 wheel 的老包,如 crcmod)+ SHA256SUMS,
#       以及一个可拷入政务内网的 tar.gz。VARIANT=legacy 时另出兼容包(见下)。
#
# 用法(在仓库根目录):
#   bash scripts/offline_bundle.sh <platform>... [pytag]
#
#   <platform> 可以传多个(常见标签并集,覆盖新旧轮子):
#     鲲鹏/飞腾:  manylinux2014_aarch64 manylinux_2_17_aarch64 manylinux_2_26_aarch64 manylinux_2_28_aarch64
#     海光/兆芯:  manylinux2014_x86_64 manylinux_2_17_x86_64 manylinux_2_28_x86_64
#
#   变体(环境变量):
#     VARIANT=standard|legacy|both   默认 both:standard(四档标签,追新)+
#                                    legacy(仅 manylinux2014 档 + 兼容替换表,
#                                    适配银河麒麟 glibc 2.23 等 2014 基线老机)。
#     SQLITE_ARCHIVEDIR=<dir>        指向含 sqlite3/<arch>/libsqlite3.so.0 与
#                                    sqlite-amalgamation*.zip 的目录(由 CI 的
#                                    manylinux2014 容器步骤产出);存在时打进包。
#
#   示例:
#     bash scripts/offline_bundle.sh manylinux2014_aarch64 manylinux_2_17_aarch64 manylinux_2_26_aarch64 manylinux_2_28_aarch64 cp312
#     bash scripts/offline_bundle.sh manylinux2014_x86_64 manylinux_2_17_x86_64 manylinux_2_28_x86_64 cp312
#
# 要点(实测踩过的坑):
#   - pip --platform 是"精确标签匹配"不是"最低基线",必须把新旧标签都传上,
#     否则像 cffi(pip 找 cp312-manylinux2014)与 argon2(只有 manylinux_2_26)
#     会一个匹配一个不匹配;
#   - 但锁定树按"最新版"取 wheel:部分新版本(如 numpy 2.5.x / argon2-cffi-bindings
#     26.x)在 PyPI 上根本没有 2014 档 wheel,四档标签再多也救不了——这正是
#     legacy 变体存在的原因:替换表把这些包降到有 2014 档的版本;
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
    sed -n '2,40p' "$0" >&2
    exit 1
fi

# 最后一个参数若形如 cp3XX 则作为 PYTAG,其余为 platform 标签
ARGS=("$@")
PYTAG="cp312"
LAST=$(( ${#ARGS[@]} - 1 ))
if [[ "${ARGS[$LAST]}" =~ ^cp3[0-9]+$ ]]; then
    PYTAG="${ARGS[$LAST]}"
    unset "ARGS[$LAST]"
fi
PLATFORMS=("${ARGS[@]}")
MIRROR="${MIRROR:-https://pypi.org/simple}"
VARIANT="${VARIANT:-both}"
SQLITE_ARCHIVEDIR="${SQLITE_ARCHIVEDIR:-}"

# ---- legacy 兼容替换表 --------------------------------------------------------
# 背景:银河麒麟 ARM 定制机 glibc 2.23,只能装 manylinux2014(glibc 2.17 基线)档
# wheel;锁定树的下列包最新版只有 manylinux_2_24+ 档,pip 拒装。legacy 变体按本表
# 降级到有 2014 档的版本。首版组合参考 kylin-fix/麒麟部署修复说明.md 实测记录,
# 按当前锁定树重新核对。
#
# ⚠️ uv.lock 中下列包升级时需复核本表:确认新版是否已有 2014 档 wheel(有则可
# 移出表),以及替换版本与依赖约束是否仍兼容(pyproject 下限、上游 wheel 互相
# 依赖)。CI 闸门会在 legacy 包出现无 2014 档 wheel 时硬失败。
#
# 格式:包名(导入名不做归一)==精确版本
LEGACY_PINNED=(
    "numpy==2.2.6"                 # 2.5.x 无 2014 档;2.2.6 有
    "pillow==12.2.0"               # 12.3+ 无 2014 档
    "greenlet==3.2.5"              # 3.5.x 无 2014 档
    "tiktoken==0.11.0"             # 0.13+ 无 2014 档
    "argon2-cffi==23.1.0"          # 配套 bindings 21.2.0(官方组合),仍满足 octop >=23.1
    "argon2-cffi-bindings==21.2.0" # 26.x 无 2014 档
    # cryptography 不需要替换:lock 原版 49.0.0 的 cp39-abi3 轮自带 manylinux2014 双架构
    # (50.0.2 反而会与 pyopenssl 26.3.0 的 cryptography<50 冲突)
    "lxml==6.1.3"                  # 6.1.x 按构建批次不同部分无 2014 档;6.1.3 实测有
    "psycopg==3.2.13"              # 3.3.x aarch64 无 2014 档(amd64 有);3.2.13 双架构有
    "psycopg-binary==3.2.13"
    "psycopg-pool==3.2.6"          # 与 psycopg 3.2.x 配套
)

# legacy 从清单中**整包剔除**的依赖(不下载、不装):
#   deepagents-backends 0.x 所有版本硬性要求 psycopg>=3.3.2,与上表 psycopg 3.2.13
#   死锁;它只服务 remote COS/S3/Postgres 后端(harness extra 'remote-backends'),
#   SQLite 默认模式与 octop 自己的存储后端都不 import 它,剔除无影响。
#   langchain-aws(py>=3.12)硬性要求 numpy>=2.3.2,与上表 numpy 2.2.6 死锁(aarch64
#   2014 档天花板是 2.2.6);它只服务 bedrock 协议(extra 'bedrock'),factory 延迟
#   import 且 ImportError 给出安装指引,剔除仅影响 AWS Bedrock 接入。
LEGACY_EXCLUDE=(
    "deepagents-backends"
    "langchain-aws"
)

OUT="$REPO_ROOT/dist/offline"

# ---- 0) 准备 3.12 解释器(sdist 编译必须用目标 Python 版本;系统 python3 往往是 3.10) ----
PY312="$REPO_ROOT/.offline-py312"
uv python install 3.12 >/dev/null 2>&1 || true
# 已存在的 venv 直接复用(uv venv 对已存在目录会报错);损坏/缺失时重建
if ! "$PY312/bin/python" -V >/dev/null 2>&1; then
    rm -rf "$PY312"
    uv venv "$PY312" --python 3.12 >/dev/null 2>&1 || { echo "[offline_bundle] ERROR: 无法准备 Python 3.12(sdist 编译需要)" >&2; exit 1; }
fi
"$PY312/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true

# ---- 0.5) 前端构建 + 5 个主包 wheel(变体无关,只做一次) ----------------------
echo "[offline_bundle] Building dashboard frontend..."
(cd dashboard && npm ci && NODE_ENV=production NODE_OPTIONS="--max-old-space-size=2048" npm run build)

echo "[offline_bundle] Building 5 wheels (octop + harness/gateway/memory/browser)..."
WHEEL_CACHE="$REPO_ROOT/.offline-wheels"
rm -rf "$WHEEL_CACHE"
mkdir -p "$WHEEL_CACHE"
uv build --wheel --out-dir "$WHEEL_CACHE" .
for p in octop-harness octop-gateway octop-memory octop-browser; do
    (cd "packages/$p" && uv build --wheel --out-dir "$WHEEL_CACHE" .)
done
echo "[offline_bundle] Wheels built: $(ls "$WHEEL_CACHE" | wc -l)"
# 诊断:主 wheel 必须含 bundled 插件树(init 时 seed_bundled 依赖);缺失会在 init 炸
python3 - "$WHEEL_CACHE"/octop-*.whl <<'CHECK_BUNDLED'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
n = sum(1 for x in z.namelist() if x.startswith("octop/infra/agents/plugins/bundled/"))
print(f"[offline_bundle] bundled entries in main wheel: {n}")
if n < 10:
    print("::error::main wheel is missing bundled plugins tree — check hatch include globs")
    sys.exit(1)
CHECK_BUNDLED

build_variant() {
    local variant="$1"; shift
    local tags=("$@")
    local platform_args=()
    local out_dir name_suffix
    local -a req_args=()

    if [ "$variant" = "legacy" ]; then
        out_dir="$REPO_ROOT/dist/offline-legacy"
        name_suffix="legacy-${tags[0]}"
        # 仅 2014 档 + 替换表:标签列表由调用方保证只有 manylinux2014 档
        local req_file
        req_file=$(mktemp)
        for pin in "${LEGACY_PINNED[@]}"; do
            echo "$pin" >> "$req_file"
        done
        req_args=(-r "$req_file")
        echo "[offline_bundle] [legacy] override pins:"
        sed 's/^/[legacy]   /' "$req_file"
    else
        out_dir="$OUT"
        name_suffix="${tags[0]}"
    fi

    rm -rf "$out_dir"
    mkdir -p "$out_dir"
    cp "$WHEEL_CACHE"/*.whl "$out_dir/"

    local pyver="${PYTAG:2:1}.${PYTAG:3}"

    for p in "${tags[@]}"; do
        platform_args+=(--platform "$p")
    done

    # ---- 导出锁定树的第三方依赖清单 ------------------------------------------
    uv export --frozen --no-dev --no-hashes --no-emit-project \
        --no-emit-package octop-harness --no-emit-package octop-gateway \
        --no-emit-package octop-memory --no-emit-package octop-browser \
        --format requirements-txt -o "$out_dir/requirements-third-party.txt"
    # 过滤跨平台 marker 行:Windows-only(pywin32)、Python>3.13(audioop-lts)等
    # 在目标(cp312/linux)下不可装,pip download 又不吃 marker 会整体失败。
    python3 - "$out_dir/requirements-third-party.txt" <<'FILTER'
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

    # legacy:把替换表包从清单中剔除,替换版本由上面的 req_args 单独下载;
    # LEGACY_EXCLUDE 中的包整行剔除(见该表注释)。清单同步改写(闸门做
    # "清单 vs 实际 wheel"一致性比对时以改写后为准)。
    if [ "$variant" = "legacy" ]; then
        python3 - "$out_dir/requirements-third-party.txt" "${LEGACY_PINNED[@]}" -- "${LEGACY_EXCLUDE[@]}" <<'APPLY_OVERRIDES'
import re, sys
argv = sys.argv[1:]
req_path, rest = argv[0], argv[1:]
sep = rest.index("--")
overrides, excludes = rest[:sep], rest[sep + 1:]
pinned = {}
for o in overrides:
    name, ver = o.split("==", 1)
    pinned[name.lower().replace("_", "-")] = (name, ver)
excluded = {e.lower().replace("_", "-") for e in excludes}
out = []
dropped = []
for line in open(req_path).read().splitlines():
    if line.startswith("#") or not line.strip():
        out.append(line); continue
    m = re.match(r"^([A-Za-z0-9_.-]+)[=~<>!]", line)
    if not m:
        out.append(line); continue
    norm = m.group(1).lower().replace("_", "-")
    if norm in excluded:
        dropped.append(m.group(1))
        continue  # 连同其 "# via" 注释行一并跳过
    if norm in pinned:
        out.append(overrides[list(pinned).index(norm)])
    else:
        out.append(line)
# 剔除指向被删包的 "#   <name>" 注释行与孤立 "    # via" 块
final = []
for line in out:
    s = line.strip()
    if s.startswith("#") and any(f"#   {d}" in line or s == f"#   {d}" for d in dropped):
        continue
    if s == "# via":
        continue
    final.append(line)
open(req_path, "w").write("\n".join(final) + "\n")
print(f"legacy overrides applied; excluded: {sorted(dropped)}")
APPLY_OVERRIDES
    fi

    # ---- 下载依赖 wheel --------------------------------------------------------
    # 第一轮:--only-binary 整批下载。坑:pip 对清单里一个解析失败的包(如
    # sdist-only 的 crcmod)会中止**整批**,已解析成功的也不落盘——所以用
    # "剔除失败包重试"循环:每轮至少剔除一个坏包,直到整批成功或清单耗尽。
    # 被剔除的包进入第二轮单独处理(sdist-only → 构建机预编译)。
    echo "[offline_bundle] [$variant] Downloading wheels (binary only)..."
    "$PY312/bin/python" -m pip install --quiet --upgrade pip
    local req_download="$out_dir/requirements-third-party.txt"
    local round=1
    while [ -s "$req_download" ]; do
        echo "[offline_bundle] [$variant] download round $round: $(grep -c '==' "$req_download" || true) pkgs"
        if "$PY312/bin/python" -m pip download -q --dest "$out_dir" \
            "${platform_args[@]}" --python-version "$pyver" --implementation cp \
            --only-binary=:all: --index-url "$MIRROR" \
            -r "$req_download"; then
            : > "$req_download"
            break
        fi
        # 从报错提取解析失败的包,从清单剔除后重试。
        # 两种形态:"for X==ver"(清单直接条目)与 "for X (from HOST)"(清单条目
        # HOST 的传递依赖解析失败,如 cos-python-sdk-v5→crcmod)——后者剔除 HOST。
        local failed
        failed=$(python3 -c '
import re, sys
req = {m.group(1).lower().replace("_", "-") for m in re.finditer(r"^([A-Za-z0-9_.-]+)==", open(sys.argv[1]).read(), re.M)}

def extract(line):
    # 先剥掉 "(from versions: ...)" 尾巴,再分两步取:失败包名 + 可选宿主。
    line = re.sub(r" \(from versions: [^)]*\)", "", line)
    m = re.search(r"(?:found for|requirement) ([A-Za-z0-9_.-]+)", line)
    if not m:
        return None
    name = m.group(1).lower().replace("_", "-")
    h = re.search(r" \(from ([A-Za-z0-9_.-]+)\)", line)
    host = h.group(1).lower().replace("_", "-") if h else ""
    return name, host

bad, hosts = set(), set()
for line in sys.stdin:
    got = extract(line)
    if not got:
        continue
    name, host = got
    bad.add(name)
    if host:
        hosts.add(host)
# 剔除优先级:清单内的宿主(传递失败,剔除宿主后其 sdist 依赖不再进解析)>
# 清单内直接失败的包。宿主被剔除后由第二轮 --no-deps 单独预编译。
drop = (req & hosts) or (req & bad)
print(" ".join(sorted(drop)))
' "$req_download" < <("$PY312/bin/python" -m pip download --dest "$out_dir" \
            "${platform_args[@]}" --python-version "$pyver" --implementation cp \
            --only-binary=:all: --index-url "$MIRROR" \
            -r "$req_download" 2>&1 || true))
        if [ -z "$failed" ]; then
            echo "[offline_bundle] [$variant] ERROR: 下载失败但未识别出坏包(网络/镜像问题?),保留清单中止重试" >&2
            break
        fi
        echo "[offline_bundle] [$variant] 剔除解析失败包(进第二轮): $failed"
        # 被剔除包仍需进 bundle:记下它们的 `pkg==ver` 原条目,循环结束后单独补
        grep -E "^($(echo "$failed" | tr ' ' '|'))==" "$req_download" >> "$out_dir/.dropped.txt" || true
        python3 - "$req_download" $failed <<'DROP'
import re, sys
path, bad = sys.argv[1], {b.lower().replace("_", "-") for b in sys.argv[2:]}
out = [l for l in open(path).read().splitlines()
       if not (m := re.match(r"^([A-Za-z0-9_.-]+)==", l)) or m.group(1).lower().replace("_", "-") not in bad]
open(path, "w").write("\n".join(out) + "\n")
DROP
        round=$((round + 1))
        [ "$round" -gt 20 ] && { echo "[offline_bundle] [$variant] ERROR: 剔除重试超过 20 轮,中止" >&2; break; }
    done

    # ---- 1.5) 被剔除包补装 --------------------------------------------------------
    # 剔除只是把它们移出**依赖解析**(它们的传递依赖是解析失败根源,如 crcmod);
    # 包本体仍要进 bundle:带原版本 --no-deps 单独下载,有 wheel 直接下,没有的
    # 落入下面的第二轮预编译。
    if [ -f "$out_dir/.dropped.txt" ] && [ -s "$out_dir/.dropped.txt" ]; then
        echo "[offline_bundle] [$variant] 补装被剔除包(--no-deps 带版本): $(tr '\n' ' ' < "$out_dir/.dropped.txt")"
        "$PY312/bin/python" -m pip download -q --dest "$out_dir" \
            "${platform_args[@]}" --python-version "$pyver" --implementation cp \
            --only-binary=:all: --no-deps --index-url "$MIRROR" \
            -r "$out_dir/.dropped.txt" \
            || echo "[offline_bundle] [$variant] INFO: 被剔除包有 wheel 缺口,留待第二轮预编译"
    fi

    # ---- 第二轮:清单剩余包(sdist-only / 预编译)逐个带版本钉定处理 ------------
    # 坑(实测,mcp 2.x 事故根源):`pip wheel $pkg` 不带版本会装**最新版**,
    # 与锁定树漂移。必须逐包用清单里的 `pkg==ver` 原样传入,且 --platform/
    # --python-version 与第一轮一致,产出的 wheel 才是"锁定版本 × 目标平台"。
    # 候选 = 主清单剩余 + 被剔除包中仍未落盘的(.dropped.txt)。
    MISSING=$(python3 -c '
import re, sys, pathlib, glob
req = {m.group(1).lower().replace("_", "-"): m.group(0) for m in re.finditer(r"^([A-Za-z0-9_.-]+)==(\S+)", open(sys.argv[1]).read(), re.M)}
for extra in sys.argv[2:]:
    for m in re.finditer(r"^([A-Za-z0-9_.-]+)==(\S+)", open(extra).read(), re.M):
        req.setdefault(m.group(1).lower().replace("_", "-"), m.group(0))
have = {re.split(r"[-_]", pathlib.Path(f).name)[0].lower().replace("_", "-")
        for f in glob.glob("*.whl")}
missing = sorted(req[n] for n in req if n not in have)
print("\n".join(missing))
' "$req_download" "$out_dir/.dropped.txt" | grep -v '^$' || true)
    if [ -n "$MISSING" ]; then
        echo "[offline_bundle] [$variant] 第二轮:构建机按目标平台预编译 sdist-only 包:"
        echo "$MISSING" | sed 's/^/[round2]   /' | head -30
        # 编译环境选择:
        #   - legacy 变体的编译产物必须带 manylinux2014 标签才能在 glibc 2.17+ 机器安装。
        #     runner 本机编译产出的是 runner 平台标签(如 manylinux_2_39/macosx),闸门会拦。
        #     因此 legacy 优先在 manylinux2014 容器内编译(docker 可用且镜像已拉取时);
        #   - standard 变体无此约束(目标机 glibc 较新,runner 标签通常可用),本机编译。
        local container_image=""
        if [ "$variant" = "legacy" ] && command -v docker >/dev/null 2>&1; then
            case "${tags[0]}" in
                *_x86_64) container_image="quay.io/pypa/manylinux2014_x86_64" ;;
                *_aarch64) container_image="quay.io/pypa/manylinux2014_aarch64" ;;
            esac
            docker image inspect "$container_image" >/dev/null 2>&1 || container_image=""
        fi
        while IFS= read -r pkg_pin; do
            echo "[offline_bundle] [$variant] Building wheel for $pkg_pin (${tags[0]} / $PYTAG)..."
            if [ -n "$container_image" ]; then
                # 容器内:用镜像自带 cp312 解释器;产物落 out_dir(挂载为 /out)
                echo "[offline_bundle] [$variant] compiling in container: $container_image"
                docker run --rm -v "$out_dir:/out" -v "$REPO_ROOT:/src:ro" \
                    "$container_image" bash -c '
                        set -euo pipefail
                        PY=$(ls /opt/python/cp312*/bin/python 2>/dev/null | head -1)
                        [ -n "$PY" ] || PY=python3
                        "$PY" -m pip wheel -q --wheel-dir /out --no-deps \
                            --index-url '"$MIRROR"' '"$pkg_pin"'
                    ' \
                    || echo "[offline_bundle] [$variant] WARNING: $pkg_pin 容器内编译失败,回退本机(产物标签可能不兼容 legacy)"
            else
                [ "$variant" = "legacy" ] && echo "[offline_bundle] [$variant] WARNING: $pkg_pin 在构建机本机编译(非 manylinux2014 容器)——产物标签可能与 legacy 不兼容"
                "$PY312/bin/python" -m pip wheel -q --wheel-dir "$out_dir" --no-deps \
                    --index-url "$MIRROR" "$pkg_pin" \
                    || echo "[offline_bundle] [$variant] WARNING: $pkg_pin wheel 编译失败,回退下载 sdist(政务机需 gcc)"
            fi
        done <<< "$MISSING"
        # 兜底:仍缺的(编译失败)下载 sdist,**同样带版本钉定**
        STILL_MISSING=$(python3 -c '
import re, sys, pathlib, glob
req = {m.group(1).lower().replace("_", "-"): m.group(0) for m in re.finditer(r"^([A-Za-z0-9_.-]+)==(\S+)", open(sys.argv[1]).read(), re.M)}
for extra in sys.argv[2:]:
    for m in re.finditer(r"^([A-Za-z0-9_.-]+)==(\S+)", open(extra).read(), re.M):
        req.setdefault(m.group(1).lower().replace("_", "-"), m.group(0))
have = {re.split(r"[-_]", pathlib.Path(f).name)[0].lower().replace("_", "-")
        for f in list(glob.glob("*.whl")) + list(glob.glob("*.tar.gz"))}
missing = sorted(req[n] for n in req if n not in have)
print(" ".join(missing))
' "$req_download" "$out_dir/.dropped.txt")
        if [ -n "$STILL_MISSING" ]; then
            echo "[offline_bundle] [$variant] 预编译后仍缺(下载 sdist 兜底,政务机需 gcc): $STILL_MISSING"
            "$PY312/bin/python" -m pip download -q --dest "$out_dir" \
                --no-binary :none: --prefer-binary --no-deps \
                --index-url "$MIRROR" \
                $STILL_MISSING || echo "[offline_bundle] [$variant] WARNING: 部分 sdist 包下载失败(逐包检查)"
        fi
    fi

    # ---- SQLite 兼容产物(可选) -----------------------------------------------
    # SQLITE_ARCHIVEDIR 指向 sqlite3/<arch>/libsqlite3.so.0 + 源码 zip 时打进包,
    # install-offline.sh 在系统 SQLite < 3.35 的机器上启用(窗口函数需求)。
    if [ -n "$SQLITE_ARCHIVEDIR" ] && [ -d "$SQLITE_ARCHIVEDIR" ]; then
        mkdir -p "$out_dir/sqlite3"
        cp -R "$SQLITE_ARCHIVEDIR/sqlite3" "$out_dir/" 2>/dev/null || true
        cp "$SQLITE_ARCHIVEDIR"/sqlite-amalgamation*.zip "$out_dir/sqlite3/" 2>/dev/null || true
        cp "$REPO_ROOT/scripts/build_sqlite.sh" "$out_dir/sqlite3/" 2>/dev/null || true
        echo "[offline_bundle] [$variant] SQLite 兼容产物已打入: $(ls "$out_dir/sqlite3" 2>/dev/null | tr '\n' ' ')"
    fi
    rm -f "$out_dir/.dropped.txt"

    # ---- 打包 + 校验和 --------------------------------------------------------
    echo "[offline_bundle] [$variant] Packing + checksums..."
    local total
    total=$(ls "$out_dir"/*.whl "$out_dir"/*.tar.gz 2>/dev/null | wc -l)
    ( cd dist && tar -czf "agentbuddy-offline-$name_suffix-$PYTAG.tar.gz" "$(basename "$out_dir")/" )
    ( cd "$out_dir" && sha256sum ./*.whl ./*.tar.gz requirements-third-party.txt > "../SHA256SUMS-$variant.txt" 2>/dev/null \
      || sha256sum ./* > "../SHA256SUMS-$variant.txt" )
    echo "[offline_bundle] [$variant] Done: $total artifacts"
}

mkdir -p dist
case "$VARIANT" in
    standard) build_variant standard "${PLATFORMS[@]}" ;;
    legacy)
        # legacy 只认 2014 档标签(精确取 platform 参数中的 2014 那个;若用户
        # 传的是四档并集则过滤出 2014 档,否则报错——多档会重新混入新 glibc wheel)
        LEGACY_TAG=""
        for p in "${PLATFORMS[@]}"; do
            case "$p" in
                manylinux2014_*) LEGACY_TAG="$p" ;;
            esac
        done
        if [ -z "$LEGACY_TAG" ]; then
            echo "[offline_bundle] ERROR: VARIANT=legacy 需要传入 manylinux2014_{x86_64,aarch64} 标签" >&2
            exit 1
        fi
        build_variant legacy "$LEGACY_TAG"
        ;;
    both)
        LEGACY_TAG=""
        for p in "${PLATFORMS[@]}"; do
            case "$p" in
                manylinux2014_*) LEGACY_TAG="$p" ;;
            esac
        done
        if [ -z "$LEGACY_TAG" ]; then
            echo "[offline_bundle] ERROR: 未找到 manylinux2014_* 标签,legacy 变体无法构建(需传入该档)" >&2
            exit 1
        fi
        build_variant standard "${PLATFORMS[@]}"
        build_variant legacy "$LEGACY_TAG"
        ;;
    *) echo "[offline_bundle] ERROR: VARIANT 必须是 standard|legacy|both" >&2; exit 1 ;;
esac

echo "[offline_bundle] 拷入内网后在政务机上运行 scripts/install-offline.sh(见该脚本头注)。"
