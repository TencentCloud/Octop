#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor — Cluster Deep Memory Analysis (via TAT)
# ==============================================================================
# Purpose:  Collect structured memory diagnostic data from a remote CVM via TAT.
#           Output is plain text with section headers for LLM parsing.
#
# Usage (local test):
#   bash scripts/cluster_deep_memory.sh
#
# Usage (via TAT — encode on local machine, decode+run on remote CVM):
#   CONTENT=$(base64 -w 0 < scripts/cluster_deep_memory.sh)
#   tccli tat RunCommand \
#     --region <region> \
#     --InstanceIds '["ins-xxx"]' \
#     --CommandType SHELL \
#     --Timeout 60 \
#     --Content "$CONTENT"
#
# Duration: ~5s
# ==============================================================================

echo "=== HOST ==="
hostname -s 2>/dev/null || echo unknown

echo "=== TOP MEMORY CONSUMERS ==="
ps aux --sort=-%mem 2>/dev/null | head -20 \
  || ps aux 2>/dev/null | sort -k4 -rn | head -20

echo "=== MEMORY OVERVIEW ==="
free -m 2>/dev/null || cat /proc/meminfo 2>/dev/null | grep -E 'MemTotal|MemFree|MemAvailable'

echo "=== MEMINFO DETAIL ==="
cat /proc/meminfo 2>/dev/null \
  | grep -E 'MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapTotal|SwapFree|Shmem|Dirty|Writeback|AnonPages|Mapped' \
  || echo "no /proc/meminfo"

echo "=== OOM KILL HISTORY ==="
dmesg 2>/dev/null | grep -i 'oom\|killed\|out of memory' | tail -10 \
  || echo "no OOM records in dmesg"

echo "=== SWAP STATUS ==="
swapon --show 2>/dev/null || cat /proc/swaps 2>/dev/null || echo "no swap info"

echo "=== SWAP ACTIVITY (VMSTAT) ==="
vmstat 1 3 2>/dev/null | awk 'NR>1 {print "si=" $7, "so=" $8}' \
  || echo "vmstat not available"

echo "=== SLAB / KERNEL MEMORY ==="
cat /proc/meminfo 2>/dev/null | grep -E 'Slab|KernelStack|PageTables' || echo "no slab info"
