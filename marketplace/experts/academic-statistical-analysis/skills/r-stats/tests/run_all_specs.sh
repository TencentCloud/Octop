#!/usr/bin/env bash
# Run all example specs and report pass/fail
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPECS_DIR="${ROOT_DIR}/examples/specs"
PASS=0; FAIL=0; ERRORS=""

# Add Rtools if on Windows
if [[ -d "/c/rtools45/usr/bin" ]]; then
  export PATH="/c/rtools45/usr/bin:/c/rtools45/x86_64-w64-mingw32.static.posix/bin:$PATH"
fi

for spec in "${SPECS_DIR}"/*.json; do
  name=$(basename "${spec}" .json)
  output_dir=$(Rscript --vanilla -e "cat(jsonlite::fromJSON('${spec}')[['output_dir']])")

  bash "${ROOT_DIR}/scripts/run-rstats.sh" analyze --spec "${spec}" >/dev/null 2>&1
  status=$(Rscript --vanilla -e "cat(jsonlite::fromJSON('${ROOT_DIR}/${output_dir}/summary.json')[['status']])" 2>/dev/null)

  if [[ "${status}" == "ok" ]]; then
    echo "PASS ${name}"
    ((PASS++))
  else
    echo "FAIL ${name}"
    ((FAIL++))
    ERRORS="${ERRORS}\n  ${name}: ${status}"
  fi
done

echo ""
echo "=== ${PASS} PASS, ${FAIL} FAIL ==="
if [[ ${FAIL} -gt 0 ]]; then
  echo -e "Failures:${ERRORS}"
  exit 1
fi
