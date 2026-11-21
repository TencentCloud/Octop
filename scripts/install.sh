#!/usr/bin/env bash
# Octop installer (macOS / Linux)
# Usage: bash scripts/install.sh                 # install from PyPI (default)
#    or: bash scripts/install.sh --from-source   # install from a local checkout
#    or: curl -fsSL <url>/install.sh | bash      # remote install
#
# Installs Octop into ~/.octop and uses uv to manage the Python environment.
# Python does not need to be installed first; uv handles that.
# After install, octop is linked into a directory already on PATH (such as
# /usr/local/bin) so the current terminal can run it without sourcing a profile.
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
OCTOP_HOME="${OCTOP_HOME:-$HOME/.octop}"
OCTOP_VENV="$OCTOP_HOME/venv"
OCTOP_BIN="$OCTOP_HOME/bin"
PYTHON_VERSION="3.12"
OCTOP_REPO="${OCTOP_REPO:-https://github.com/TencentCloud/Octop.git}"
_OCTOP_REPO_BASE="${OCTOP_REPO%/*}"
HARNESS_AGENT_REPO="${HARNESS_AGENT_REPO:-${_OCTOP_REPO_BASE}/octop-harness.git}"
HARNESS_GATEWAY_REPO="${HARNESS_GATEWAY_REPO:-${_OCTOP_REPO_BASE}/octop-gateway.git}"
HARNESS_BROWSER_REPO="${HARNESS_BROWSER_REPO:-${_OCTOP_REPO_BASE}/octop-browser.git}"

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

# ── Colors ─────────────────────────────────────────────────────────────────────
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

# ── Parse arguments ──────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"; shift 2 ;;
        --from-source)
            FROM_SOURCE=true
            if [[ $# -ge 2 && "$2" != --* ]]; then
                SOURCE_DIR="$(cd "$2" && pwd)" || die "Directory not found: $2"
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
Octop installer (macOS / Linux)

Usage: bash install.sh [OPTIONS]

Options:
  --version <VER>       Install a specific version (e.g. 0.1.0) [PyPI only]
  --from-source [DIR]   Install from source; clones the git repo if DIR is omitted
  --from-pypi           Install from PyPI (default)
  --extras <EXTRAS>     Extra optional components (e.g. desktop, browser)
  --mirror <URL>        Use a specific PyPI mirror (e.g. https://mirrors.cloud.tencent.com/pypi/simple)
  -h, --help            Show this help

Note: Playwright Chromium is not downloaded by default. Pass
  --extras browser to install it, or install later from the dashboard.
  If a system Chrome/Chromium already exists, that download is skipped
  even with --extras browser.

Environment variables:
  OCTOP_HOME              Install directory (default: ~/.octop)
  OCTOP_PYPI_MIRROR       PyPI mirror URL (same as --mirror)
  OCTOP_REPO              Git URL to clone (used by --from-source with no local dir)
  HARNESS_AGENT_REPO      octop-harness repo (derived from OCTOP_REPO by default)
  HARNESS_GATEWAY_REPO    octop-gateway repo (derived from OCTOP_REPO by default)
  HARNESS_BROWSER_REPO    octop-browser repo (used for source installs)
  PLAYWRIGHT_DOWNLOAD_HOST  Playwright download mirror (optional; auto: npmmirror -> official)
  PLAYWRIGHT_INSTALL_TIMEOUT  Per-mirror download timeout in seconds (default 600)

Details:
  Everything is installed into an isolated virtualenv (~/.octop/venv), so the
  system Python is untouched. Playwright Chromium is opt-in (--extras browser):
  1. Playwright Chromium browser (skipped if a system browser exists)
  2. System libraries (Linux: apt/dnf/yum/pacman/zypper; only needed for Chromium)
  3. CJK fonts for rendering Chinese web pages
EOF
            exit 0 ;;
        *)
            die "Unknown option: $1 (try --help)" ;;
    esac
done

# ── OS check ──────────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
    Linux|Darwin) ;;
    *) die "Unsupported OS: $OS. Use install.ps1 or install.bat on Windows." ;;
esac

printf "${GREEN}[octop]${RESET} Installing Octop into ${BOLD}%s${RESET}\n" "$OCTOP_HOME"

# ── Step 1: ensure uv is available ────────────────────────────────────────────────────
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

    # Skip the Tsinghua and USTC mirrors: some networks 302 wheel downloads to TUNA and get HTTP 403.
    local mirrors=(
        "https://mirrors.cloud.tencent.com/pypi/simple"
        "https://mirrors.aliyun.com/pypi/simple"
    )
    for mirror in "${mirrors[@]}"; do
        local host
        host="$(echo "$mirror" | awk -F/ '{print $3}')"
        info "Trying uv from PyPI mirror: $mirror"
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
    info "Trying the official uv installer..."
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
        info "Found uv: $(command -v uv)"
        return
    fi
    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [ -x "$candidate" ]; then
            export PATH="$(dirname "$candidate"):$PATH"
            info "Found uv: $candidate"
            return
        fi
    done

    info "Installing uv..."
    if _install_uv_via_pip; then
        command -v uv &>/dev/null && { info "uv installed successfully (via PyPI)"; return; }
    fi
    if _install_uv_via_astral; then
        command -v uv &>/dev/null && { info "uv installed successfully (via astral.sh)"; return; }
    fi
    die "Failed to install uv. Run manually: pip3 install uv -i https://mirrors.cloud.tencent.com/pypi/simple"
}

