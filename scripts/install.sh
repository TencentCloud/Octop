#!/usr/bin/env bash
# Octop 安装脚本 (macOS / Linux)
# 用法: bash scripts/install.sh              # 从 PyPI 安装（默认）
#   或: bash scripts/install.sh --from-source  # 从本地源码安装
#   或: curl -fsSL <url>/install.sh | bash   # 远程安装
#
# 将 Octop 安装到 ~/.octop，使用 uv 管理 Python 环境。
# 用户无需预先安装 Python — uv 会处理一切。
# 安装后会尽量把 octop 链接到已在 PATH 中的目录（如 /usr/local/bin），
# 当前终端无需 source / 重开即可直接使用。
set -euo pipefail

# ── 默认配置 ──────────────────────────────────────────────────────────────────
OCTOP_HOME="${OCTOP_HOME:-$HOME/.octop}"
OCTOP_VENV="$OCTOP_HOME/venv"
OCTOP_BIN="$OCTOP_HOME/bin"
PYTHON_VERSION="3.12"
OCTOP_REPO="${OCTOP_REPO:-https://github.com/TencentCloud/Octop.git}"
_OCTOP_REPO_BASE="${OCTOP_REPO%/*}"
HARNESS_AGENT_REPO="${HARNESS_AGENT_REPO:-${_OCTOP_REPO_BASE}/harness-agent.git}"
HARNESS_GATEWAY_REPO="${HARNESS_GATEWAY_REPO:-${_OCTOP_REPO_BASE}/harness-gateway.git}"
HARNESS_BROWSER_REPO="${HARNESS_BROWSER_REPO:-${_OCTOP_REPO_BASE}/harness-browser.git}"

if [ -n "${BASH_SOURCE[0]:-}" ]; then
    _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    _REPO_ROOT="$(cd "$_SCRIPT_DIR/.." && pwd)"
    if [ -f "$_REPO_ROOT/pyproject.toml" ]; then
        SOURCE_DIR="$_REPO_ROOT"
    else
        SOURCE_DIR=""
    fi
else
    SOURCE_DIR=""
fi

VERSION=""
FROM_SOURCE=false
EXTRAS=""
PYPI_MIRROR=""

# ── 颜色 ─────────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    BOLD="\033[1m"
    GREEN="\033[0;32m"
    YELLOW="\033[0;33m"
    RED="\033[0;31m"
    RESET="\033[0m"
else
    BOLD="" GREEN="" YELLOW="" RED="" RESET=""
fi

info()  { printf "${GREEN}[octop]${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}[octop]${RESET} %s\n" "$*"; }
error() { printf "${RED}[octop]${RESET} %s\n" "$*" >&2; }
die()   { error "$@"; exit 1; }

# ── 解析参数 ──────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"; shift 2 ;;
        --from-source)
            FROM_SOURCE=true
            if [[ $# -ge 2 && "$2" != --* ]]; then
                SOURCE_DIR="$(cd "$2" && pwd)" || die "目录不存在: $2"
                shift
            fi
            shift ;;
        --from-pypi|--pypi)
            FROM_SOURCE=false
            SOURCE_DIR=""
            shift ;;
        --extras)
            EXTRAS="$2"; shift 2 ;;
        --mirror)
            PYPI_MIRROR="$2"; shift 2 ;;
        -h|--help)
            cat <<EOF
Octop 安装脚本 (macOS / Linux)

用法: bash install.sh [选项]

选项:
  --version <版本>      安装指定版本（例如 0.1.0）[仅限 PyPI]
  --from-source [目录]  从源码安装；未指定目录时从 git 仓库克隆
  --from-pypi           从 PyPI 安装（默认）
  --extras <附加组件>   额外可选组件（例如 desktop）；browser/playwright 默认安装
  --mirror <镜像URL>    指定 PyPI 镜像（例如 https://mirrors.aliyun.com/pypi/simple）
  -h, --help            显示此帮助

说明: 若系统已安装 Chrome/Chromium（常见于 macOS/Windows 或 Linux 桌面），
  安装脚本将直接使用它，跳过体积较大的 Playwright 自带 Chromium 下载。

环境变量:
  OCTOP_HOME              安装目录（默认: ~/.octop）
  OCTOP_PYPI_MIRROR       PyPI 镜像地址（与 --mirror 等效）
  OCTOP_REPO              源码克隆地址（--from-source 且无本地目录时使用）
  HARNESS_AGENT_REPO      harness-agent 仓库（默认从 OCTOP_REPO 推导）
  HARNESS_GATEWAY_REPO    harness-gateway 仓库（默认从 OCTOP_REPO 推导）
  HARNESS_BROWSER_REPO    harness-browser 仓库（源码安装时使用）
  PLAYWRIGHT_DOWNLOAD_HOST  Playwright 下载镜像（可选，用于加速）

