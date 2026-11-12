#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor Combined Analysis Decision Tree
# ==============================================================================
# Purpose:  Implement the 5-branch root cause decision tree from
#           references/resource-saturation-deep-combined.md
#           Converts pure threshold logic to deterministic script output,
#           so the LLM only needs to narrate the pre-classified result.
#
# Usage:
#   bash scripts/combined_analysis.sh \
#     --mem-pct 92 --swap-gb 2.3 --iowait 25 \
#     --cpu-pct 85 --load-ratio 2.2 \
#     --disk-pct 78 \
#     --sys-pct 45 --net-throughput-mbps 900 --user-pct 15 \
#     --cpu-freq-ratio 0.72 --cpu-temp 84
#
# All flags are optional; unset / undetectable values default to 0.
# Output: JSON with branch classification, matched conditions, and
#         recommended deep-dive reference files.
# ==============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
MEM_PCT=0
SWAP_GB=0
IOWAIT=0
CPU_PCT=0
LOAD_RATIO=0
DISK_PCT=0
SYS_PCT=0
NET_THROUGHPUT=0   # Mbps
USER_PCT=0
CPU_FREQ_RATIO=1.0  # current / nominal (1.0 = no throttle)
CPU_TEMP=0         # °C

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mem-pct)           MEM_PCT="$2";          shift 2 ;;
    --swap-gb)           SWAP_GB="$2";          shift 2 ;;
    --iowait)            IOWAIT="$2";           shift 2 ;;
    --cpu-pct)           CPU_PCT="$2";          shift 2 ;;
    --load-ratio)        LOAD_RATIO="$2";       shift 2 ;;
    --disk-pct)          DISK_PCT="$2";         shift 2 ;;
    --sys-pct)           SYS_PCT="$2";          shift 2 ;;
    --net-throughput-mbps) NET_THROUGHPUT="$2"; shift 2 ;;
    --user-pct)          USER_PCT="$2";         shift 2 ;;
    --cpu-freq-ratio)    CPU_FREQ_RATIO="$2";   shift 2 ;;
    --cpu-temp)          CPU_TEMP="$2";         shift 2 ;;
    *)
      echo "Unknown flag: $1" >&2
      echo "Usage: bash scripts/combined_analysis.sh [--mem-pct N] [--swap-gb N] [--iowait N]" >&2
      echo "       [--cpu-pct N] [--load-ratio N] [--disk-pct N]" >&2
      echo "       [--sys-pct N] [--net-throughput-mbps N] [--user-pct N]" >&2
      echo "       [--cpu-freq-ratio N] [--cpu-temp N]" >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Float comparison helpers
# ---------------------------------------------------------------------------
float_gte() { awk "BEGIN {exit !($1 >= $2)}"; }
float_gt()  { awk "BEGIN {exit !($1 > $2)}"; }
float_lt()  { awk "BEGIN {exit !($1 < $2)}"; }

# ---------------------------------------------------------------------------
# Decision tree
# ---------------------------------------------------------------------------

BRANCH=0
ROOT_CAUSE="unknown"
LABEL=""
CONFIDENCE="LOW"
declare -a MATCHED=()
declare -a RECOMMENDED=()
declare -a WRONG_FIX=()

# ── Branch 1: Memory-Triggered Cascade ────────────────────────────────────
# IF mem >= 90% AND swap > 1GB AND iowait > 20%
B1_conds=()
B1_ok=true

float_gte "$MEM_PCT" "90"   && B1_conds+=("mem_pct>=${MEM_PCT}>=90%")   || { B1_ok=false; }
float_gt  "$SWAP_GB" "1.0"  && B1_conds+=("swap_gb=${SWAP_GB}>1GB")     || { B1_ok=false; }
float_gt  "$IOWAIT"  "20"   && B1_conds+=("iowait=${IOWAIT}%>20%")      || { B1_ok=false; }

