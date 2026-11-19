#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor — Cluster Deep Disk Analysis (via TAT)
# ==============================================================================
# Purpose:  Collect structured disk diagnostic data from a remote CVM via TAT.
#           Output is plain text with section headers for LLM parsing.
#
# Usage (local test):
#   bash scripts/cluster_deep_disk.sh
#
# Usage (via TAT — encode on local machine, decode+run on remote CVM):
#   CONTENT=$(base64 -w 0 < scripts/cluster_deep_disk.sh)
#   tccli tat RunCommand \
#     --region <region> \
#     --InstanceIds '["ins-xxx"]' \
#     --CommandType SHELL \
#     --Timeout 90 \
#     --Content "$CONTENT"
#
# Duration: ~10s (find bounded by 30s timeout; -xdev avoids crossing mount points)
# ==============================================================================

echo "=== HOST ==="
hostname -s 2>/dev/null || echo unknown

echo "=== DISK USAGE ==="
df -h 2>/dev/null

echo "=== INODE USAGE ==="
df -i 2>/dev/null | head -10

echo "=== TOP DIRECTORIES BY SIZE ==="
du -sh /var/log/* /home/* /tmp/* /opt/* /data/* 2>/dev/null \
  | sort -hr | head -20 \
  || echo "du not available or directories empty"

echo "=== LARGE FILES (>500MB) ==="
timeout 30 find / -maxdepth 5 -xdev -type f -size +500M 2>/dev/null | head -15 \
  || echo "find timed out or no large files"

echo "=== DISK IO STATS ==="
iostat -x 1 3 2>/dev/null | tail -20 || echo "iostat not available"

echo "=== IO WAIT PROCESSES ==="
# Show top IO-consuming processes if iotop available
if command -v iotop &>/dev/null; then
  iotop -b -n 1 -o 2>/dev/null | head -15
elif command -v pidstat &>/dev/null; then
  pidstat -d 1 3 2>/dev/null | tail -20
else
  echo "iotop/pidstat not available (install sysstat)"
fi

echo "=== LOGROTATE STATUS ==="
logrotate --debug /etc/logrotate.conf 2>&1 | grep -E 'rotating|state|error|last' | tail -20 \
  || echo "logrotate not available or /etc/logrotate.conf not found"