说明:
  本脚本在隔离虚拟环境（~/.octop/venv）中安装，不会影响系统 Python。
  默认会安装 Playwright 相关依赖；若检测到系统已安装 Chrome/Chromium，
  则跳过 Playwright 自带 Chromium 的下载，直接使用系统浏览器：
  1. Playwright Chromium 浏览器及 Python 包（已安装系统浏览器时跳过）
  2. 系统级依赖（Linux: apt/dnf/yum/pacman/zypper；仅下载 Chromium 时需要）
  3. CJK 字体用于中文网页渲染
EOF
            exit 0 ;;
        *)
            die "未知选项: $1（尝试 --help）" ;;
    esac
done

# ── 操作系统检查 ──────────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
    Linux|Darwin) ;;
    *) die "不支持的操作系统: $OS。请使用 install.ps1 或 install.bat 安装 Windows 版本。" ;;
esac

printf "${GREEN}[octop]${RESET} 正在将 Octop 安装到 ${BOLD}%s${RESET}\n" "$OCTOP_HOME"

# ── 步骤 1: 确保 uv 可用 ────────────────────────────────────────────────────
_install_uv_via_pip() {
    local py_bin=""
    for candidate in python3 python; do
        if command -v "$candidate" &>/dev/null; then
            py_bin="$candidate"
            break
        fi
    done
    [ -z "$py_bin" ] && return 1

    local install_dir="$HOME/.local/bin"
    mkdir -p "$install_dir"

    local mirrors=(
        "https://mirrors.cloud.tencent.com/pypi/simple"
        "https://mirrors.aliyun.com/pypi/simple"
        "https://pypi.tuna.tsinghua.edu.cn/simple"
    )
    for mirror in "${mirrors[@]}"; do
        local host
        host="$(echo "$mirror" | awk -F/ '{print $3}')"
        info "尝试通过 PyPI 镜像安装 uv: $mirror"
        "$py_bin" -m pip install -q uv \
            --break-system-packages \
            -i "$mirror" --trusted-host "$host" 2>/dev/null || \
        "$py_bin" -m pip install -q uv --user \
            --break-system-packages \
            -i "$mirror" --trusted-host "$host" 2>/dev/null || \
        "$py_bin" -m pip install -q uv \
            -i "$mirror" --trusted-host "$host" 2>/dev/null || \
        "$py_bin" -m pip install -q uv --user \
            -i "$mirror" --trusted-host "$host" 2>/dev/null || true

        local uv_bin
        uv_bin="$("$py_bin" -c 'from uv._find_uv import find_uv_bin; print(find_uv_bin())' 2>/dev/null)" || true
        if [ -z "$uv_bin" ] || [ ! -x "$uv_bin" ]; then
            uv_bin="$("$py_bin" -c '
import sysconfig, os, sys
for p in [
    sysconfig.get_path("scripts"),
    sysconfig.get_path("scripts", vars={"base": sys.base_prefix}),
    sysconfig.get_path("scripts", scheme="posix_user"),
    os.path.expanduser("~/.local/bin"),
    "/usr/local/bin",
]:
    if p and os.path.isfile(os.path.join(p, "uv")):
        print(os.path.join(p, "uv"))
        break
' 2>/dev/null)" || true
        fi

        if [ -n "$uv_bin" ] && [ -x "$uv_bin" ]; then
            [ "$uv_bin" != "$install_dir/uv" ] && \
                { ln -sf "$uv_bin" "$install_dir/uv" 2>/dev/null || cp "$uv_bin" "$install_dir/uv"; }
            chmod +x "$install_dir/uv"
            export PATH="$install_dir:$PATH"
            command -v uv &>/dev/null && return 0
        fi
    done
    return 1
}

_install_uv_via_astral() {
    info "尝试通过官方安装脚本安装 uv..."
    if curl -LsSf --connect-timeout 20 https://astral.sh/uv/install.sh 2>/dev/null | sh 2>/dev/null; then
        if [ -f "$HOME/.local/bin/env" ]; then
            # shellcheck disable=SC1091
            . "$HOME/.local/bin/env" 2>/dev/null || true
        fi
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
        command -v uv &>/dev/null && return 0
    fi
    return 1
}

ensure_uv() {
    if command -v uv &>/dev/null; then
        info "已找到 uv: $(command -v uv)"
        return
    fi
    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [ -x "$candidate" ]; then
            export PATH="$(dirname "$candidate"):$PATH"
            info "已找到 uv: $candidate"
            return
        fi
    done

    info "正在安装 uv..."
    if _install_uv_via_pip; then
        command -v uv &>/dev/null && { info "uv 安装成功（via PyPI）"; return; }
    fi
    if _install_uv_via_astral; then
        command -v uv &>/dev/null && { info "uv 安装成功（via astral.sh）"; return; }
    fi
    die "uv 安装失败。请手动运行: pip3 install uv -i https://mirrors.cloud.tencent.com/pypi/simple"
}

ensure_uv

