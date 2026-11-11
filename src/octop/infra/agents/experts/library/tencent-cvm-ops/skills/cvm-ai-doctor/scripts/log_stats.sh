#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor Stats Logger
# ==============================================================================
# 统一的诊断记录写入器，所有路径 (patrol/手动/cron) 都写同一个文件
# Usage: bash scripts/log_stats.sh <mode> <scenario> <os> <duration_s> <cpu> <mem> <disk> <net> <trigger>
# Example: bash scripts/log_stats.sh quick health_check linux 8 ok ok warning ok user
# ==============================================================================

STATS_FILE="${HOME}/.lightclaw/stats/cvm-doctor.jsonl"
mkdir -p "$(dirname "$STATS_FILE")"

mode="${1:-quick}"
scenario="${2:-general}"
os_type="${3:-$(uname -s | tr '[:upper:]' '[:lower:]')}"
duration="${4:-0}"
cpu="${5:-skipped}"
mem="${6:-skipped}"
disk="${7:-skipped}"
net="${8:-skipped}"
trigger="${9:-user}"

issues=0
severity="ok"
for s in "$cpu" "$mem" "$disk" "$net"; do
  case "$s" in
    critical) issues=$((issues+1)); severity="critical" ;;
    warning)  issues=$((issues+1)); [ "$severity" != "critical" ] && severity="warning" ;;
  esac
done

ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ts_local=$(date '+%Y-%m-%d %H:%M:%S')
hostname_val=$(hostname 2>/dev/null || echo "unknown")

echo "{\"ts\":\"${ts}\",\"ts_local\":\"${ts_local}\",\"mode\":\"${mode}\",\"scenario\":\"${scenario}\",\"hostname\":\"${hostname_val}\",\"os\":\"${os_type}\",\"duration_s\":${duration},\"components\":{\"cpu\":{\"status\":\"${cpu}\",\"detail\":\"\"},\"memory\":{\"status\":\"${mem}\",\"detail\":\"\"},\"disk\":{\"status\":\"${disk}\",\"detail\":\"\"},\"network\":{\"status\":\"${net}\",\"detail\":\"\"}},\"issues_found\":${issues},\"severity\":\"${severity}\",\"trigger\":\"${trigger}\"}" >> "$STATS_FILE"