ensure_uv

# ── Pick the fastest PyPI mirror ──────────────────────────────────────────────
# Keep only mirrors that actually work. Tsinghua TUNA and USTC 302 some wheel
# downloads to TUNA and return 403, which makes uv pip install fail.
_PYPI_MIRRORS=(
    "https://mirrors.cloud.tencent.com/pypi/simple"
    "https://mirrors.aliyun.com/pypi/simple"
)
_FASTEST_MIRROR=""
_select_fastest_pypi_mirror() {
    local best_mirror="${_PYPI_MIRRORS[0]}"
    local best_time=9999
    local found=0
    info "Benchmarking PyPI mirrors..."
    for mirror in "${_PYPI_MIRRORS[@]}"; do
        local t t_ms code
        # Also check the HTTP status: a fast mirror that is not 2xx is unusable.
        code="$(curl -o /dev/null -s -w '%{http_code}' \
            --connect-timeout 3 --max-time 5 \
            "$mirror/pip/" 2>/dev/null || echo '000')"
        case "$code" in
            2*) ;;
            *)
                warn "Mirror unavailable (HTTP $code), skipping: $mirror"
                continue
                ;;
        esac
        t="$(curl -o /dev/null -s -w '%{time_total}' \
            --connect-timeout 3 --max-time 5 \
            "$mirror/pip/" 2>/dev/null || echo '9999')"
        t_ms="$(echo "$t" | awk '{printf "%d", $1*1000}')"
        if [ "$t_ms" -lt "$best_time" ] 2>/dev/null; then
            best_time="$t_ms"
            best_mirror="$mirror"
            found=1
        fi
    done
    if [ "$found" -eq 0 ]; then
        warn "No usable mirror found; using official PyPI only"
        _FASTEST_MIRROR=""
        return
    fi
    info "Fastest mirror: $best_mirror (${best_time}ms)"
    _FASTEST_MIRROR="$best_mirror"
}

# Try uv pip install against each candidate mirror, then fall back to official PyPI.
# Args: package spec (extras allowed) plus extra uv flags (for example --prerelease=explicit).
_uv_pip_install_with_mirror_fallback() {
    local package="$1"
    shift
    local -a candidates=()
    local m

    if [ -n "${_EXTRA_MIRROR:-}" ]; then
        candidates+=("$_EXTRA_MIRROR")
    fi
    for m in "${_PYPI_MIRRORS[@]}"; do
        if [ -n "$m" ] && [ "$m" != "${_EXTRA_MIRROR:-}" ]; then
            candidates+=("$m")
        fi
    done
    candidates+=("")  # official PyPI only

    local mirror
    local -a seen=()
    for mirror in "${candidates[@]}"; do
        local dup=0 s
        for s in "${seen[@]+"${seen[@]}"}"; do
            [ "$s" = "$mirror" ] && { dup=1; break; }
        done
        [ "$dup" -eq 1 ] && continue
        seen+=("$mirror")

        local -a args=(
            --python "$OCTOP_VENV/bin/python"
            --quiet
            --index-url https://pypi.org/simple
        )
        if [ -n "$mirror" ]; then
            args+=(--extra-index-url "$mirror")
            info "Trying dependency mirror: $mirror"
        else
            info "Trying official PyPI only (no mirror)..."
        fi

        if UV_SYSTEM_PYTHON=0 uv pip install "$package" "${args[@]}" "$@"; then
            _EXTRA_MIRROR="$mirror"
            return 0
        fi
        warn "Install failed from this index, trying the next mirror..."
    done
    return 1
}

# ── glibc / old distros: some deps (for example tiktoken) ship only manylinux_2_28+ wheels ──
_glibc_major_minor() {
    # Print a version such as 2.17. Empty when not Linux or when detection fails.
    [ "$OS" = "Linux" ] || { echo ""; return; }
    local ver
    ver="$(ldd --version 2>&1 | head -n1 | awk '{print $NF}')"
    echo "$ver"
}