# ── 选择最快的 PyPI 镜像 ──────────────────────────────────────────────────────
_PYPI_MIRRORS=(
    "https://mirrors.cloud.tencent.com/pypi/simple"
    "https://mirrors.aliyun.com/pypi/simple"
    "https://pypi.tuna.tsinghua.edu.cn/simple"
    "https://mirrors.ustc.edu.cn/pypi/simple"
)
_FASTEST_MIRROR=""
_select_fastest_pypi_mirror() {
    local best_mirror="${_PYPI_MIRRORS[0]}"
    local best_time=9999
    info "正在测速 PyPI 镜像..."
    for mirror in "${_PYPI_MIRRORS[@]}"; do
        local t t_ms
        t="$(curl -o /dev/null -s -w '%{time_connect}' \
            --connect-timeout 3 --max-time 5 \
            "$mirror/pip/" 2>/dev/null || echo '9999')"
        t_ms="$(echo "$t" | awk '{printf "%d", $1*1000}')"
        if [ "$t_ms" -lt "$best_time" ] 2>/dev/null; then
            best_time="$t_ms"
            best_mirror="$mirror"
        fi
    done
    info "最快镜像: $best_mirror (${best_time}ms)"
    _FASTEST_MIRROR="$best_mirror"
}

# ── glibc / 旧发行版：部分依赖（如 tiktoken）仅提供 manylinux_2_28+ wheel ──
_glibc_major_minor() {
    # 输出如 2.17；非 Linux / 无法检测时返回空
    [ "$OS" = "Linux" ] || { echo ""; return; }
    local ver
    ver="$(ldd --version 2>&1 | head -n1 | awk '{print $NF}')"
    echo "$ver"
}

_glibc_too_old_for_wheels() {
    # manylinux_2_28 要求 glibc >= 2.28（CentOS 7 = 2.17）
    local ver
    ver="$(_glibc_major_minor)"
    [ -n "$ver" ] || return 1
    local major minor
    major="${ver%%.*}"
    minor="${ver#*.}"
    minor="${minor%%.*}"
    [ "$major" -lt 2 ] 2>/dev/null && return 0
    [ "$major" -eq 2 ] && [ "$minor" -lt 28 ] 2>/dev/null && return 0
    return 1
}

_ensure_rustc() {
    if command -v rustc &>/dev/null; then
        info "已找到 rustc: $(command -v rustc) ($(rustc --version 2>/dev/null | awk '{print $2}'))"
        return 0
    fi
    for candidate in "$HOME/.cargo/bin/rustc"; do
        if [ -x "$candidate" ]; then
            export PATH="$(dirname "$candidate"):$PATH"
            info "已找到 rustc: $candidate"
            return 0
        fi
    done

    info "正在安装 Rust 工具链（rustup）以便从源码编译部分依赖..."
    if curl -LsSf --connect-timeout 30 https://sh.rustup.rs 2>/dev/null | sh -s -- -y --default-toolchain stable 2>/dev/null; then
        # shellcheck disable=SC1091
        . "$HOME/.cargo/env" 2>/dev/null || export PATH="$HOME/.cargo/bin:$PATH"
        command -v rustc &>/dev/null && return 0
    fi
    return 1
}

_ensure_c_build_tools() {
    if command -v cc &>/dev/null || command -v gcc &>/dev/null; then
        return 0
    fi
    info "正在安装 C 编译工具（gcc/make）..."
    if command -v apt-get &>/dev/null; then
        if command -v sudo &>/dev/null && sudo -n true 2>/dev/null; then
            sudo apt-get update -qq 2>/dev/null || true
            sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq build-essential 2>/dev/null || true
        elif [ "$(id -u)" -eq 0 ]; then
            apt-get update -qq 2>/dev/null || true
            DEBIAN_FRONTEND=noninteractive apt-get install -y -qq build-essential 2>/dev/null || true
        fi
    elif command -v yum &>/dev/null; then
        if [ "$(id -u)" -eq 0 ]; then
            yum install -y gcc gcc-c++ make openssl-devel 2>/dev/null || true
        elif command -v sudo &>/dev/null && sudo -n true 2>/dev/null; then
            sudo yum install -y gcc gcc-c++ make openssl-devel 2>/dev/null || true
        fi
    elif command -v dnf &>/dev/null; then
        if [ "$(id -u)" -eq 0 ]; then
            dnf install -y gcc gcc-c++ make openssl-devel 2>/dev/null || true
        elif command -v sudo &>/dev/null && sudo -n true 2>/dev/null; then
            sudo dnf install -y gcc gcc-c++ make openssl-devel 2>/dev/null || true
        fi
    fi
    command -v cc &>/dev/null || command -v gcc &>/dev/null
}

_cxx_major() {
    local v
    v="$(${CXX:-g++} -dumpversion 2>/dev/null || true)"
    echo "${v%%.*}"
}

