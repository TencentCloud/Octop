#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor Deep Scan (Linux / macOS)
# ==============================================================================
# Purpose:  Collect raw diagnostic data for a given component and emit
#           structured JSON, so the LLM only needs to interpret — not run
#           commands one at a time.
#
# Usage:
#   bash scripts/deep_scan.sh <component> [--output json|text]
#   component: cpu | memory | disk | network | all
#
# Output:   JSON (default) or plain text suitable for LLM context
#
# Duration: cpu ~8s | memory ~20s | disk ~15s | network ~5s | all ~35s
# ==============================================================================

set -euo pipefail
IFS=$'\n\t'

COMPONENT="${1:-cpu}"
OUTPUT_FORMAT="json"
if [[ "${2:-}" == "--output" ]]; then
  OUTPUT_FORMAT="${3:-json}"
elif [[ "${2:-}" == "--output=text" ]]; then
  OUTPUT_FORMAT="text"
fi

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
START_TS=$(date +%s)

# Detect OS
OS="unknown"
if [[ "$(uname)" == "Darwin" ]]; then
  OS="macos"
elif [[ "$(uname)" == "Linux" ]]; then
  OS="linux"
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Run a command silently; return empty string on failure
safe_run() {
  local cmd="$*"
  eval "$cmd" 2>/dev/null || true
}

# Escape a string for JSON embedding
json_escape() {
  python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" 2>/dev/null \
    || sed 's/\\/\\\\/g; s/"/\\"/g; s/$/\\n/' | tr -d '\n' | sed 's/\\n$//'
}

# Produce a JSON key:"value" pair where value is a multi-line raw string
json_field() {
  local key="$1"
  local value="$2"
  printf '"%s": %s' "$key" "$(printf '%s' "$value" | json_escape)"
}

# ---------------------------------------------------------------------------
# Component: CPU
# ---------------------------------------------------------------------------