_glibc_too_old_for_wheels() {
    # manylinux_2_28 requires glibc >= 2.28 (CentOS 7 is 2.17).
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
        info "Found rustc: $(command -v rustc) ($(rustc --version 2>/dev/null | awk '{print $2}'))"
        return 0
    fi
    for candidate in "$HOME/.cargo/bin/rustc"; do
        if [ -x "$candidate" ]; then
            export PATH="$(dirname "$candidate"):$PATH"
            info "Found rustc: $candidate"
            return 0
        fi
    done

    info "Installing the Rust toolchain (rustup) to build some deps from source..."
    if curl -LsSf --connect-timeout 30 https://sh.rustup.rs 2>/dev/null | sh -s -- -y --default-toolchain stable 2>/dev/null; then
        # shellcheck disable=SC1091
        . "$HOME/.cargo/env" 2>/dev/null || export PATH="$HOME/.cargo/bin:$PATH"
        command -v rustc &>/dev/null && return 0
    fi
    return 1
}

# Run package-manager commands as root or passwordless sudo. CentOS often logs in as root, so do not require sudo.
_sudo_nopass() {
    command -v sudo &>/dev/null && sudo -n true 2>/dev/null
}

_run_as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    elif _sudo_nopass; then
        sudo "$@"
    else
        return 1
    fi
}

# Whether the Python that will compile extensions has Python.h (uv's interpreter or system python3-dev).
_python_dev_headers_ok() {
    local py=""
    if [ -x "${OCTOP_VENV:-}/bin/python" ]; then
        py="$OCTOP_VENV/bin/python"
    elif command -v python3 &>/dev/null; then
        py="$(command -v python3)"
    else
        return 1
    fi
    "$py" -c 'import sysconfig, os
p = sysconfig.get_path("include")
raise SystemExit(0 if p and os.path.isfile(os.path.join(p, "Python.h")) else 1)' 2>/dev/null
}

# gcc plus Python headers: evdev/pynput and similar packages compile locally when no matching wheel exists.
# gcc alone is not enough. Missing python3-dev (common on Ubuntu cloud images) still fails, so do not skip just because gcc is present.
_ensure_c_build_tools() {
    local have_cc=0 have_pyh=0
    if command -v cc &>/dev/null || command -v gcc &>/dev/null; then
        have_cc=1
    fi
    if _python_dev_headers_ok; then
        have_pyh=1
    fi
    if [ "$have_cc" -eq 1 ] && [ "$have_pyh" -eq 1 ]; then
        return 0
    fi

    info "Installing local build dependencies (gcc / Python dev headers)..."
    if command -v apt-get &>/dev/null; then
        _run_as_root env DEBIAN_FRONTEND=noninteractive apt-get update -qq 2>/dev/null || true
        _run_as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
            build-essential python3-dev 2>/dev/null || true
    elif command -v dnf &>/dev/null; then
        _run_as_root dnf install -y \
            gcc gcc-c++ make openssl-devel libffi-devel python3-devel 2>/dev/null || true
    elif command -v yum &>/dev/null; then
        _run_as_root yum install -y \
            gcc gcc-c++ make openssl-devel libffi-devel python3-devel 2>/dev/null || true
    fi

    have_cc=0
    if command -v cc &>/dev/null || command -v gcc &>/dev/null; then
        have_cc=1
    fi
    have_pyh=0
    if _python_dev_headers_ok; then
        have_pyh=1
    fi
    [ "$have_cc" -eq 1 ] || return 1
    # System python3-devel may not match the Python minor version uv downloaded. uv's interpreter usually ships headers.
    # If headers are still missing, a later source build may fail and pip will report it.
    return 0
}

_cxx_major() {
    local v
    v="$(${CXX:-g++} -dumpversion 2>/dev/null || true)"
    echo "${v%%.*}"
}

_fix_centos7_scl_repos() {
    # CentOS 7 is EOL: mirrorlist.centos.org is dead, so use vault.centos.org.
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
    # playwright pulls greenlet, and numpy 2.x needs a newer C++ compiler. CentOS 7 ships gcc 4.8, which is not enough.
    # numpy>=2.5 requires GCC >= 10.3, so prefer devtoolset-11.
    local major
    major="$(_cxx_major)"
    if [ -n "$major" ] && [ "$major" -ge 10 ] 2>/dev/null; then
        info "C++ compiler ready: $(${CXX:-g++} --version 2>/dev/null | head -n1)"
        return 0
    fi

    if ! command -v yum &>/dev/null; then
        warn "System gcc is too old and yum is unavailable; building greenlet/numpy may fail"
        return 1
    fi

    if [ "$(id -u)" -ne 0 ] && ! _sudo_nopass; then
        warn "Installing devtoolset requires root/sudo"
        return 1
    fi

    _run_as_root yum install -y centos-release-scl 2>/dev/null || true
    _fix_centos7_scl_repos

    local dts enable_file=""
    for dts in 11 10 9; do
        info "System gcc is too old (numpy needs >=10.3), installing devtoolset-${dts}..."
        if _run_as_root yum install -y \
            "devtoolset-${dts}-gcc" "devtoolset-${dts}-gcc-c++" make 2>/dev/null; then
            if [ -f "/opt/rh/devtoolset-${dts}/enable" ]; then
                enable_file="/opt/rh/devtoolset-${dts}/enable"
                break
            fi
        fi
        warn "devtoolset-${dts} install failed, trying the next version..."
    done

    if [ -z "$enable_file" ]; then
        warn "Could not install a usable devtoolset; greenlet/numpy may fail to build"
        return 1
    fi

    # The enable script reads an unset MANPATH; turn nounset off briefly.
    set +u
    # shellcheck disable=SC1091
    . "$enable_file"
    set -u
    export CC=gcc CXX=g++
    info "Enabled $(basename "$(dirname "$enable_file")"): $(g++ --version 2>/dev/null | head -n1)"
    major="$(_cxx_major)"
    if [ -n "$major" ] && [ "$major" -ge 10 ] 2>/dev/null; then
        return 0
    fi
    # gcc 9 can still build greenlet, but not current numpy.
    warn "Current g++ major version is ${major:-?} (numpy 2.5+ needs >=10)"
    return 0
}