_fix_centos7_scl_repos() {
    # CentOS 7 EOL：mirrorlist.centos.org 已失效，改用 vault
    local f
    for f in /etc/yum.repos.d/CentOS-SCLo*.repo; do
        [ -f "$f" ] || continue
        sed -i \
            -e 's|^mirrorlist=|#mirrorlist=|g' \
            -e 's|^#[[:space:]]*baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' \
            -e 's|^baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' \
            "$f" 2>/dev/null || true
    done
}

_ensure_modern_cxx() {
    # playwright → greenlet 等需较新 C++；CentOS 7 自带 gcc 4.8 不够
    local major
    major="$(_cxx_major)"
    if [ -n "$major" ] && [ "$major" -ge 7 ] 2>/dev/null; then
        info "C++ 编译器就绪: $(${CXX:-g++} --version 2>/dev/null | head -n1)"
        return 0
    fi

    if ! command -v yum &>/dev/null; then
        warn "系统 gcc 过旧且无 yum，greenlet/playwright 源码编译可能失败"
        return 1
    fi

    info "系统 gcc 过旧（需 >=7），正在安装 devtoolset-9..."
    local yum_cmd=(yum)
    if [ "$(id -u)" -ne 0 ]; then
        if command -v sudo &>/dev/null && sudo -n true 2>/dev/null; then
            yum_cmd=(sudo yum)
        else
            warn "需要 root/sudo 安装 devtoolset-9"
            return 1
        fi
    fi

    "${yum_cmd[@]}" install -y centos-release-scl 2>/dev/null || true
    _fix_centos7_scl_repos
    if ! "${yum_cmd[@]}" install -y devtoolset-9-gcc devtoolset-9-gcc-c++ make 2>/dev/null; then
        warn "devtoolset-9 安装失败，greenlet/playwright 可能无法编译"
        return 1
    fi

    if [ -f /opt/rh/devtoolset-9/enable ]; then
        # enable 脚本会读未定义的 MANPATH；临时关闭 nounset
        set +u
        # shellcheck disable=SC1091
        . /opt/rh/devtoolset-9/enable
        set -u
        export CC=gcc CXX=g++
        info "已启用 devtoolset-9: $(g++ --version 2>/dev/null | head -n1)"
        return 0
    fi
    return 1
}

_ensure_old_glibc_build_toolchain() {
    # CentOS 7 / 旧 RHEL：无 manylinux_2_28 wheel 时需源码编译 Rust/C++ 扩展
    if ! _glibc_too_old_for_wheels; then
        return 0
    fi
    local ver
    ver="$(_glibc_major_minor)"
    warn "检测到 glibc ${ver}（< 2.28，如 CentOS 7）：部分依赖需本地编译"
    _ensure_c_build_tools || warn "未找到 gcc，源码编译可能失败"
    _ensure_modern_cxx || warn "未启用新版 g++，playwright 依赖（greenlet）可能编译失败"
    if ! _ensure_rustc; then
        die "当前系统 glibc=$ver，无法使用预编译 wheel，且 Rust 安装失败。请升级到 CentOS/RHEL 8+、Ubuntu 20.04+，或手动安装 rustup 后重试。"
    fi
}

# ── 步骤 2: 创建/更新虚拟环境 ────────────────────────────────────────────────
if [ -x "$OCTOP_VENV/bin/python" ]; then
    info "发现已有环境，正在升级..."
else
    info "正在创建 Python $PYTHON_VERSION 环境..."
    uv venv "$OCTOP_VENV" --python "$PYTHON_VERSION" --quiet --seed
fi
[ -x "$OCTOP_VENV/bin/python" ] || die "虚拟环境创建失败"
info "Python 环境就绪 ($("$OCTOP_VENV/bin/python" --version))"

_ensure_old_glibc_build_toolchain

# ── 步骤 3: 安装 Octop ───────────────────────────────────────────────────────
# browser/playwright 为默认安装内容；其它 --extras 追加合并
_merge_install_extras() {
    local result="browser"
    if [ -n "$EXTRAS" ]; then
        local IFS=','
        local part
        for part in $EXTRAS; do
            case "$part" in
                ""|browser|channels-feishu) continue ;;
                *) result="${result},${part}" ;;
            esac
        done
    fi
    echo "$result"
}
EXTRAS_MERGED="$(_merge_install_extras)"
EXTRAS_SUFFIX="[$EXTRAS_MERGED]"

_EXTRA_MIRROR="${PYPI_MIRROR:-${OCTOP_PYPI_MIRROR:-}}"
if [ -z "$_EXTRA_MIRROR" ]; then
    _select_fastest_pypi_mirror
    _EXTRA_MIRROR="$_FASTEST_MIRROR"
else
    info "使用指定镜像: $_EXTRA_MIRROR"
fi

