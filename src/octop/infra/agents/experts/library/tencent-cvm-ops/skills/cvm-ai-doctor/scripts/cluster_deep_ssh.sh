#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor — Cluster Deep SSH Analysis (via TAT)
# ==============================================================================
# Purpose:  Collect structured SSH/sshd diagnostic data from a remote CVM via TAT.
#           Output is plain text with section headers for LLM parsing.
#
# Usage (local test):
#   bash scripts/cluster_deep_ssh.sh
#
# Usage (via TAT — encode on local machine, decode+run on remote CVM):
#   CONTENT=$(base64 -w 0 < scripts/cluster_deep_ssh.sh)
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

echo "=== SSHD SERVICE STATUS ==="
systemctl status sshd --no-pager -l 2>/dev/null \
  || systemctl status ssh --no-pager -l 2>/dev/null \
  || service ssh status 2>/dev/null \
  || echo "systemctl/service not available"

echo "=== SSHD LISTENING PORTS ==="
ss -tlnp 2>/dev/null | grep -E ':22|:2222' \
  || netstat -tlnp 2>/dev/null | grep -E ':22|:2222' \
  || echo "ss/netstat not available"

echo "=== RECENT SSHD LOGS (last 50 lines) ==="
journalctl -u sshd -n 50 --no-pager 2>/dev/null \
  || journalctl -u ssh -n 50 --no-pager 2>/dev/null \
  || tail -50 /var/log/auth.log 2>/dev/null \
  || tail -50 /var/log/secure 2>/dev/null \
  || echo "no sshd logs found"

echo "=== SSHD CONFIG (key lines) ==="
grep -E '^(Port|PermitRootLogin|PasswordAuthentication|PubkeyAuthentication|AllowUsers|DenyUsers|MaxSessions|MaxStartups)' \
  /etc/ssh/sshd_config 2>/dev/null \
  || echo "/etc/ssh/sshd_config not readable"

echo "=== FAILED SSH ATTEMPTS (last 20) ==="
journalctl -u sshd --no-pager 2>/dev/null | grep -i 'failed\|invalid\|refused' | tail -20 \
  || grep -E 'Failed|Invalid|refused' /var/log/auth.log 2>/dev/null | tail -20 \
  || grep -E 'Failed|Invalid|refused' /var/log/secure 2>/dev/null | tail -20 \
  || echo "no failure records found"
