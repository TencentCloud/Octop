#!/usr/bin/env bash
set -euo pipefail

# Add Rtools to PATH if on Windows (needed for Stan/brms compilation)
if [[ -d "/c/rtools45/usr/bin" ]]; then
  export PATH="/c/rtools45/usr/bin:/c/rtools45/x86_64-w64-mingw32.static.posix/bin:$PATH"
fi

COMMAND="${1:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  echo "openclaw-r-stats"
  echo "Usage:"
  echo "  bash scripts/run-rstats.sh doctor"
  echo "  bash scripts/run-rstats.sh schema --data <file.csv>"
  echo "  bash scripts/run-rstats.sh analyze --spec <file.json>"
  exit 1
}

if [[ -z "${COMMAND}" ]]; then usage; fi

if ! command -v Rscript &>/dev/null; then
  echo "ERROR: Rscript not found on PATH."
  echo "Install R: https://cran.r-project.org/"
  exit 1
fi

case "${COMMAND}" in
  doctor)
    Rscript --vanilla "${ROOT_DIR}/scripts/doctor.R"
    ;;
  schema)
    if [[ "${2:-}" != "--data" || -z "${3:-}" ]]; then
      echo "Usage: bash scripts/run-rstats.sh schema --data <file.csv>"
      exit 1
    fi
    if [[ ! -f "${3}" ]]; then echo "ERROR: File not found: ${3}"; exit 1; fi
    Rscript --vanilla "${ROOT_DIR}/scripts/inspect_schema.R" "${3}"
    ;;
  analyze)
    if [[ "${2:-}" != "--spec" || -z "${3:-}" ]]; then
      echo "Usage: bash scripts/run-rstats.sh analyze --spec <file.json>"
      exit 1
    fi
    if [[ ! -f "${3}" ]]; then echo "ERROR: Spec not found: ${3}"; exit 1; fi
    RSTATS_ROOT="${ROOT_DIR}" Rscript --vanilla "${ROOT_DIR}/scripts/oc_rstats.R" "${3}"
    ;;
  *) usage ;;
esac