_CONSOLE_AVAILABLE=0
prepare_console() {
    local repo_dir="$1"
    local console_dest="$repo_dir/src/octop/dashboard"

    if [ -f "$console_dest/index.html" ]; then
        _CONSOLE_AVAILABLE=1
        return
    fi

    if [ ! -f "$repo_dir/dashboard/package.json" ]; then
        warn "未找到前端源码 — Web UI 将不可用。"
        return
    fi

    if ! command -v npm &>/dev/null; then
        warn "未找到 npm — 跳过前端构建。"
        warn "请安装 Node.js 后重新运行，或手动执行: cd dashboard && npm ci && npm run build"
        return
    fi

    info "正在构建前端 (npm ci && npm run build)..."
    (cd "$repo_dir/dashboard" && npm ci && npm run build)
    if [ -f "$console_dest/index.html" ]; then
        _CONSOLE_AVAILABLE=1
        info "前端构建成功"
    else
        warn "前端构建完成但未找到 index.html — Web UI 将不可用。"
    fi
}

_verify_install() {
    info "正在验证安装..."
    if ! "$OCTOP_VENV/bin/python" -c "from octop.infra.agents.manager import AgentManager" 2>/dev/null; then
        die "安装验证失败：核心模块无法导入。请检查依赖版本或重新运行安装脚本。"
    fi
    info "安装验证通过"
}

_clone_source_workspace() {
    local workdir="$1"
    command -v git &>/dev/null || die "克隆仓库需要 git。请安装 git 或使用 --from-pypi。"
    mkdir -p "$workdir"
    info "正在克隆 harness-agent / harness-gateway / Octop 源码..."
    git clone --depth 1 "$HARNESS_AGENT_REPO" "$workdir/harness-agent"
    git clone --depth 1 "$HARNESS_GATEWAY_REPO" "$workdir/harness-gateway"
    git clone --depth 1 "$HARNESS_BROWSER_REPO" "$workdir/harness-browser"
    git clone --depth 1 "$OCTOP_REPO" "$workdir/orca"
}

if [ "$FROM_SOURCE" = true ]; then
    if [ -n "$SOURCE_DIR" ]; then
        info "正在从本地源码安装: $SOURCE_DIR"
        prepare_console "$SOURCE_DIR"
        uv pip install "${SOURCE_DIR}${EXTRAS_SUFFIX}" --python "$OCTOP_VENV/bin/python"
    else
        INSTALL_WORKDIR="$(mktemp -d)"
        trap 'rm -rf "$INSTALL_WORKDIR"' EXIT
        _clone_source_workspace "$INSTALL_WORKDIR"
        REPO_DIR="$INSTALL_WORKDIR/orca"
        prepare_console "$REPO_DIR"
        uv pip install "${REPO_DIR}${EXTRAS_SUFFIX}" --python "$OCTOP_VENV/bin/python"
    fi
else
    PACKAGE="octop"
    [ -n "$VERSION" ] && PACKAGE="octop==$VERSION"

    info "正在从 PyPI 安装 ${PACKAGE}${EXTRAS_SUFFIX}..."
    info "主源: https://pypi.org/simple  依赖加速: $_EXTRA_MIRROR"
    install_args=(
        --python "$OCTOP_VENV/bin/python"
        --quiet
        --index-url https://pypi.org/simple
        --extra-index-url "$_EXTRA_MIRROR"
    )
    if [ -n "$VERSION" ] && [[ "$VERSION" =~ (dev|a|b|rc) ]]; then
        install_args+=(--prerelease=explicit)
    fi
    UV_SYSTEM_PYTHON=0 uv pip install "${PACKAGE}${EXTRAS_SUFFIX}" "${install_args[@]}"
fi

_verify_install

[ -x "$OCTOP_VENV/bin/octop" ] || die "安装失败: 在虚拟环境中未找到 octop CLI"
info "Octop 安装成功"

if [ "$_CONSOLE_AVAILABLE" = 0 ]; then
    CONSOLE_CHECK="$("$OCTOP_VENV/bin/python" -c "import importlib.resources, octop; p=importlib.resources.files('octop')/'dashboard'/'index.html'; print('yes' if p.is_file() else 'no')" 2>/dev/null || echo 'no')"
    [ "$CONSOLE_CHECK" = "yes" ] && _CONSOLE_AVAILABLE=1
fi