collect_cpu() {
  local top_consumers="" freq_info="" thermal_info="" load_info="" psi_info=""
  local load_1="" load_5="" load_15="" ncpu=""

  # Top CPU consumers
  if [[ "$OS" == "linux" ]]; then
    top_consumers=$(safe_run "ps aux --sort=-%cpu | head -20 | awk 'BEGIN {print \"PID\\tUSER\\tCPU%\\tMEM%\\tCOMMAND\"} NR>1 {printf \"%s\\t%s\\t%s%%\\t%s%%\\t%s\\n\", \$2, \$1, \$3, \$4, \$11}'")
  elif [[ "$OS" == "macos" ]]; then
    top_consumers=$(safe_run "ps aux -r | head -20 | awk 'BEGIN {print \"PID\\tUSER\\tCPU%\\tMEM%\\tCOMMAND\"} NR>1 {printf \"%s\\t%s\\t%s%%\\t%s%%\\t%s\\n\", \$2, \$1, \$3, \$4, \$11}'")
  fi

  # CPU frequency
  if [[ "$OS" == "linux" ]]; then
    freq_info=$(safe_run "grep 'MHz' /proc/cpuinfo | head -8")
  elif [[ "$OS" == "macos" ]]; then
    freq_info=$(safe_run "sysctl -n hw.cpufrequency hw.cpufrequency_max 2>/dev/null || sysctl hw.cpufrequency 2>/dev/null")
  fi

  # Thermal / throttling
  if [[ "$OS" == "linux" ]]; then
    local sensors_out=""
    if command -v sensors &>/dev/null; then
      sensors_out=$(safe_run "sensors | grep -E 'Core |Package' | head -8")
    fi
    local throttle_out=""
    throttle_out=$(safe_run "dmesg 2>/dev/null | tail -200 | grep -i 'thermal\\|throttle' | tail -5")
    thermal_info="${sensors_out}${throttle_out:+$'\n'$throttle_out}"
  elif [[ "$OS" == "macos" ]]; then
    # powermetrics requires root; attempt silently
    thermal_info=$(safe_run "sudo powermetrics -n 1 --samplers smc 2>/dev/null | grep -E 'CPU die temperature|Package' | head -5")
  fi

  # Load average
  local uptime_out=""
  uptime_out=$(safe_run "uptime")
  if [[ "$OS" == "linux" ]]; then
    ncpu=$(safe_run "nproc")
    local psi_cpu=""
    psi_cpu=$(safe_run "cat /proc/pressure/cpu 2>/dev/null")
    psi_info="$psi_cpu"
  elif [[ "$OS" == "macos" ]]; then
    ncpu=$(safe_run "sysctl -n hw.ncpu")
  fi
  ncpu="${ncpu:-1}"

  # Parse load values from uptime
  load_1=$(  printf '%s' "$uptime_out" | grep -oE 'load average[s]?:.*' | grep -oE '[0-9]+\.[0-9]+' | sed -n '1p' || true)
  load_5=$(  printf '%s' "$uptime_out" | grep -oE 'load average[s]?:.*' | grep -oE '[0-9]+\.[0-9]+' | sed -n '2p' || true)
  load_15=$( printf '%s' "$uptime_out" | grep -oE 'load average[s]?:.*' | grep -oE '[0-9]+\.[0-9]+' | sed -n '3p' || true)

  load_info="$uptime_out"

  # Context switches via vmstat (Linux only)
  local vmstat_out=""
  if [[ "$OS" == "linux" ]]; then
    vmstat_out=$(safe_run "vmstat 1 3 2>/dev/null")
  fi

  if [[ "$OUTPUT_FORMAT" == "json" ]]; then
    cat <<EOF
{
  "component": "cpu",
  "timestamp": "$TIMESTAMP",
  "os": "$OS",
  "summary": {
    "ncpu": $ncpu,
    "load_1min": "${load_1:-N/A}",
    "load_5min": "${load_5:-N/A}",
    "load_15min": "${load_15:-N/A}"
  },
  "data": {
    $(json_field "top_consumers" "$top_consumers"),
    $(json_field "cpu_frequency" "$freq_info"),
    $(json_field "thermal_throttling" "$thermal_info"),
    $(json_field "load_trend" "$load_info"),
    $(json_field "vmstat" "$vmstat_out"),
    $(json_field "psi" "$psi_info")
  }
}
EOF
  else
    echo "=== DEEP CPU SCAN ==="
    echo "OS: $OS | Cores: $ncpu | Load: ${load_1:-?}/${load_5:-?}/${load_15:-?}"
    echo ""
    echo "--- Top CPU Consumers ---"
    echo "$top_consumers"
    echo ""
    echo "--- CPU Frequency ---"
    echo "$freq_info"
    echo ""
    echo "--- Thermal / Throttling ---"
    echo "${thermal_info:-N/A}"
    echo ""
    echo "--- Load Trend ---"
    echo "$load_info"
    [[ -n "$vmstat_out" ]] && { echo ""; echo "--- VMstat ---"; echo "$vmstat_out"; }
    [[ -n "$psi_info" ]]   && { echo ""; echo "--- PSI (Pressure Stall) ---"; echo "$psi_info"; }
  fi
}

# ---------------------------------------------------------------------------
# Component: Memory
# ---------------------------------------------------------------------------

