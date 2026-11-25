#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor — Cluster Deep CPU Analysis (via TAT)
# ==============================================================================
# Purpose:  Collect structured CPU diagnostic data from a remote CVM via TAT.
#           Output is plain text with section headers for LLM parsing.
#
# Usage (local test):
#   bash scripts/cluster_deep_cpu.sh
#
# Usage (via TAT — encode on local machine, decode+run on remote CVM):
#   CONTENT=$(base64 -w 0 < scripts/cluster_deep_cpu.sh)
#   tccli tat RunCommand \
#     --region <region> \
#     --InstanceIds '["ins-xxx"]' \
#     --CommandType SHELL \
#     --Timeout 60 \
#     --Content "$CONTENT"
#
# Duration: ~10s
# ==============================================================================

echo "=== HOST ==="
hostname -s 2>/dev/null || echo unknown

echo "=== TOP CPU CONSUMERS ==="
ps aux --sort=-%cpu 2>/dev/null | head -20 \
  || ps aux 2>/dev/null | sort -k3 -rn | head -20

echo "=== LOAD DETAIL ==="
top -bn1 2>/dev/null | head -30 || uptime

echo "=== CPU CORES ==="
nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null || echo 1

echo "=== LOAD AVERAGE ==="
cat /proc/loadavg 2>/dev/null || uptime

echo "=== CGROUP CPU STAT ==="
cat /sys/fs/cgroup/cpu/cpu.stat 2>/dev/null | head -5 \
  || cat /sys/fs/cgroup/cpu,cpuacct/cpu.stat 2>/dev/null | head -5 \
  || echo "no-cgroup"

echo "=== IO WAIT / VMSTAT ==="
# Pre-run vmstat once and cache; reused in CONTEXT SWITCHES to avoid a second 3s wait
vmstat_out=$(vmstat 1 3 2>/dev/null)
iostat -x 1 3 2>/dev/null | tail -20 \
  || { [ -n "$vmstat_out" ] && echo "$vmstat_out" || echo "iostat/vmstat not available"; }

echo "=== CONTEXT SWITCHES (VMSTAT) ==="
if [ -n "$vmstat_out" ]; then
  echo "$vmstat_out" | awk 'NR>2 {print "cs=" $12, "in=" $11, "us=" $13, "sy=" $14, "wa=" $16}'
else
  echo "vmstat not available"
fi