# ── 步骤 3.5: 安装 Playwright Chromium 及系统依赖 ─────────────────────────────
_install_playwright_system_deps() {
    # macOS 无需额外系统依赖
    if [ "$OS" = "Darwin" ]; then
        info "macOS: Playwright 系统依赖已内置"
        return
    fi

    if command -v apt-get &>/dev/null || command -v apt &>/dev/null; then
        info "检测到 apt 包管理器 (Debian/Ubuntu)..."
        info "正在安装 Playwright 系统依赖..."
        # 优先使用 Playwright 自带的 install-deps
        if "$OCTOP_VENV/bin/python" -m playwright install-deps chromium --with-deps 2>/dev/null; then
            return
        fi
        # 回退：手动安装（Ubuntu 24+ 部分包名为 *t64）
        local _apt="apt-get"
        if command -v sudo &>/dev/null && [ "$(id -u)" -ne 0 ]; then
            _apt="sudo apt-get"
        fi
        $_apt update 2>/dev/null || true
        # 逐包尝试，兼容 Ubuntu 22/24 包名差异
        local pkg
        for pkg in \
            libnss3 libxss1 libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 \
            libxrender1 libatk1.0-0 libc6 libcairo2 libcups2 libdbus-1-3 \
            libexpat1 libfontconfig1 libfreetype6 libgbm1 libglib2.0-0 \
            libgtk-3-0 libpango-1.0-0 libpangocairo-1.0-0 libxfixes3 \
            libxinerama1 libxt6 zlib1g fonts-noto-cjk \
            libasound2t64 libasound2 \
            libatk-bridge2.0-0t64 libatk-bridge2.0-0 \
            libgdk-pixbuf-2.0-0 libgdk-pixbuf2.0-0 \
            ; do
            $_apt install -y "$pkg" 2>/dev/null || true
        done
        return
    fi

    if command -v dnf &>/dev/null; then
        info "检测到 dnf 包管理器 (Fedora/RHEL)..."
        info "正在安装 Playwright 系统依赖..."
        sudo dnf install -y \
            alsa-lib atk at-spi2-atk cups-libs libdrm libgbm \
            libX11 libXcomposite libXdamage libXext libXfixes libXrandr \
            libxkbcommon nss pango \
            google-noto-sans-cjk-ttc-fonts 2>/dev/null || true
        return
    fi

    if command -v yum &>/dev/null; then
        info "检测到 yum 包管理器 (CentOS/RHEL)..."
        info "正在安装 Playwright 系统依赖..."
        sudo yum install -y \
            alsa-lib atk at-spi2-atk cups-libs libdrm libgbm \
            libX11 libXcomposite libXdamage libXext libXfixes libXrandr \
            libxkbcommon nss pango \
            google-noto-sans-cjk-ttc-fonts 2>/dev/null || true
        return
    fi

    if command -v pacman &>/dev/null; then
        info "检测到 pacman 包管理器 (Arch/Manjaro)..."
        info "正在安装 Playwright 系统依赖..."
        sudo pacman -S --noconfirm --needed \
            alsa-lib atk at-spi2-atk cups libdrm mesa \
            libx11 libxcomposite libxdamage libxext libxfixes libxrandr \
            libxkbcommon nss pango \
            noto-fonts-cjk 2>/dev/null || true
        return
    fi

    if command -v zypper &>/dev/null; then
        info "检测到 zypper 包管理器 (openSUSE)..."
        info "正在安装 Playwright 系统依赖..."
        sudo zypper install -y \
            alsa libatk-1_0-0 libatk-bridge-2_0-0 libcups2 libdrm2 \
            Mesa-libgbm1 libX11-6 libXcomposite1 libXdamage1 libXext6 \
            libXfixes3 libXrandr2 libxkbcommon0 libnspr4 libnss3 \
            libpango-1_0-0 \
            noto-sans-cjk-fonts 2>/dev/null || true
        return
    fi

    warn "未检测到已知包管理器，跳过 Playwright 系统依赖自动安装"
    warn "如果 Playwright 运行出错，请手动安装依赖或运行: playwright install-deps chromium"
}

_install_playwright_browsers() {
    if _glibc_too_old_for_wheels; then
        warn "当前 glibc=$(_glibc_major_minor)（如 CentOS 7）无法运行 Playwright 自带的 Node/Chromium（需 glibc ≥ 2.28）"
        warn "已安装 playwright Python 包，但跳过 Chromium；建议使用 Ubuntu 20.04+ / CentOS/RHEL 8+"
        return 1
    fi
    info "正在安装 Playwright Chromium 浏览器..."
    if "$OCTOP_VENV/bin/python" -m playwright install chromium; then
        info "✓ Playwright Chromium 安装成功"
        return 0
    fi
    warn "⚠ Playwright Chromium 安装失败，可稍后运行:"
    warn "  $OCTOP_VENV/bin/python -m playwright install chromium"
    return 1
}

# 检测系统是否已安装 Chrome / Chromium。
# GUI 系统（macOS / Windows / Linux 桌面）通常已自带，无需再下载 Playwright 自带 Chromium。
_detect_system_chrome() {
    # 优先复用 harness-browser 的探测器（与运行期 launch 路径一致）
    local chrome
    chrome="$("$OCTOP_VENV/bin/python" -c '
import sys
try:
    from harness_browser.cdp.launcher import find_chrome
except Exception:
    sys.exit(0)
p = find_chrome()
if p:
    print(p)
' 2>/dev/null)"
    [ -n "$chrome" ] && { echo "$chrome"; return 0; }

    # 回退：常见命令
    local candidate
    for candidate in google-chrome google-chrome-stable chromium chromium-browser chrome; do
        if command -v "$candidate" &>/dev/null; then
            command -v "$candidate"
            return 0
        fi
    done

    # 回退：常见安装路径（GUI 系统）
    local p
    for p in \
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
        "/Applications/Chromium.app/Contents/MacOS/Chromium" \
        "/opt/google/chrome/chrome" \
        "/usr/bin/google-chrome" \
        "/usr/bin/chromium" \
        "/usr/bin/chromium-browser" \
        ; do
        [ -x "$p" ] && { echo "$p"; return 0; }
    done
    return 1
}