if $B1_ok; then
  BRANCH=1
  ROOT_CAUSE="memory_cascade_to_disk_thrash"
  LABEL="内存不足导致磁盘换页雪崩 (Memory shortage cascading to disk thrashing)"
  CONFIDENCE="HIGH"
  MATCHED=("${B1_conds[@]}")
  RECOMMENDED=("references/resource-saturation-deep-memory.md" "references/resource-saturation-deep-disk.md")
  WRONG_FIX=("Adding CPU will not help — the root cause is memory, not compute capacity")
fi

# ── Branch 2: CPU Bottleneck ───────────────────────────────────────────────
# IF cpu > 80% AND load_ratio > 2.0 AND mem < 70%
if [[ $BRANCH -eq 0 ]]; then
  B2_conds=()
  B2_ok=true

  float_gt  "$CPU_PCT"    "80"  && B2_conds+=("cpu_pct=${CPU_PCT}%>80%")      || { B2_ok=false; }
  float_gt  "$LOAD_RATIO" "2.0" && B2_conds+=("load_ratio=${LOAD_RATIO}>2.0") || { B2_ok=false; }
  float_lt  "$MEM_PCT"    "70"  && B2_conds+=("mem_pct=${MEM_PCT}%<70%")      || { B2_ok=false; }

  if $B2_ok; then
    BRANCH=2
    ROOT_CAUSE="cpu_bottleneck"
    LABEL="CPU 瓶颈（计算资源不足） (CPU bottleneck — insufficient compute capacity)"
    CONFIDENCE="HIGH"
    MATCHED=("${B2_conds[@]}")
    RECOMMENDED=("references/resource-saturation-deep-cpu.md")
    WRONG_FIX=("Adding RAM will not help if memory is already OK")
  fi
fi

# ── Branch 3: Disk I/O Cascade ────────────────────────────────────────────
# IF disk_pct > 90% AND iowait > 30% AND mem < 80% AND swap < 0.5GB
if [[ $BRANCH -eq 0 ]]; then
  B3_conds=()
  B3_ok=true

  float_gt  "$DISK_PCT"  "90"  && B3_conds+=("disk_pct=${DISK_PCT}%>90%")  || { B3_ok=false; }
  float_gt  "$IOWAIT"    "30"  && B3_conds+=("iowait=${IOWAIT}%>30%")      || { B3_ok=false; }
  float_lt  "$MEM_PCT"   "80"  && B3_conds+=("mem_pct=${MEM_PCT}%<80%")    || { B3_ok=false; }
  float_lt  "$SWAP_GB"   "0.5" && B3_conds+=("swap_gb=${SWAP_GB}<0.5GB")   || { B3_ok=false; }

  if $B3_ok; then
    BRANCH=3
    ROOT_CAUSE="disk_io_bottleneck"
    LABEL="磁盘 I/O 瓶颈（存储过载） (Disk bottleneck — slow storage or excessive I/O)"
    CONFIDENCE="HIGH"
    MATCHED=("${B3_conds[@]}")
    RECOMMENDED=("references/resource-saturation-deep-disk.md")
    WRONG_FIX=("Adding CPU or RAM will not fix a disk I/O bottleneck")
  fi
fi

# ── Branch 4: Network Interrupt Storm ─────────────────────────────────────
# IF sys% > 40% AND net_throughput high (>500Mbps proxy) AND user% < 30%
if [[ $BRANCH -eq 0 ]]; then
  B4_conds=()
  B4_ok=true

  float_gt "$SYS_PCT"       "40"   && B4_conds+=("sys_pct=${SYS_PCT}%>40%")               || { B4_ok=false; }
  float_gt "$NET_THROUGHPUT" "500"  && B4_conds+=("net_throughput=${NET_THROUGHPUT}Mbps>500") || { B4_ok=false; }
  float_lt "$USER_PCT"      "30"   && B4_conds+=("user_pct=${USER_PCT}%<30%")              || { B4_ok=false; }

  if $B4_ok; then
    BRANCH=4
    ROOT_CAUSE="network_interrupt_storm"
    LABEL="网络中断风暴使内核过载 (Network interrupt storm overloading kernel)"
    CONFIDENCE="MEDIUM"
    MATCHED=("${B4_conds[@]}")
    RECOMMENDED=("references/resource-saturation-deep-network.md" "references/resource-saturation-deep-cpu.md")
    WRONG_FIX=("Killing user processes will not help — they are not the bottleneck (kernel sys% is)")
  fi