_ensure_old_glibc_image_libs() {
    # Without a manylinux_2_28 wheel, Pillow and similar packages build from source and need jpeg/zlib/freetype headers.
    info "Installing image library headers (needed to build Pillow from source)..."
    if command -v apt-get &>/dev/null; then
        _run_as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
            libjpeg-dev zlib1g-dev libfreetype6-dev libtiff-dev libwebp-dev \
            liblcms2-dev libopenjp2-7-dev 2>/dev/null || true
    elif command -v dnf &>/dev/null; then
        _run_as_root dnf install -y \
            libjpeg-turbo-devel zlib-devel freetype-devel libtiff-devel \
            libwebp-devel lcms2-devel openjpeg2-devel 2>/dev/null || true
    elif command -v yum &>/dev/null; then
        _run_as_root yum install -y \
            libjpeg-turbo-devel zlib-devel freetype-devel libtiff-devel \
            libwebp-devel lcms2-devel openjpeg2-devel 2>/dev/null || true
    fi
}

_ensure_old_glibc_build_toolchain() {
    # CentOS 7 / old RHEL: without manylinux_2_28 wheels, Rust and C++ extensions must be built from source.
    if ! _glibc_too_old_for_wheels; then
        return 0
    fi
    local ver
    ver="$(_glibc_major_minor)"
    warn "Detected glibc ${ver} (< 2.28, e.g. CentOS 7): some deps must be built locally"
    _ensure_c_build_tools || warn "gcc not found; building from source may fail"
    _ensure_old_glibc_image_libs
    _ensure_modern_cxx || warn "No modern g++ enabled; the playwright dep (greenlet) may fail to build"
    if ! _ensure_rustc; then
        die "glibc=$ver on this system: prebuilt wheels are unusable and installing Rust failed. Upgrade to CentOS/RHEL 8+ or Ubuntu 20.04+, or install rustup manually and retry."
    fi
}

# ── Step 2: create or update the virtualenv ────────────────────────────────────────────────
if [ -x "$OCTOP_VENV/bin/python" ]; then
    info "Existing environment found, upgrading..."
else
    info "Creating the Python $PYTHON_VERSION environment..."
    uv venv "$OCTOP_VENV" --python "$PYTHON_VERSION" --quiet --seed
fi
[ -x "$OCTOP_VENV/bin/python" ] || die "Failed to create the virtualenv"
info "Python environment ready ($("$OCTOP_VENV/bin/python" --version))"

# On Linux, always make sure native extensions can be compiled (Ubuntu may lack python3-dev, CentOS python3-devel, and so on).
if [ "$OS" = "Linux" ]; then
    _ensure_c_build_tools || warn "gcc / Python headers are incomplete; deps needing a source build may fail"
fi
_ensure_old_glibc_build_toolchain

# ── Step 3: install Octop ───────────────────────────────────────────────────────
# The playwright Python package is a core dependency. Chromium is downloaded only with --extras browser.
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
    info "Using the specified mirror: $_EXTRA_MIRROR"
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
        warn "Frontend source not found - the Web UI will be unavailable."
        return
    fi

    if ! command -v npm &>/dev/null; then
        warn "npm not found - skipping the frontend build."
        warn "Install Node.js and re-run, or build manually: cd dashboard && npm ci && npm run build"
        return
    fi

    info "Building the frontend (npm ci && npm run build)..."
    (cd "$repo_dir/dashboard" && npm ci && npm run build)
    if [ -f "$console_dest/index.html" ]; then
        _CONSOLE_AVAILABLE=1
        info "Frontend build succeeded"
    else
        warn "Frontend build finished but index.html is missing - the Web UI will be unavailable."
    fi
}

# TEMP: mcp 2.x removed RequestContext and is incompatible with langchain-mcp-adapters.
# octop-harness>=0.9.18 already pins this. Pin again before verification so an
# older harness or a lagging mirror still gets a compatible mcp.
# Remove this once an Octop release carries the pin on its own.
_pin_mcp_compat() {
    info "Pinning mcp<2 (langchain-mcp-adapters compatibility; temporary)..."
    if ! _uv_pip_install_with_mirror_fallback "mcp>=1.27.1,<2"; then
        warn "Failed to pin mcp; install verification may fail"
        return 1
    fi
    return 0
}