# 默认安装 Playwright 系统依赖和 Chromium，但检测到系统浏览器时跳过下载。
if "$OCTOP_VENV/bin/python" -c "import playwright" 2>/dev/null; then
    _SYSTEM_CHROME="$(_detect_system_chrome || true)"
    if [ -n "$_SYSTEM_CHROME" ]; then
        info "检测到系统已安装 Chrome/Chromium: $_SYSTEM_CHROME"
        info "将直接使用系统浏览器，跳过 Playwright Chromium 下载（更快、更省空间）。"
        info "如需改用 Playwright 自带的 Chromium，可运行:"
        info "  $OCTOP_VENV/bin/python -m playwright install chromium"
    else
        _install_playwright_system_deps
        _install_playwright_browsers || true
    fi
else
    warn "playwright 未安装到虚拟环境，跳过 Chromium；可稍后: uv pip install playwright --python $OCTOP_VENV/bin/python"
fi

# ── 步骤 4: 创建包装脚本 ─────────────────────────────────────────────────────
mkdir -p "$OCTOP_BIN"

cat > "$OCTOP_BIN/octop" << 'WRAPPER'
#!/usr/bin/env bash
# Octop CLI 包装脚本 — 委托给 uv 管理的环境。
set -euo pipefail

OCTOP_HOME="${OCTOP_HOME:-$HOME/.octop}"
REAL_BIN="$OCTOP_HOME/venv/bin/octop"

if [ ! -x "$REAL_BIN" ]; then
    echo "错误: 在 $OCTOP_HOME/venv 未找到 Octop 环境" >&2
    echo "请重新运行安装脚本" >&2
    exit 1
fi

exec "$REAL_BIN" "$@"
WRAPPER

chmod +x "$OCTOP_BIN/octop"
info "包装脚本已创建: $OCTOP_BIN/octop"

# ── 步骤 5: 让 octop 立即可用（无需 source）──────────────────────────────────
# 子进程无法修改父 shell 的 PATH。要让 curl|bash / bash install.sh 后立刻可用，
# 只能把可执行文件放进「当前 PATH 里已有」的目录（常见为 /usr/local/bin）。

_can_write_dir() {
    local dir="$1"
    [ -d "$dir" ] && [ -w "$dir" ]
}

_sudo_nopass() {
    command -v sudo &>/dev/null && sudo -n true 2>/dev/null
}

_try_symlink() {
    # 在 target_dir 创建指向包装脚本的 octop 符号链接。成功返回 0。
    local target_dir="$1"
    local link_path="$target_dir/octop"
    local src="$OCTOP_BIN/octop"

    mkdir -p "$target_dir" 2>/dev/null || true

    if _can_write_dir "$target_dir"; then
        ln -sfn "$src" "$link_path" && return 0
    fi
    if _sudo_nopass; then
        sudo mkdir -p "$target_dir" 2>/dev/null || true
        sudo ln -sfn "$src" "$link_path" && return 0
    fi
    return 1
}

_path_contains() {
    case ":$PATH:" in
        *":$1:"*) return 0 ;;
        *) return 1 ;;
    esac
}

LINKED_PATH=""
_link_into_existing_path() {
    local candidates=()
    case "$OS" in
        Darwin)
            # Apple Silicon Homebrew 优先，再退回传统 /usr/local/bin
            candidates=(/opt/homebrew/bin /usr/local/bin)
            ;;
        *)
            candidates=(/usr/local/bin)
            ;;
    esac

    local dir
    for dir in "${candidates[@]}"; do
        if _path_contains "$dir" && _try_symlink "$dir"; then
            LINKED_PATH="$dir/octop"
            return 0
        fi
    done

    # 回退：~/.local/bin（Ubuntu/Debian 的 ~/.profile 会在目录存在时加入 PATH；
    # 若当前会话 PATH 尚无该目录，仍无法免 source，仅作持久化兜底）
    if _try_symlink "$HOME/.local/bin"; then
        LINKED_PATH="$HOME/.local/bin/octop"
        if _path_contains "$HOME/.local/bin"; then
            return 0
        fi
        # 目录刚创建、尚未在当前 PATH 中：本会话仍依赖下方 profile / 手动 PATH
        return 1
    fi
    return 1
}