collect_memory() {
  local top_consumers="" swap_info="" vmstat_out="" psi_info=""
  local mem_leak_samples=""

  # Top memory consumers
  if [[ "$OS" == "linux" ]]; then
    top_consumers=$(safe_run "ps aux --sort=-%mem | head -20 | awk 'BEGIN {print \"PID\\tUSER\\tCPU%\\tMEM%\\tRSS(MB)\\tCOMMAND\"} NR>1 {printf \"%s\\t%s\\t%s%%\\t%s%%\\t%.1f\\t%s\\n\", \$2, \$1, \$3, \$4, \$6/1024, \$11}'")
  elif [[ "$OS" == "macos" ]]; then
    top_consumers=$(safe_run "ps aux -m | head -20 | awk 'BEGIN {print \"PID\\tUSER\\tCPU%\\tMEM%\\tRSS(MB)\\tCOMMAND\"} NR>1 {printf \"%s\\t%s\\t%s%%\\t%s%%\\t%.1f\\t%s\\n\", \$2, \$1, \$3, \$4, \$6/1024, \$11}'")
  fi

  # Memory leak sample (3 samples × 5s = 15s total)
  echo "[deep_scan] Sampling memory (3x5s)..." >&2
  local sample_result=""
  for i in 1 2 3; do
    local snap=""
    if [[ "$OS" == "linux" ]]; then
      snap=$(safe_run "ps aux --sort=-%mem | head -5 | awk 'NR>1 {printf \"  PID %s: RSS %.1fMB (%s)\\n\", \$2, \$6/1024, \$11}'")
    elif [[ "$OS" == "macos" ]]; then
      snap=$(safe_run "ps aux -m | head -5 | awk 'NR>1 {printf \"  PID %s: RSS %.1fMB (%s)\\n\", \$2, \$6/1024, \$11}'")
    fi
    sample_result+="Sample $i (t=$((i*5-5))s):"$'\n'"$snap"$'\n'
    [[ $i -lt 3 ]] && sleep 5
  done
  mem_leak_samples="$sample_result"

  # Swap / page activity
  if [[ "$OS" == "linux" ]]; then
    local free_out=""
    free_out=$(safe_run "free -h")
    vmstat_out=$(safe_run "vmstat 1 5 2>/dev/null | awk 'BEGIN {print \"Time\\tSwapIn\\tSwapOut\"} NR>2 {print NR-2 \"\\t\" \$7 \"\\t\" \$8}'")
    swap_info="${free_out}"$'\n\n'"vmstat swap columns (si/so):"$'\n'"${vmstat_out}"
    psi_info=$(safe_run "cat /proc/pressure/memory 2>/dev/null")
  elif [[ "$OS" == "macos" ]]; then
    swap_info=$(safe_run "sysctl vm.swapusage 2>/dev/null")
    swap_info+=$'\n'$(safe_run "vm_stat | grep -E 'Pages (active|inactive|wired|free|swapped)' 2>/dev/null")
  fi

  if [[ "$OUTPUT_FORMAT" == "json" ]]; then
    cat <<EOF
{
  "component": "memory",
  "timestamp": "$TIMESTAMP",
  "os": "$OS",
  "data": {
    $(json_field "top_consumers" "$top_consumers"),
    $(json_field "memory_leak_samples" "$mem_leak_samples"),
    $(json_field "swap_info" "$swap_info"),
    $(json_field "psi" "$psi_info")
  }
}
EOF
  else
    echo "=== DEEP MEMORY SCAN ==="
    echo "OS: $OS"
    echo ""
    echo "--- Top Memory Consumers ---"
    echo "$top_consumers"
    echo ""
    echo "--- Memory Leak Detection (3 samples × 5s) ---"
    echo "$mem_leak_samples"
    echo ""
    echo "--- Swap / Page Activity ---"
    echo "$swap_info"
    [[ -n "$psi_info" ]] && { echo ""; echo "--- PSI (Memory Pressure) ---"; echo "$psi_info"; }
  fi
}

# ---------------------------------------------------------------------------
# Component: Disk
# ---------------------------------------------------------------------------