_verify_install() {
    info "Verifying the installation..."
    if ! "$OCTOP_VENV/bin/python" -c "from octop.infra.agents.manager import AgentManager" 2>/dev/null; then
        die "Verification failed: core modules cannot be imported. Check dependency versions or re-run the installer."
    fi
    info "Installation verified"
}

_clone_source_workspace() {
    local workdir="$1"
    command -v git &>/dev/null || die "git is required to clone the repos. Install git or use --from-pypi."
    mkdir -p "$workdir"
    info "Cloning octop-harness / octop-gateway / Octop sources..."
    git clone --depth 1 "$HARNESS_AGENT_REPO" "$workdir/octop-harness"
    git clone --depth 1 "$HARNESS_GATEWAY_REPO" "$workdir/octop-gateway"
    git clone --depth 1 "$HARNESS_BROWSER_REPO" "$workdir/octop-browser"
    git clone --depth 1 "$OCTOP_REPO" "$workdir/orca"
}

if [ "$FROM_SOURCE" = true ]; then
    if [ -n "$SOURCE_DIR" ]; then
        info "Installing from local source: $SOURCE_DIR"
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
    # PEP 508: extras go between the name and the version (octop[browser]==x.y.z).
    # octop==x.y.z[browser] is an invalid requirement and uv/pip reject it.
    PACKAGE="octop${EXTRAS_SUFFIX}"
    [ -n "$VERSION" ] && PACKAGE="octop${EXTRAS_SUFFIX}==$VERSION"

    info "Installing ${PACKAGE} from PyPI..."
    if [ -n "${_EXTRA_MIRROR:-}" ]; then
        info "Primary index: https://pypi.org/simple  preferred mirror: $_EXTRA_MIRROR"
    else
        info "Primary index: https://pypi.org/simple"
    fi
    _PYPI_EXTRA_ARGS=()
    if [ -n "$VERSION" ] && [[ "$VERSION" =~ (dev|a|b|rc) ]]; then
        _PYPI_EXTRA_ARGS+=(--prerelease=explicit)
    fi
    _uv_pip_install_with_mirror_fallback "$PACKAGE" ${_PYPI_EXTRA_ARGS[@]+"${_PYPI_EXTRA_ARGS[@]}"} \
        || die "Install from PyPI failed (tried mirrors and the official index)"
fi

_pin_mcp_compat || true
_verify_install

[ -x "$OCTOP_VENV/bin/octop" ] || die "Install failed: octop CLI not found in the virtualenv"
info "Octop installed successfully"

if [ "$_CONSOLE_AVAILABLE" = 0 ]; then
    CONSOLE_CHECK="$("$OCTOP_VENV/bin/python" -c "import importlib.resources, octop; p=importlib.resources.files('octop')/'dashboard'/'index.html'; print('yes' if p.is_file() else 'no')" 2>/dev/null || echo 'no')"
    [ "$CONSOLE_CHECK" = "yes" ] && _CONSOLE_AVAILABLE=1
fi

# ── Step 3.4: install bubblewrap on Linux (execute jail under a local root_dir) ──
_ensure_bubblewrap() {
    # macOS has no usable bwrap; install it only on Linux. Without it, harness uses a plain local shell and no directory jail.
    if [ "$(uname -s 2>/dev/null || echo unknown)" != "Linux" ]; then
        return 0
    fi
    if command -v bwrap &>/dev/null; then
        info "bubblewrap ready: $(command -v bwrap)"
        return 0
    fi
    info "Installing bubblewrap (required for the execute jail under a local root_dir)..."
    if command -v apt-get &>/dev/null || command -v apt &>/dev/null; then
        _run_as_root env DEBIAN_FRONTEND=noninteractive apt-get update -qq 2>/dev/null || true
        _run_as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq bubblewrap 2>/dev/null || true
    elif command -v dnf &>/dev/null; then
        _run_as_root dnf install -y bubblewrap 2>/dev/null || true
    elif command -v yum &>/dev/null; then
        _run_as_root yum install -y bubblewrap 2>/dev/null || true
    elif command -v pacman &>/dev/null; then
        _run_as_root pacman -Sy --noconfirm bubblewrap 2>/dev/null || true
    elif command -v zypper &>/dev/null; then
        _run_as_root zypper install -y bubblewrap 2>/dev/null || true
    else
        warn "Unrecognized package manager; install bubblewrap (bwrap) manually"
        return 0
    fi
    if command -v bwrap &>/dev/null; then
        info "bubblewrap installed successfully: $(command -v bwrap)"
    else
        warn "bubblewrap install failed: execute under a local root_dir falls back to path rewriting (no real jail)"
    fi
}

_ensure_bubblewrap

