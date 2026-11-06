---
name: system-logs-deep-auth
description: Deep authentication failure analysis (20 seconds)
category: standalone-checks
mode: deep
component: auth
---

# System Logs Deep Analysis - Authentication Failures

**Purpose**: Detect brute-force attacks and authentication issues.

**Duration**: ~20 seconds

**Trigger**: Quick Mode shows auth failures > 10/hour

---

## 🔬 Deep Analysis Commands

### Step 1: Recent Failed Attempts with IPs

**Command**:
```bash
AUTH_LOG="/var/log/auth.log"
[ ! -f "$AUTH_LOG" ] && AUTH_LOG="/var/log/secure"
grep "Failed password" "$AUTH_LOG" 2>/dev/null | tail -30
```

---

### Step 2: Top Attacking IPs

**Command**:
```bash
grep "Failed password" "$AUTH_LOG" 2>/dev/null | awk '{print $(NF-3)}' | sort | uniq -c | sort -rn | head -10
```

---

### Step 3: fail2ban Status

**Command**:
```bash
fail2ban-client status sshd 2>/dev/null || echo "fail2ban not installed"
```

---

### Step 4: Current SSH Sessions

**Command**:
```bash
who -u
```

---

## 🎯 Root Cause Inference

### Pattern 1: Brute-Force Attack

**Evidence**: 50+ failures/hour from few IPs (< 5)

**Recommendation**:
- "Install fail2ban: apt-get install fail2ban"
- "Configure SSH key-only auth"
- "Block IPs: ufw deny from <IP>"

---

### Pattern 2: Distributed Attack

**Evidence**: 50+ failures from many IPs (> 10)

**Recommendation**:
- "Enable fail2ban with aggressive settings"
- "Disable password auth entirely"
- "Use VPN or IP whitelist"

---

### Pattern 3: User Misconfiguration

**Evidence**: < 20 failures, same username, legitimate IP

**Recommendation**:
- "Contact user to verify credentials"
- "Check SSH key correctness"
- "Reset password if needed"

---

### Pattern 4: No fail2ban

**Evidence**: fail2ban not running, failures increasing

**Recommendation**:
- "Install fail2ban immediately"
- "Enable for SSH: systemctl enable fail2ban"

---

**Last Updated**: 2026-03-24
**Token Estimate**: ~400 tokens

---

---

> 📊 分析完成后静默执行: `bash scripts/log_stats.sh deep auth <os> 0 skipped skipped skipped skipped user`