collect_disk() {
  local io_processes="" iostat_out="" df_out="" smart_out=""

  # I/O-heavy processes
  echo "[deep_scan] Collecting disk I/O metrics..." >&2
  if [[ "$OS" == "linux" ]]; then
    if command -v iotop &>/dev/null; then
      io_processes=$(safe_run "sudo iotop -b -n 1 -o 2>/dev/null | head -15" || safe_run "iotop -b -n 1 -o 2>/dev/null | head -15")
    fi
    if [[ -z "$io_processes" ]] && command -v pidstat &>/dev/null; then
      io_processes=$(safe_run "pidstat -d 1 3 2>/dev/null | tail -20")
    fi
    if [[ -z "$io_processes" ]]; then
      io_processes="iotop/pidstat not available; install sysstat for detailed I/O analysis"
    fi
  elif [[ "$OS" == "macos" ]]; then
    io_processes=$(safe_run "iostat -d 1 3 2>/dev/null")
    [[ -z "$io_processes" ]] && io_processes="iostat -d not available on this macOS version"
  fi

  # Disk queue and latency (iostat -x, Linux only)
  if [[ "$OS" == "linux" ]]; then
    iostat_out=$(safe_run "iostat -x 1 5 2>/dev/null | awk 'BEGIN {print \"Device\\tUtil%\\tAvgQu\\tr_await\\tw_await\"} /^[sv]d[a-z]/ {printf \"%s\\t%.1f%%\\t%.2f\\t%.1fms\\t%.1fms\\n\", \$1, \$14, \$9, \$10, \$11}'" \
                || safe_run "iostat -x 1 5 2>/dev/null")
    [[ -z "$iostat_out" ]] && iostat_out="iostat not available; install sysstat"
  elif [[ "$OS" == "macos" ]]; then
    iostat_out=$(safe_run "iostat -d -c 5 2>/dev/null")
  fi

  # Disk usage
  df_out=$(safe_run "df -h 2>/dev/null")

  # SMART health (Linux, best-effort)
  if [[ "$OS" == "linux" ]] && command -v smartctl &>/dev/null; then
    local smart_results=""
    for dev in /dev/sda /dev/sdb /dev/sdc /dev/nvme0 /dev/vda; do
      if [[ -b "$dev" ]]; then
        local health=""
        health=$(safe_run "sudo smartctl -H $dev 2>/dev/null | grep -E 'SMART overall|test result'")
        [[ -n "$health" ]] && smart_results+="${dev}: ${health}"$'\n'
      fi
    done
    smart_out="${smart_results:-smartctl: no supported block devices found}"
  else
    smart_out="smartctl not available (install smartmontools for SMART health checks)"
  fi

  # PSI (Linux)
  local psi_info=""
  if [[ "$OS" == "linux" ]]; then
    psi_info=$(safe_run "cat /proc/pressure/io 2>/dev/null")
  fi

  if [[ "$OUTPUT_FORMAT" == "json" ]]; then
    cat <<EOF
{
  "component": "disk",
  "timestamp": "$TIMESTAMP",
  "os": "$OS",
  "data": {
    $(json_field "io_processes" "$io_processes"),
    $(json_field "iostat" "$iostat_out"),
    $(json_field "disk_usage" "$df_out"),
    $(json_field "smart_health" "$smart_out"),
    $(json_field "psi" "$psi_info")
  }
}
EOF
  else
    echo "=== DEEP DISK SCAN ==="
    echo "OS: $OS"
    echo ""
    echo "--- I/O-Heavy Processes ---"
    echo "$io_processes"
    echo ""
    echo "--- Disk Queue / Latency (iostat) ---"
    echo "$iostat_out"
    echo ""
    echo "--- Disk Usage ---"
    echo "$df_out"
    echo ""
    echo "--- SMART Health ---"
    echo "$smart_out"
    [[ -n "$psi_info" ]] && { echo ""; echo "--- PSI (I/O Pressure) ---"; echo "$psi_info"; }
  fi
}

# ---------------------------------------------------------------------------
# Component: Network
# ---------------------------------------------------------------------------

