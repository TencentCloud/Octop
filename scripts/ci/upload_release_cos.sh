#!/usr/bin/env bash
# Upload GitHub Release files to
# cos://${RELEASE_COS_BUCKET}/${RELEASE_COS_PREFIX}/<version>/<filename>.
#
#   scripts/ci/upload_release_cos.sh <version-or-vtag> <src-dir>
#
# RELEASE_COS_PREFIX is the bucket-root folder for this product. OctopPet
# releases use a sibling folder so both can share the bucket. The version
# directory has no leading v.
#
# Required (Actions repository variables; no defaults):
#   RELEASE_COS_BUCKET, RELEASE_COS_REGION, RELEASE_COS_ENDPOINT, RELEASE_COS_PREFIX
# Credentials, from Actions secrets:
#   RELEASE_COS_SECRET_ID, RELEASE_COS_SECRET_KEY
set -euo pipefail

COSCLI_VERSION="${COSCLI_VERSION:-v1.0.9}"

usage() {
  echo "usage: $0 <version-or-vtag> <src-dir>" >&2
  exit 2
}

[[ $# -eq 2 ]] || usage
raw_version="$1"
src_dir="$2"

missing=()
for name in RELEASE_COS_BUCKET RELEASE_COS_REGION RELEASE_COS_ENDPOINT RELEASE_COS_PREFIX; do
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
done
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "::error::required COS variables are unset: ${missing[*]}" >&2
  exit 1
fi

version="${raw_version#v}"
if [[ ! "$version" =~ ^[0-9][0-9A-Za-z.+_-]*$ ]]; then
  echo "::error::invalid version: ${raw_version}" >&2
  exit 1
fi
if [[ ! -d "$src_dir" ]]; then
  echo "::error::source directory does not exist: ${src_dir}" >&2
  exit 1
fi

shopt -s nullglob
files=()
for path in "$src_dir"/*; do
  if [[ -f "$path" ]]; then
    files+=("$path")
  fi
done
shopt -u nullglob

if [[ ${#files[@]} -eq 0 ]]; then
  echo "::error::no files to upload in ${src_dir}" >&2
  exit 1
fi

public_base="https://${RELEASE_COS_BUCKET}.${RELEASE_COS_ENDPOINT}/${RELEASE_COS_PREFIX}/${version}"
echo "COS prefix: ${RELEASE_COS_PREFIX}/${version}/ (${#files[@]} files)"
for path in "${files[@]}"; do
  name="$(basename "$path")"
  echo "  ${public_base}/${name}"
done

if [[ -z "${RELEASE_COS_SECRET_ID:-}" || -z "${RELEASE_COS_SECRET_KEY:-}" ]]; then
  echo "::error::RELEASE_COS_SECRET_ID and RELEASE_COS_SECRET_KEY are required" >&2
  exit 1
fi

work="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
coscli="${work}/coscli-${COSCLI_VERSION}"
cfg="${work}/cos-upload-$$.yaml"
trap 'rm -f "$cfg"' EXIT

if [[ ! -x "$coscli" ]]; then
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) asset="coscli-${COSCLI_VERSION}-linux-amd64" ;;
    Linux-aarch64) asset="coscli-${COSCLI_VERSION}-linux-arm64" ;;
    Darwin-arm64) asset="coscli-${COSCLI_VERSION}-darwin-arm64" ;;
    Darwin-x86_64) asset="coscli-${COSCLI_VERSION}-darwin-amd64" ;;
    *)
      echo "::error::unsupported coscli host: $(uname -s)-$(uname -m)" >&2
      exit 1
      ;;
  esac
  url="https://github.com/tencentyun/coscli/releases/download/${COSCLI_VERSION}/${asset}"
  echo "Downloading ${url}"
  curl -fsSL "$url" -o "$coscli"
  # CI runners are linux-amd64. Other hosts used for a local dry upload are unchecked.
  if [[ "$asset" == "coscli-${COSCLI_VERSION}-linux-amd64" ]]; then
    expected="7165f2ae16c5f7ac495864c963ca574a76e04ec72680d7bc8a8eee3234d8cf91"
    if command -v sha256sum >/dev/null; then
      actual="$(sha256sum "$coscli" | awk '{print $1}')"
    else
      actual="$(shasum -a 256 "$coscli" | awk '{print $1}')"
    fi
    if [[ "$actual" != "$expected" ]]; then
      echo "::error::coscli checksum mismatch" >&2
      rm -f "$coscli"
      exit 1
    fi
  fi
  chmod 700 "$coscli"
fi

python3 - "$cfg" "$RELEASE_COS_BUCKET" "$RELEASE_COS_REGION" "$RELEASE_COS_ENDPOINT" <<'PY'
import json
import os
import pathlib
import sys

path, bucket, region, endpoint = sys.argv[1:5]

def q(value: str) -> str:
    return json.dumps(value)

text = "\n".join(
    [
        "cos:",
        "  base:",
        f"    secretid: {q(os.environ['RELEASE_COS_SECRET_ID'])}",
        f"    secretkey: {q(os.environ['RELEASE_COS_SECRET_KEY'])}",
        '    sessiontoken: ""',
        "    protocol: https",
        '    disableencryption: "true"',
        "  buckets:",
        f"    - name: {q(bucket)}",
        "      alias: octop",
        f"      region: {q(region)}",
        f"      endpoint: {q(endpoint)}",
        "      ofs: false",
        "",
    ]
)
dest = pathlib.Path(path)
dest.write_text(text, encoding="utf-8")
dest.chmod(0o600)
PY

for path in "${files[@]}"; do
  name="$(basename "$path")"
  key="${RELEASE_COS_PREFIX}/${version}/${name}"
  echo "Uploading ${name} -> ${key}"
  "$coscli" --disable-log --init-skip -c "$cfg" -e "$RELEASE_COS_ENDPOINT" \
    cp "$path" "cos://${RELEASE_COS_BUCKET}/${key}" \
    --acl public-read \
    --fail-output=false \
    --process-log=false \
    --err-retry-num 3 \
    --err-retry-interval 2
done

echo "Uploaded ${#files[@]} files under ${public_base}/"