IMMEDIATE_OK=false
if _link_into_existing_path; then
    IMMEDIATE_OK=true
    info "已链接到 ${LINKED_PATH}（当前终端可直接运行 octop）"
elif [ -n "$LINKED_PATH" ]; then
    info "已链接到 $LINKED_PATH"
fi

# ── 步骤 6: 更新 shell / 系统 profile（新开终端持久生效）─────────────────────
PATH_ENTRY="export PATH=\"${OCTOP_BIN}:\$PATH\""

add_to_profile() {
    local profile="$1"
    local create="$2"
    if [ -f "$profile" ] && grep -qF "$OCTOP_BIN" "$profile" 2>/dev/null; then
        return 0
    fi
    # 兼容旧版标记（仅含 .octop/bin 字样）
    if [ -f "$profile" ] && grep -qF '.octop/bin' "$profile" 2>/dev/null; then
        return 0
    fi
    if [ -f "$profile" ] || [ "$create" = "create" ]; then
        printf '\n# Octop\n%s\n' "$PATH_ENTRY" >> "$profile"
        info "已更新 $profile"
        return 0
    fi
    return 1
}

_write_profile_d() {
    # CentOS / Ubuntu 登录 shell 会加载 /etc/profile.d/*.sh
    local dest="/etc/profile.d/octop.sh"
    local content="# Octop CLI
export PATH=\"${OCTOP_BIN}:\$PATH\"
"
    if [ -d /etc/profile.d ]; then
        if [ -w /etc/profile.d ] || _can_write_dir /etc/profile.d; then
            printf '%s' "$content" > "$dest" && chmod 644 "$dest" && {
                info "已写入 $dest"
                return 0
            }
        fi
        if _sudo_nopass; then
            printf '%s' "$content" | sudo tee "$dest" >/dev/null && sudo chmod 644 "$dest" && {
                info "已写入 $dest"
                return 0
            }
        fi
    fi
    return 1
}

UPDATED_PROFILE=false
case "$OS" in
    Darwin)
        add_to_profile "$HOME/.zshrc" "create" && UPDATED_PROFILE=true
        add_to_profile "$HOME/.bash_profile" "no-create" || true
        add_to_profile "$HOME/.bashrc" "no-create" || true
        ;;
    Linux)
        # CentOS/RHEL：SSH 登录读 .bash_profile；Ubuntu：登录读 .profile，交互读 .bashrc
        add_to_profile "$HOME/.bashrc" "create" && UPDATED_PROFILE=true
        add_to_profile "$HOME/.bash_profile" "no-create" || true
        add_to_profile "$HOME/.profile" "no-create" || true
        add_to_profile "$HOME/.zshrc" "no-create" || true
        _write_profile_d || true
        ;;
esac

export PATH="$OCTOP_BIN:$PATH"

# ── 完成 ──────────────────────────────────────────────────────────────────────
echo ""
printf "${GREEN}${BOLD}Octop 安装成功！${RESET}\n"
echo ""
printf "  安装位置:          ${BOLD}%s${RESET}\n" "$OCTOP_HOME"
printf "  Python:            ${BOLD}%s${RESET}\n" "$("$OCTOP_VENV/bin/python" --version 2>&1)"
if [ -n "$LINKED_PATH" ]; then
    printf "  CLI 链接:          ${BOLD}%s${RESET}\n" "$LINKED_PATH"
fi
if [ "$_CONSOLE_AVAILABLE" = 1 ]; then
    printf "  控制台 (Web UI):   ${GREEN}可用${RESET}\n"
else
    printf "  控制台 (Web UI):   ${YELLOW}不可用${RESET}\n"
fi
echo ""

if [ "$IMMEDIATE_OK" = true ]; then
    info "octop 命令已就绪，当前终端可直接使用（无需 source）"
elif [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "$0" ]; then
    export PATH="$OCTOP_BIN:$PATH"
    info "PATH 已更新，octop 命令即刻可用"
else
    warn "未能写入已在 PATH 中的目录（如 /usr/local/bin）。当前终端请执行:"
    echo ""
    printf "  ${BOLD}export PATH=\"%s:\$PATH\"${RESET}\n" "$OCTOP_BIN"
    echo ""
    if [ "$UPDATED_PROFILE" = true ]; then
        echo "新开终端无需此步骤。"
    fi
fi
echo ""
echo "然后运行:"
echo ""
printf "  ${BOLD}octop run${RESET}       # 前台启动（API + Web 控制台）\n"
printf "  ${BOLD}octop service start${RESET}  # 安装并后台守护运行（systemd / launchd）\n"
printf "  ${BOLD}open http://127.0.0.1:8088${RESET}\n"
echo ""
printf "升级: 重新运行本安装脚本。清理: ${BOLD}octop clean${RESET}\n"
printf "Playwright 重装: ${BOLD}$OCTOP_VENV/bin/python -m playwright install chromium${RESET}\n"