fi

# ── Branch 5: Thermal Throttling ──────────────────────────────────────────
# IF cpu_freq_ratio < 0.80 AND cpu_temp > 80°C AND load > 0 (cpu busy)
if [[ $BRANCH -eq 0 ]]; then
  B5_conds=()
  B5_ok=true

  float_lt "$CPU_FREQ_RATIO" "0.80" && B5_conds+=("cpu_freq_ratio=${CPU_FREQ_RATIO}<0.80 (throttled)") || { B5_ok=false; }
  float_gt "$CPU_TEMP"       "80"   && B5_conds+=("cpu_temp=${CPU_TEMP}°C>80°C")                       || { B5_ok=false; }
  float_gt "$LOAD_RATIO"     "0"    && B5_conds+=("load_ratio=${LOAD_RATIO}>0 (load present)")         || { B5_ok=false; }

  if $B5_ok; then
    BRANCH=5
    ROOT_CAUSE="thermal_throttling"
    LABEL="热节流降频导致性能下降 (Thermal throttling reducing CPU performance)"
    CONFIDENCE="HIGH"
    MATCHED=("${B5_conds[@]}")
    RECOMMENDED=("references/resource-saturation-deep-cpu.md")
    WRONG_FIX=("Software optimization will not fix a hardware thermal problem")
  fi
fi

# ── No branch matched ─────────────────────────────────────────────────────
if [[ $BRANCH -eq 0 ]]; then
  ROOT_CAUSE="no_clear_pattern"
  LABEL="无明确组合根因（需手动深度分析） (No clear multi-component pattern matched)"
  CONFIDENCE="LOW"
  MATCHED=()
  RECOMMENDED=(
    "references/resource-saturation-deep-cpu.md"
    "references/resource-saturation-deep-memory.md"
    "references/resource-saturation-deep-disk.md"
    "references/resource-saturation-deep-network.md"
  )
  WRONG_FIX=()
fi

# ---------------------------------------------------------------------------
# Emit JSON
# ---------------------------------------------------------------------------

# Build matched_conditions array
matched_json="["
first=true
for c in "${MATCHED[@]+"${MATCHED[@]}"}"; do
  $first || matched_json+=","
  matched_json+="\"$c\""
  first=false
done
matched_json+="]"

# Build recommended_depth array
rec_json="["
first=true
for r in "${RECOMMENDED[@]+"${RECOMMENDED[@]}"}"; do
  $first || rec_json+=","
  rec_json+="\"$r\""
  first=false
done
rec_json+="]"

# Build wrong_fix array
wf_json="["
first=true
for w in "${WRONG_FIX[@]+"${WRONG_FIX[@]}"}"; do
  $first || wf_json+=","
  wf_json+="\"$w\""
  first=false
done
wf_json+="]"

cat <<EOF
{
  "branch": $BRANCH,
  "root_cause": "$ROOT_CAUSE",
  "label": "$LABEL",
  "confidence": "$CONFIDENCE",
  "matched_conditions": $matched_json,
  "recommended_depth": $rec_json,
  "wrong_fix": $wf_json,
  "input": {
    "mem_pct": $MEM_PCT,
    "swap_gb": $SWAP_GB,
    "iowait": $IOWAIT,
    "cpu_pct": $CPU_PCT,
    "load_ratio": $LOAD_RATIO,
    "disk_pct": $DISK_PCT,
    "sys_pct": $SYS_PCT,
    "net_throughput_mbps": $NET_THROUGHPUT,
    "user_pct": $USER_PCT,
    "cpu_freq_ratio": $CPU_FREQ_RATIO,
    "cpu_temp": $CPU_TEMP
  }
}
EOF
