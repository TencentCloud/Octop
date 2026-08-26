# Shared helpers for green portable packaging scripts.
# shellcheck shell=bash
# Sourced by bootstrap-runtime.sh / vendor-wheels.sh / package.sh

GREEN_ROOT="${GREEN_ROOT:-${REPO_ROOT}/desktop/portable}"
GREEN_RUNTIMES="${GREEN_ROOT}/runtimes"
GREEN_WHEELS="${GREEN_ROOT}/wheels"
GREEN_CACHE="${GREEN_ROOT}/.cache"
GREEN_RELEASE="${GREEN_ROOT}/release"

# Pin a known-good python-build-standalone release (override with PBS_TAG / PBS_PY).
PBS_TAG="${PBS_TAG:-20251209}"
PBS_PY="${PBS_PY:-3.12.12}"
# Prefer npmmirror mirror; override with PBS_BASE_URL for GitHub upstream.
PBS_BASE_URL="${PBS_BASE_URL:-https://registry.npmmirror.com/-/binary/python-build-standalone/${PBS_TAG}}"

ALL_PLATS=(
  darwin-arm64
  darwin-amd64
  linux-amd64
  linux-arm64
  windows-amd64
  windows-arm64
)

# Map GitHub Actions RUNNER_ARCH (X64/ARM64/...) → green arch suffix.
runner_arch_to_green() {
  case "$(printf '%s' "${1:-}" | tr '[:lower:]' '[:upper:]')" in
    ARM64|ARM) echo arm64 ;;
    X64|AMD64) echo amd64 ;;
    *) return 1 ;;
  esac
}

# Probe python machine() — setup-uv on windows-11-arm provides arm64 CPython
# even when Git Bash itself is an x64 process.
python_machine_arch() {
  local py m
  for py in python python3; do
    if command -v "$py" >/dev/null 2>&1; then
      m="$("$py" -c 'import platform; print(platform.machine())' 2>/dev/null | tr -d '\r\n')"
      case "$(printf '%s' "$m" | tr '[:lower:]' '[:upper:]')" in
        ARM64|AARCH64) echo arm64; return 0 ;;
        AMD64|X86_64|X64) echo amd64; return 0 ;;
      esac
    fi
  done
  return 1
}