# ── Step 3.5: install Playwright Chromium and system dependencies ─────────────────────────────
_install_playwright_system_deps() {
    # macOS needs no extra system packages.
    if [ "$OS" = "Darwin" ]; then
        info "macOS: Playwright system dependencies are built in"
        return
    fi

    if command -v apt-get &>/dev/null || command -v apt &>/dev/null; then
        info "Detected the apt package manager (Debian/Ubuntu)..."
        info "Installing Playwright system dependencies..."
        # Prefer Playwright's own install-deps.
        if "$OCTOP_VENV/bin/python" -m playwright install-deps chromium --with-deps 2>/dev/null; then
            return
        fi
        # Fallback: install packages by hand. Ubuntu 24+ renamed some of them to *t64.
        _run_as_root apt-get update 2>/dev/null || true
        # Try one package at a time so Ubuntu 22 and 24 names both work.
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
            _run_as_root apt-get install -y "$pkg" 2>/dev/null || true
        done
        return
    fi

    if command -v dnf &>/dev/null; then
        info "Detected the dnf package manager (Fedora/RHEL)..."
        info "Installing Playwright system dependencies..."
        _run_as_root dnf install -y \
            alsa-lib atk at-spi2-atk cups-libs libdrm libgbm \
            libX11 libXcomposite libXdamage libXext libXfixes libXrandr \
            libxkbcommon nss pango \
            google-noto-sans-cjk-ttc-fonts 2>/dev/null || true
        return
    fi

    if command -v yum &>/dev/null; then
        info "Detected the yum package manager (CentOS/RHEL)..."
        info "Installing Playwright system dependencies..."
        _run_as_root yum install -y \
            alsa-lib atk at-spi2-atk cups-libs libdrm libgbm \
            libX11 libXcomposite libXdamage libXext libXfixes libXrandr \
            libxkbcommon nss pango \
            google-noto-sans-cjk-ttc-fonts 2>/dev/null || true
        return
    fi

    if command -v pacman &>/dev/null; then
        info "Detected the pacman package manager (Arch/Manjaro)..."
        info "Installing Playwright system dependencies..."
        _run_as_root pacman -S --noconfirm --needed \
            alsa-lib atk at-spi2-atk cups libdrm mesa \
            libx11 libxcomposite libxdamage libxext libxfixes libxrandr \
            libxkbcommon nss pango \
            noto-fonts-cjk 2>/dev/null || true
        return
    fi

    if command -v zypper &>/dev/null; then
        info "Detected the zypper package manager (openSUSE)..."
        info "Installing Playwright system dependencies..."
        _run_as_root zypper install -y \
            alsa libatk-1_0-0 libatk-bridge-2_0-0 libcups2 libdrm2 \
            Mesa-libgbm1 libX11-6 libXcomposite1 libXdamage1 libXext6 \
            libXfixes3 libXrandr2 libxkbcommon0 libnspr4 libnss3 \
            libpango-1_0-0 \
            noto-sans-cjk-fonts 2>/dev/null || true
        return
    fi

    warn "No known package manager detected; skipping automatic Playwright system deps"
    warn "If Playwright fails at runtime, install deps manually or run: playwright install-deps chromium"
}

_install_playwright_browsers() {
    if _glibc_too_old_for_wheels; then
        warn "glibc=$(_glibc_major_minor) (e.g. CentOS 7) cannot run Playwright's bundled Node/Chromium (needs glibc >= 2.28)"
        warn "The playwright Python package is installed but Chromium was skipped; Ubuntu 20.04+ / CentOS/RHEL 8+ recommended"
        return 1
    fi

    # Mirror order, matching the finnie TencentOS installer:
    #   1. PLAYWRIGHT_DOWNLOAD_HOST when the user set it
    #   2. npmmirror (fastest from China)
    #   3. the official CDN as the last resort
    # A per-mirror timeout keeps a stuck GCS download from hanging the whole install.
    # Override it with PLAYWRIGHT_INSTALL_TIMEOUT (seconds).
    local _pw_timeout="${PLAYWRIGHT_INSTALL_TIMEOUT:-600}"
    _run_playwright_chromium_install() {
        if command -v timeout &>/dev/null; then
            timeout "$_pw_timeout" "$OCTOP_VENV/bin/python" -m playwright install chromium
        else
            "$OCTOP_VENV/bin/python" -m playwright install chromium
        fi
    }

    local -a _pw_hosts=()
    local _h
    if [ -n "${PLAYWRIGHT_DOWNLOAD_HOST:-}" ]; then
        _pw_hosts+=("$PLAYWRIGHT_DOWNLOAD_HOST")
    fi
    _pw_hosts+=("https://cdn.npmmirror.com/binaries/playwright")
    _pw_hosts+=("")  # official CDN: clear PLAYWRIGHT_DOWNLOAD_HOST

    local _seen="|"
    for _h in "${_pw_hosts[@]}"; do
        case "$_seen" in
            *"|${_h}|"*) continue ;;
        esac
        _seen="${_seen}${_h}|"

        if [ -n "$_h" ]; then
            export PLAYWRIGHT_DOWNLOAD_HOST="$_h"
            info "Trying Playwright mirror: $_h"
        else
            unset PLAYWRIGHT_DOWNLOAD_HOST || true
            info "Trying the official Playwright CDN..."
        fi

        if _run_playwright_chromium_install; then
            info "✓ Playwright Chromium installed successfully"
            return 0
        fi
        warn "This source failed or timed out, trying the next mirror..."
    done

    warn "⚠ Playwright Chromium install failed; you can run this later:"
    warn "  PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright \\"
    warn "    $OCTOP_VENV/bin/python -m playwright install chromium"
    return 1
}

