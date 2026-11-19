#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor — Cluster OS Snapshot (TAT Layer 2B)
# ==============================================================================
# Purpose:  Collect a single-line health snapshot from a remote CVM via TAT.
#           Output is a KEY=VALUE line parsed by cluster_score.sh.
#
# Usage (local test):
#   bash scripts/cluster_os_snapshot.sh
#
# Usage (via TAT — encode on local machine, decode+run on remote CVM):
#   CONTENT=$(base64 -w 0 < scripts/cluster_os_snapshot.sh)
#   tccli tat RunCommand \
#     --region <region> \
#     --InstanceIds '["ins-xxx","ins-yyy","ins-zzz"]' \
#     --CommandType SHELL \
#     --Timeout 30 \
#     --Content "$CONTENT"
#
# Output format (one line, all fields space-separated KEY=VALUE):
#   HOST=order-api-1 LOAD=0.85 NCPU=4 MEM_MB=2048/8192 DISK_ROOT_PCT=55 SSH=active
#
# Fields:
#   HOST          - short hostname (hostname -s)
#   LOAD          - 1-minute load average from /proc/loadavg
#   NCPU          - logical CPU count (nproc)
#   MEM_MB        - memory: used_mb/total_mb (from free -m)
#   DISK_ROOT_PCT - root partition usage percentage (integer, no % symbol)
#   SSH           - systemd sshd service status (active/inactive/unknown)
# ==============================================================================

h=$(hostname -s 2>/dev/null || echo unknown)
l=$(awk '{print $1}' /proc/loadavg 2>/dev/null || echo -1)
c=$(nproc 2>/dev/null || echo 1)
m=$(free -m 2>/dev/null | awk '/Mem:/{printf "%.0f/%d",$3,$2}')
d=$(df / 2>/dev/null | awk 'NR==2{print $5}' | tr -d '%')
s=$(systemctl is-active sshd 2>/dev/null || echo unknown)

echo "HOST=$h LOAD=$l NCPU=$c MEM_MB=$m DISK_ROOT_PCT=$d SSH=$s"