collect_network() {
  local iface_stats="" conn_stats="" bw_info=""

  echo "[deep_scan] Collecting network metrics..." >&2

  # Interface statistics
  if [[ "$OS" == "linux" ]]; then
    iface_stats=$(safe_run "ip -s link show 2>/dev/null")
  elif [[ "$OS" == "macos" ]]; then
    iface_stats=$(safe_run "netstat -i -b 2>/dev/null | awk 'NR>1 {print \$1 \"\\tRX_err:\" \$6 \" TX_err:\" \$9 \" Drops:\" \$8+\$11}'")
  fi

  # Connection saturation
  if [[ "$OS" == "linux" ]]; then
    local ss_out="" drop_out=""
    ss_out=$(safe_run "ss -s 2>/dev/null")
    drop_out=$(safe_run "netstat -s 2>/dev/null | grep -E 'overflow|drop|failed' | head -10")
    conn_stats="${ss_out}"$'\n\n'"Error/Drop counters:"$'\n'"${drop_out}"
  elif [[ "$OS" == "macos" ]]; then
    conn_stats=$(safe_run "netstat -s 2>/dev/null | grep -E 'overflow|drop|fail|retransmit' | head -15")
  fi

  # Bandwidth utilization (1-second delta)
  if [[ "$OS" == "linux" ]]; then
    local bw_lines=""
    for iface in $(ip -o link show 2>/dev/null | awk -F': ' '{print $2}' | grep -v '^lo$'); do
      local rx1 tx1 rx2 tx2
      rx1=$(cat "/sys/class/net/$iface/statistics/rx_bytes" 2>/dev/null || echo 0)
      tx1=$(cat "/sys/class/net/$iface/statistics/tx_bytes" 2>/dev/null || echo 0)
      sleep 1
      rx2=$(cat "/sys/class/net/$iface/statistics/rx_bytes" 2>/dev/null || echo 0)
      tx2=$(cat "/sys/class/net/$iface/statistics/tx_bytes" 2>/dev/null || echo 0)
      local rx_kbps=$(( (rx2 - rx1) / 1024 ))
      local tx_kbps=$(( (tx2 - tx1) / 1024 ))
      bw_lines+="${iface}: RX ${rx_kbps}KB/s  TX ${tx_kbps}KB/s"$'\n'
    done
    bw_info="$bw_lines"
  elif [[ "$OS" == "macos" ]]; then
    bw_info=$(safe_run "netstat -i -b -w 1 2>/dev/null | head -10")
  fi

  if [[ "$OUTPUT_FORMAT" == "json" ]]; then
    cat <<EOF
{
  "component": "network",
  "timestamp": "$TIMESTAMP",
  "os": "$OS",
  "data": {
    $(json_field "interface_stats" "$iface_stats"),
    $(json_field "connection_stats" "$conn_stats"),
    $(json_field "bandwidth_utilization" "$bw_info")
  }
}
EOF
  else
    echo "=== DEEP NETWORK SCAN ==="
    echo "OS: $OS"
    echo ""
    echo "--- Interface Statistics ---"
    echo "$iface_stats"
    echo ""
    echo "--- Connection Saturation ---"
    echo "$conn_stats"
    echo ""
    echo "--- Bandwidth Utilization (1s sample) ---"
    echo "$bw_info"
  fi
}

# ---------------------------------------------------------------------------
# Component: All — combine all components into a single JSON envelope
# ---------------------------------------------------------------------------

collect_all() {
  local cpu_json mem_json disk_json net_json

  # Force JSON output for sub-collections, capture separately
  OUTPUT_FORMAT="json"

  echo "[deep_scan] Starting full scan (cpu + memory + disk + network)..." >&2

  cpu_json=$(collect_cpu)
  mem_json=$(collect_memory)
  disk_json=$(collect_disk)
  net_json=$(collect_network)

  local end_ts duration
  end_ts=$(date +%s)
  duration=$(( end_ts - START_TS ))

  cat <<EOF
{
  "component": "all",
  "timestamp": "$TIMESTAMP",
  "os": "$OS",
  "duration_s": $duration,
  "cpu": $cpu_json,
  "memory": $mem_json,
  "disk": $disk_json,
  "network": $net_json
}
EOF
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

case "$COMPONENT" in
  cpu)     collect_cpu     ;;
  memory)  collect_memory  ;;
  disk)    collect_disk    ;;
  network) collect_network ;;
  all)     collect_all     ;;
  *)
    echo "Usage: bash scripts/deep_scan.sh <cpu|memory|disk|network|all> [--output json|text]" >&2
    exit 1
    ;;
esac
