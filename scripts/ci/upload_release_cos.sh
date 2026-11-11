#!/usr/bin/env bash
# Upload GitHub Release files to
# cos://${RELEASE_COS_BUCKET}/octop/release/<version>/<filename>.
#
#   scripts/ci/upload_release_cos.sh <version-or-vtag> <src-dir>
#
# The version directory has no leading v.
#
# Required Actions repository secrets (no defaults):
#   RELEASE_COS_BUCKET, RELEASE_COS_REGION, RELEASE_COS_ENDPOINT
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
for name in RELEASE_COS_BUCKET RELEASE_COS_REGION RELEASE_COS_ENDPOINT; do
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
  if [[ ! -f "$path" ]]; then
    continue
  fi
  name="$(basename "$path")"
  # Python wheel and sdist stay on PyPI / GitHub Release. Installer names use an
  # uppercase Octop- prefix, so this does not drop desktop archives.
  if [[ "$name" == *.whl || "$name" == octop-*.tar.gz ]]; then
    echo "Skipping non-installer package: ${name}"
    continue
  fi
  files+=("$path")
done
shopt -u nullglob

if [[ ${#files[@]} -eq 0 ]]; then
  echo "::error::no files to upload in ${src_dir}" >&2
  exit 1
fi

public_base="https://${RELEASE_COS_BUCKET}.${RELEASE_COS_ENDPOINT}/octop/release/${version}"
echo "COS prefix: octop/release/${version}/ (${#files[@]} files)"
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
log_dir="${work}/coscli-process-$$"
done_flag="${work}/cos-upload-done-$$"
mkdir -p "$log_dir"
rm -f "$done_flag"
trap 'touch "$done_flag"; rm -f "$cfg" "$cfg".*' EXIT

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
    expected="a07de5ba2800147a700ed29036b0c76a4229088cee68e1682d0eae19b638a915"
    if command -v sha256sum >/dev/null; then
      actual="$(sha256sum "$coscli" | awk '{print $1}')"
    else
      actual="$(shasum -a 256 "$coscli" | awk '{print $1}')"
    fi
    if [[ "$actual" != "$expected" ]]; then
      echo "::error::coscli checksum mismatch: ${actual}" >&2
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

upload_one() {
  local path="$1"
  local name key job_cfg job_log rc
  name="$(basename "$path")"
  key="octop/release/${version}/${name}"
  job_cfg="${cfg}.${name}.yaml"
  job_log="${log_dir}/${name}"
  cp "$cfg" "$job_cfg"
  chmod 600 "$job_cfg"
  mkdir -p "$job_log"
  echo "Uploading ${name} -> ${key}"
  rc=0
  "$coscli" --disable-log --init-skip -c "$job_cfg" -e "$RELEASE_COS_ENDPOINT" \
    cp "$path" "cos://${RELEASE_COS_BUCKET}/${key}" \
    --acl public-read \
    --fail-output=false \
    --process-log=true \
    --process-log-path "$job_log" \
    --err-retry-num 3 \
    --err-retry-interval 2 || rc=$?
  rm -f "$job_cfg"
  if [[ "$rc" -ne 0 ]]; then
    echo "::error::upload failed for ${name}" >&2
  fi
  return "$rc"
}

follow_process_logs() {
  local seen="${work}/cos-followed-$$"
  local logfile
  : > "$seen"
  while [[ ! -f "$done_flag" ]]; do
    while IFS= read -r logfile; do
      [[ -n "$logfile" ]] || continue
      if grep -Fxq "$logfile" "$seen"; then
        continue
      fi
      printf '%s\n' "$logfile" >> "$seen"
      echo "---- ${logfile#"${log_dir}/"} ----"
      tail -n +1 -F "$logfile" &
    done < <(find "$log_dir" -type f | sort)
    sleep 2
  done
  sleep 1
  pkill -P "$BASHPID" tail || true
}

follow_process_logs &
follower_pid=$!

pids=()
for path in "${files[@]}"; do
  upload_one "$path" &
  pids+=("$!")
done

failed=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    failed=1
  fi
done
touch "$done_flag"
wait "$follower_pid" || true
if [[ "$failed" -ne 0 ]]; then
  echo "::error::one or more COS uploads failed" >&2
  exit 1
fi

echo "Uploaded ${#files[@]} files under ${public_base}/"