host_plat() {
  # CI / operators can pin this when shell arch detection is wrong
  # (common on windows-11-arm + x64 Git Bash).
  if [[ -n "${GREEN_HOST_PLAT:-}" ]]; then
    if ! is_known_plat "$GREEN_HOST_PLAT"; then
      echo "GREEN_HOST_PLAT=${GREEN_HOST_PLAT} is not a known plat" >&2
      return 1
    fi
    echo "$GREEN_HOST_PLAT"
    return 0
  fi

  local os arch
  case "$(uname -s)" in
    Darwin) os=darwin ;;
    Linux) os=linux ;;
    MINGW*|MSYS*|CYGWIN*|Windows_NT) os=windows ;;
    *)
      echo "unsupported host OS: $(uname -s)" >&2
      return 1
      ;;
  esac

  # GitHub Actions: RUNNER_ARCH is the VM architecture (not the shell binary).
  if arch="$(runner_arch_to_green "${RUNNER_ARCH:-}")"; then
    echo "${os}-${arch}"
    return 0
  fi

  # Windows: detect OS / interpreter arch, not the current process arch.
  # Git Bash / MSYS on windows-11-arm often is an x64 binary, so both
  # `uname -m` and PROCESSOR_ARCHITECTURE can look like amd64 while the
  # machine is ARM64. That falsely enables cross-assemble + --only-binary
  # and breaks sdist-only pure-Python deps (e.g. aliyun-python-sdk-core).
  if [[ "$os" == windows ]]; then
    if arch="$(python_machine_arch)"; then
      echo "${os}-${arch}"
      return 0
    fi

    local os_arch="" pa="${PROCESSOR_ARCHITECTURE:-}" pa32="${PROCESSOR_ARCHITEW6432:-}"
    if command -v powershell.exe >/dev/null 2>&1; then
      os_arch="$(
        powershell.exe -NoProfile -Command \
          '[System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()' \
          2>/dev/null | tr -d '\r\n'
      )"
    fi
    # Fallback: CIM OS architecture (more reliable on some runner images).
    if [[ -z "$os_arch" ]] && command -v powershell.exe >/dev/null 2>&1; then
      os_arch="$(
        powershell.exe -NoProfile -Command \
          '(Get-CimInstance -ClassName Win32_OperatingSystem).OSArchitecture' \
          2>/dev/null | tr -d '\r\n'
      )"
    fi
    case "$(printf '%s' "$os_arch" | tr '[:lower:]' '[:upper:]')" in
      ARM64|*ARM64*|ARM\ 64*) arch=arm64 ;;
      X64|AMD64|*X64*) arch=amd64 ;;
      *)
        case "$(printf '%s' "${pa32:-$pa}" | tr '[:lower:]' '[:upper:]')" in
          ARM64) arch=arm64 ;;
          AMD64|X86_64) arch=amd64 ;;
          *)
            case "$(uname -m)" in
              arm64|aarch64) arch=arm64 ;;
              x86_64|amd64) arch=amd64 ;;
              *)
                echo "unsupported arch: OSArchitecture=${os_arch} uname=$(uname -m) PROCESSOR_ARCHITECTURE=${pa} PROCESSOR_ARCHITEW6432=${pa32} RUNNER_ARCH=${RUNNER_ARCH:-}" >&2
                return 1
                ;;
            esac
            ;;
        esac
        ;;
    esac
  else
    case "$(uname -m)" in
      arm64|aarch64) arch=arm64 ;;
      x86_64|amd64) arch=amd64 ;;
      *)
        echo "unsupported arch: $(uname -m)" >&2
        return 1
        ;;
    esac
  fi
  echo "${os}-${arch}"
}

# python-build-standalone triple
plat_triple() {
  case "$1" in
    darwin-arm64) echo "aarch64-apple-darwin" ;;
    darwin-amd64) echo "x86_64-apple-darwin" ;;
    linux-amd64) echo "x86_64-unknown-linux-gnu" ;;
    linux-arm64) echo "aarch64-unknown-linux-gnu" ;;
    windows-amd64) echo "x86_64-pc-windows-msvc" ;;
    windows-arm64) echo "aarch64-pc-windows-msvc" ;;
    *) return 1 ;;
  esac
}

# uv --python-platform values
uv_platform() {
  case "$1" in
    darwin-arm64) echo "aarch64-apple-darwin" ;;
    darwin-amd64) echo "x86_64-apple-darwin" ;;
    linux-amd64) echo "x86_64-unknown-linux-gnu" ;;
    linux-arm64) echo "aarch64-unknown-linux-gnu" ;;
    windows-amd64) echo "x86_64-pc-windows-msvc" ;;
    windows-arm64) echo "aarch64-pc-windows-msvc" ;;
    *) return 1 ;;
  esac
}

# pip --platform tags (for optional offline wheel prefetch)
pip_platform() {
  case "$1" in
    darwin-arm64) echo "macosx_11_0_arm64" ;;
    darwin-amd64) echo "macosx_11_0_x86_64" ;;
    linux-amd64) echo "manylinux2014_x86_64" ;;
    linux-arm64) echo "manylinux2014_aarch64" ;;
    windows-amd64) echo "win_amd64" ;;
    windows-arm64) echo "win_arm64" ;;
    *) return 1 ;;
  esac
}

is_known_plat() {
  local p
  for p in "${ALL_PLATS[@]}"; do
    [[ "$p" == "$1" ]] && return 0
  done
  return 1
}