# Detect an already installed Chrome or Chromium.
# GUI systems (macOS, Windows, Linux desktops) usually have one, so Playwright's bundled Chromium is unnecessary.
_detect_system_chrome() {
    # Prefer octop-browser's detector so this matches the runtime launch path.
    local chrome
    chrome="$("$OCTOP_VENV/bin/python" -c '
import sys
try:
    from octop_browser.cdp.launcher import find_chrome
except Exception:
    sys.exit(0)
p = find_chrome()
if p:
    print(p)
' 2>/dev/null)"
    [ -n "$chrome" ] && { echo "$chrome"; return 0; }

    # Fallback: common command names.
    local candidate
    for candidate in google-chrome google-chrome-stable chromium chromium-browser chrome; do
        if command -v "$candidate" &>/dev/null; then
            command -v "$candidate"
            return 0
        fi
    done

    # Fallback: common install paths on GUI systems.
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

# Playwright Chromium is opt-in (--extras browser).
_WANT_PW_CHROMIUM=0
if [ -n "$EXTRAS" ]; then
    _old_ifs="$IFS"
    IFS=','
    for _part in $EXTRAS; do
        [ "$_part" = "browser" ] && _WANT_PW_CHROMIUM=1
    done
    IFS="$_old_ifs"
fi

if [ "$_WANT_PW_CHROMIUM" != 1 ]; then
    info "Skipping Playwright Chromium download."
    info "For remote-browser automation, re-run with --extras browser, use the dashboard, or:"
    info "  $OCTOP_VENV/bin/python -m playwright install chromium"
elif "$OCTOP_VENV/bin/python" -c "import playwright" 2>/dev/null; then
    _SYSTEM_CHROME="$(_detect_system_chrome || true)"
    if [ -n "$_SYSTEM_CHROME" ]; then
        info "Detected system Chrome/Chromium: $_SYSTEM_CHROME"
        info "Using the system browser and skipping the Playwright Chromium download (faster, smaller)."
        info "To use Playwright's bundled Chromium instead, run:"
        info "  $OCTOP_VENV/bin/python -m playwright install chromium"
    else
        _install_playwright_system_deps
        _install_playwright_browsers || true
    fi
else
    warn "playwright is not in the virtualenv, skipping Chromium; you can later run: uv pip install playwright --python $OCTOP_VENV/bin/python"
fi

# ── Step 4: create the wrapper script ─────────────────────────────────────────────────────
mkdir -p "$OCTOP_BIN"

cat > "$OCTOP_BIN/octop" << 'WRAPPER'
#!/usr/bin/env bash
# Octop CLI wrapper. Delegates to the uv-managed environment.
set -euo pipefail

OCTOP_HOME="${OCTOP_HOME:-$HOME/.octop}"
REAL_BIN="$OCTOP_HOME/venv/bin/octop"

if [ ! -x "$REAL_BIN" ]; then
    echo "Error: Octop environment not found in $OCTOP_HOME/venv" >&2
    echo "Please re-run the installer" >&2
    exit 1
fi

exec "$REAL_BIN" "$@"
WRAPPER

chmod +x "$OCTOP_BIN/octop"
info "Wrapper script created: $OCTOP_BIN/octop"

# ── Step 5: make octop available immediately (no source) ─────────────────────
# A child process cannot change the parent shell's PATH. After curl|bash or
# bash install.sh, the binary has to land in a directory already on PATH
# (commonly /usr/local/bin) to work in the current terminal.

_can_write_dir() {
    local dir="$1"
    [ -d "$dir" ] && [ -w "$dir" ]
}

_try_symlink() {
    # Symlink the wrapper to octop in target_dir. Return 0 on success.
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
            # Prefer Apple Silicon Homebrew, then fall back to /usr/local/bin.
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

    # Fallback: ~/.local/bin. Ubuntu/Debian ~/.profile adds that directory to PATH
    # once it exists. If this session's PATH does not include it yet, the current
    # shell still needs the profile block below.
    if _try_symlink "$HOME/.local/bin"; then
        LINKED_PATH="$HOME/.local/bin/octop"
        if _path_contains "$HOME/.local/bin"; then
            return 0
        fi
        # The directory was just created and is not on PATH yet. This session still needs the profile block below, or a manual PATH export.
        return 1
    fi
    return 1
}

IMMEDIATE_OK=false
if _link_into_existing_path; then
    IMMEDIATE_OK=true
    info "Linked to ${LINKED_PATH} (octop works in the current shell)"
elif [ -n "$LINKED_PATH" ]; then
    info "Linked to $LINKED_PATH"
fi

# ── Step 6: update the shell profile so new terminals keep octop on PATH ─────────────────────
PATH_ENTRY="export PATH=\"${OCTOP_BIN}:\$PATH\""

add_to_profile() {
    local profile="$1"
    local create="$2"
    if [ -f "$profile" ] && grep -qF "$OCTOP_BIN" "$profile" 2>/dev/null; then
        return 0
    fi
    # Also accept the older marker that only mentions .octop/bin.
    if [ -f "$profile" ] && grep -qF '.octop/bin' "$profile" 2>/dev/null; then
        return 0
    fi
    if [ -f "$profile" ] || [ "$create" = "create" ]; then
        printf '\n# Octop\n%s\n' "$PATH_ENTRY" >> "$profile"
        info "Updated $profile"
        return 0
    fi
    return 1
}

_write_profile_d() {
    # CentOS and Ubuntu login shells load /etc/profile.d/*.sh.
    local dest="/etc/profile.d/octop.sh"
    local content="# Octop CLI
export PATH=\"${OCTOP_BIN}:\$PATH\"
"
    if [ -d /etc/profile.d ]; then
        if [ -w /etc/profile.d ] || _can_write_dir /etc/profile.d; then
            printf '%s' "$content" > "$dest" && chmod 644 "$dest" && {
                info "Wrote $dest"
                return 0
            }
        fi
        if _sudo_nopass; then
            printf '%s' "$content" | sudo tee "$dest" >/dev/null && sudo chmod 644 "$dest" && {
                info "Wrote $dest"
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
        # CentOS/RHEL SSH logins read .bash_profile. Ubuntu logins read .profile; interactive shells read .bashrc.
        add_to_profile "$HOME/.bashrc" "create" && UPDATED_PROFILE=true
        add_to_profile "$HOME/.bash_profile" "no-create" || true
        add_to_profile "$HOME/.profile" "no-create" || true
        add_to_profile "$HOME/.zshrc" "no-create" || true
        _write_profile_d || true
        ;;
esac

export PATH="$OCTOP_BIN:$PATH"


# Probe mobile host capability into config.json
if [ -f "$OCTOP_VENV/bin/python" ] && [ -d "$OCTOP_HOME" ]; then
  CONFIG_PATH="$OCTOP_HOME/config.json"
  if [ ! -f "$CONFIG_PATH" ]; then
    echo "{}" > "$CONFIG_PATH"
  fi
  "$OCTOP_VENV/bin/python" -m octop.infra.control.mobile "$CONFIG_PATH" || true
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
printf "${GREEN}${BOLD}Octop installed successfully!${RESET}\n"
echo ""
printf "  Location:          ${BOLD}%s${RESET}\n" "$OCTOP_HOME"
printf "  Python:            ${BOLD}%s${RESET}\n" "$("$OCTOP_VENV/bin/python" --version 2>&1)"
if [ -n "$LINKED_PATH" ]; then
    printf "  CLI link:          ${BOLD}%s${RESET}\n" "$LINKED_PATH"
fi
if [ "$_CONSOLE_AVAILABLE" = 1 ]; then
    printf "  Console (Web UI):  ${GREEN}available${RESET}\n"
else
    printf "  Console (Web UI):  ${YELLOW}unavailable${RESET}\n"
fi
echo ""

if [ "$IMMEDIATE_OK" = true ]; then
    info "octop is ready to use in the current shell (no source needed)"
elif [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "$0" ]; then
    export PATH="$OCTOP_BIN:$PATH"
    info "PATH updated; octop is available now"
else
    warn "Could not write to a directory already in PATH (e.g. /usr/local/bin). In this shell run:"
    echo ""
    printf "  ${BOLD}export PATH=\"%s:\$PATH\"${RESET}\n" "$OCTOP_BIN"
    echo ""
    if [ "$UPDATED_PROFILE" = true ]; then
        echo "New shells will not need this step."
    fi
fi
echo ""
echo "Then run:"
echo ""
printf "  ${BOLD}octop run${RESET}       # Run in the foreground (API + Web console)\n"
printf "  ${BOLD}octop service start${RESET}  # Install and run in the background (systemd / launchd)\n"
printf "  ${BOLD}open http://127.0.0.1:8088${RESET}\n"
echo ""
printf "Upgrade: re-run this installer. Cleanup: ${BOLD}octop clean${RESET}\n"
printf "Playwright Chromium (optional): ${BOLD}$OCTOP_VENV/bin/python -m playwright install chromium${RESET}\n"
