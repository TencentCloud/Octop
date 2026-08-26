#!/usr/bin/env bash
# Download python-build-standalone into green/runtimes/<plat>.
#
# Usage:
#   bash desktop/portable/bootstrap-runtime.sh              # host platform
#   bash desktop/portable/bootstrap-runtime.sh darwin-arm64
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=desktop/portable/_common.sh
source "${REPO_ROOT}/desktop/portable/_common.sh"

download() {
  local url="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [[ -f "$dest" && -s "$dest" ]]; then
    echo "[bootstrap] cache hit ${dest}" >&2
    return 0
  fi
  echo "[bootstrap] downloading ${url}" >&2
  curl -fL --retry 3 --retry-delay 2 -o "${dest}.partial" "$url"
  mv "${dest}.partial" "$dest"
}

flatten_pbs_install() {
  local extract_dir="$1"
  local dest="$2"
  rm -rf "$dest"
  mkdir -p "$(dirname "$dest")"
  if [[ -d "${extract_dir}/python" ]]; then
    mv "${extract_dir}/python" "$dest"
  elif [[ -d "${extract_dir}/install" ]]; then
    mv "${extract_dir}/install" "$dest"
  else
    echo "[bootstrap] unexpected PBS layout under ${extract_dir}" >&2
    find "$extract_dir" -maxdepth 2 -print >&2 || true
    exit 1
  fi
}

bootstrap_one() {
  local plat="$1"
  local triple archive url cache dest
  triple="$(plat_triple "$plat")" || {
    echo "unknown platform: $plat" >&2
    exit 1
  }
  archive="$(pbs_archive_name "$plat")"
  url="${PBS_BASE_URL}/${archive}"
  cache="${GREEN_CACHE}/${archive}"
  dest="${GREEN_RUNTIMES}/${plat}"

  mkdir -p "$GREEN_RUNTIMES" "$GREEN_CACHE"
  if [[ -x "$(runtime_python "$dest")" || -f "${dest}/python.exe" ]]; then
    echo "[bootstrap] ${plat}: runtime already present → ${dest}" >&2
    return 0
  fi

  download "$url" "$cache"
  local tmp
  tmp="$(mktemp -d "${GREEN_CACHE}/extract.XXXXXX")"
  tar -xzf "$cache" -C "$tmp"
  flatten_pbs_install "$tmp" "$dest"
  rm -rf "$tmp"

  local py
  py="$(runtime_python "$dest")"
  if [[ ! -x "$py" && ! -f "$py" ]]; then
    echo "[bootstrap] python missing after extract: ${py}" >&2
    exit 1
  fi
  echo "[bootstrap] ${plat}: ${py}" >&2
  "$py" -c "import sys; print(sys.version)" >&2 || true
}

main() {
  local plat="${1:-}"
  if [[ -z "$plat" ]]; then
    plat="$(host_plat)"
  fi
  if ! is_known_plat "$plat"; then
    echo "unknown platform: $plat (known: ${ALL_PLATS[*]})" >&2
    exit 1
  fi
  bootstrap_one "$plat"
}

main "${1:-}"