runtime_python() {
  # Print path to python inside a runtime root (may not exist yet).
  local runtime_dir="$1"
  if [[ -x "${runtime_dir}/bin/python3" ]]; then
    echo "${runtime_dir}/bin/python3"
  elif [[ -f "${runtime_dir}/python.exe" ]]; then
    echo "${runtime_dir}/python.exe"
  elif [[ -x "${runtime_dir}/install/bin/python3" ]]; then
    echo "${runtime_dir}/install/bin/python3"
  else
    echo "${runtime_dir}/bin/python3"
  fi
}

require_uv() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required (https://docs.astral.sh/uv/)" >&2
    exit 1
  fi
}

pbs_archive_name() {
  local plat="$1"
  local triple
  triple="$(plat_triple "$plat")" || return 1
  echo "cpython-${PBS_PY}+${PBS_TAG}-${triple}-install_only_stripped.tar.gz"
}

# Write platform-specific uv/pip overrides (empty file = none).
# Prints the override file path when overrides exist; otherwise prints nothing.
#
# cryptography: locked 49.x dropped macOS Intel / universal2 wheels. Native
# darwin-amd64 builds then compile from sdist and link Homebrew OpenSSL
# (/usr/local/opt/openssl@3), which is missing on end-user machines.
# Pin to the last release that still ships macosx_*_universal2 wheels.
write_green_overrides() {
  local plat="$1"
  local out="${2:-${GREEN_ROOT}/overrides-${plat}.txt}"
  mkdir -p "$(dirname "$out")"
  case "$plat" in
    windows-arm64)
      {
        echo "psycopg-binary ; sys_platform == 'octop-unsupported'"
        echo "sqlite-vec ; sys_platform == 'octop-unsupported'"
        # 46.0.0 is the only release shipping a win_arm64 wheel; newer ones would
        # fall back to a Rust + OpenSSL source build that fails on the runner.
        echo "cryptography==46.0.0"
      } > "$out"
      echo "$out"
      ;;
    darwin-amd64)
      {
        # 46.0.3 still publishes cp*-abi3-macosx_10_9_universal2 (covers x86_64).
        # cryptography>=47 only ships macos arm64 wheels → sdist + brew openssl.
        echo "cryptography==46.0.3"
      } > "$out"
      echo "$out"
      ;;
    *)
      rm -f "$out"
      ;;
  esac
}

# Fail if any Mach-O under packages/ links Homebrew / MacPorts absolute paths.
# Catches relocatable-package regressions (e.g. cryptography built against brew openssl).
verify_no_homebrew_dylibs() {
  local staging_packages="$1"
  local plat="$2"

  case "$plat" in
    darwin-*) ;;
    *) return 0 ;;
  esac
  if ! command -v otool >/dev/null 2>&1; then
    echo "[green] WARNING: otool missing — skip Homebrew dylib check" >&2
    return 0
  fi

  local bad=0
  local f deps
  # Limit to native extension shared objects (skip .dylibs already vendored beside wheels).
  while IFS= read -r -d '' f; do
    deps="$(otool -L "$f" 2>/dev/null || true)"
    if printf '%s\n' "$deps" | grep -E -q '/usr/local/opt/|/opt/homebrew/|/opt/local/'; then
      echo "[green] ERROR: non-portable dylib link in ${f}" >&2
      printf '%s\n' "$deps" | grep -E '/usr/local/opt/|/opt/homebrew/|/opt/local/' >&2 || true
      bad=1
    fi
  done < <(find "$staging_packages" \( -name '*.so' -o -name '*.dylib' \) -print0 2>/dev/null)

  if [[ "$bad" -ne 0 ]]; then
    echo "[green] ERROR: green zip must not depend on Homebrew/MacPorts libraries." >&2
    echo "  Tip: pin cryptography to a release with macos universal2 wheels (see write_green_overrides)," >&2
    echo "  and keep --only-binary cryptography so sdist builds cannot slip through." >&2
    return 1
  fi
  echo "[green] dylib check OK (no Homebrew/MacPorts absolute paths)"
  return 0
}
