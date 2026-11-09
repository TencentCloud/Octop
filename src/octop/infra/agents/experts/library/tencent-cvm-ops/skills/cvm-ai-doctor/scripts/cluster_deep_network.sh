#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor — Cluster Deep Network Analysis (via TAT)
# ==============================================================================
# Purpose:  Collect structured network diagnostic data from a remote CVM via TAT.
#           Output is plain text with section headers for LLM parsing.
#
# Usage (local test):
#   bash scripts/cluster_deep_network.sh
#
# Usage (via TAT — encode on local machine, decode+run on remote CVM):
#   CONTENT=$(base64 -w 0 < scripts/cluster_deep_network.sh)
#   tccli tat RunCommand \
#     --region <region> \
#     --InstanceIds '["ins-xxx"]' \
#     --CommandType SHELL \
#     --Timeout 30 \
#     --Content "$CONTENT"
#
# Duration: ~5s
# ==============================================================================

echo "=== HOST ==="
hostname -s 2>/dev/null || echo unknown

echo "=== CONNECTION SUMMARY ==="
ss -s 2>/dev/null || netstat -s 2>/dev/null | head -30 || echo "ss/netstat not available"

echo "=== ESTABLISHED CONNECTIONS COUNT ==="
echo "ESTABLISHED: $(ss -nt state ESTABLISHED 2>/dev/null | wc -l)"
echo "CLOSE_WAIT:  $(ss -nt state CLOSE-WAIT 2>/dev/null | wc -l)"
echo "TIME_WAIT:   $(ss -nt state TIME-WAIT 2>/dev/null | wc -l)"
echo "FIN_WAIT1:   $(ss -nt state FIN-WAIT-1 2>/dev/null | wc -l)"

echo "=== TOP CONNECTIONS BY REMOTE HOST ==="
ss -nt state ESTABLISHED 2>/dev/null \
  | awk 'NR>1 {print $5}' | cut -d: -f1 | sort | uniq -c | sort -rn | head -15 \
  || echo "ss not available"

echo "=== INTERFACE STATS ==="
ip -s link show 2>/dev/null \
  || netstat -i -b 2>/dev/null \
  || echo "ip/netstat not available"

echo "=== NETWORK ERRORS ==="
ip -s link show 2>/dev/null | grep -A2 'errors:' \
  || netstat -s 2>/dev/null | grep -E 'overflow|drop|failed|error|retransmit' | head -15 \
  || echo "no error stats available"

echo "=== ROUTING TABLE ==="
ip route show 2>/dev/null | head -10 \
  || route -n 2>/dev/null | head -10 \
  || echo "routing table not available"

echo "=== DNS RESOLUTION TEST ==="
time dig +short +time=3 +tries=1 www.tencentcloud.com 2>/dev/null \
  || time nslookup -timeout=3 www.tencentcloud.com 2>/dev/null \
  || echo "DNS test tools not available"
