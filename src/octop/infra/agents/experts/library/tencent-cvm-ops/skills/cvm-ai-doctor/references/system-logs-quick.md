---
name: system-logs-quick
description: Fast error count across 5 categories (10 seconds) - kernel, OOM, FS, auth, services
category: standalone-checks
mode: quick
---

# System Logs Quick Check

**Purpose**: Rapid error count across 5 categories - triage in 10 seconds.

**Based on**: Brendan Gregg's USE Method (Errors dimension) + Google SRE error rate monitoring

---

## 🎯 AI Usage Guide

### Quick Mode Workflow

```yaml
purpose: Fast triage to identify which log categories need deep analysis
duration: ~10 seconds
checks: 5 (Kernel, OOM, FS, Auth, Services)

execution_steps:
  1. Run 5 quick check commands below
  2. Compare each result against thresholds
  3. Classify status: OK | WARNING | CRITICAL
  4. Recommend Deep analysis for WARNING/CRITICAL categories

output_format:
  findings:
    kernel: {count: N, status: OK/WARNING/CRITICAL}
    oom: {count: N, status: OK/WARNING/CRITICAL}
    fs: {count: N, status: OK/WARNING/CRITICAL}
    auth: {count: N, status: OK/WARNING/CRITICAL}
    service: {count: N, status: OK/WARNING/CRITICAL}
  deep_recommended: [list of categories needing deep analysis]
```

---

## ⚡ Quick Check Commands

### 1. Kernel Errors Count

**Command**:
```bash
# Linux
dmesg -l err,crit,alert,emerg 2>/dev/null | wc -l

# macOS
log show --predicate 'messageType == error' --last 1h 2>/dev/null | wc -l

# Windows (PowerShell)
(Get-EventLog -LogName System -EntryType Error -Newest 50 -ErrorAction SilentlyContinue).Count
```

**Thresholds**:
```yaml
CRITICAL: > 10
WARNING: 1-10
OK: 0
```

**AI Interpretation**:
- Extract error count
- Kernel errors indicate hardware failures or driver bugs
- If WARNING/CRITICAL → add "kernel" to `deep_recommended`

---

### 2. OOM Killer Events Count

**Command**:
```bash
# Linux
dmesg 2>/dev/null | grep -c "Out of memory"

# macOS
log show --predicate 'eventMessage contains "killed"' --last 1d 2>/dev/null | wc -l

# Windows (Application crashes)
(Get-EventLog -LogName Application -Source "Application Error" -Newest 20 -ErrorAction SilentlyContinue).Count
```

**Thresholds**:
```yaml
CRITICAL: > 5
WARNING: 1-5
OK: 0
```

**AI Interpretation**:
- OOM events mean memory exhaustion
- Multiple OOM events suggest memory leak or insufficient RAM
- If WARNING/CRITICAL → add "oom" to `deep_recommended`

---

### 3. File System Errors Count

**Command**:
```bash
# Linux
dmesg 2>/dev/null | grep -i "ext4\|xfs\|btrfs" | grep -ci error

# macOS
log show --predicate 'subsystem == "com.apple.filesystems"' --last 1d 2>/dev/null | grep -ci error

# Windows
(Get-EventLog -LogName System -Source "Ntfs" -EntryType Error -Newest 20 -ErrorAction SilentlyContinue).Count
```

**Thresholds**:
```yaml
WARNING: > 0
OK: 0
```

**AI Interpretation**:
- Any file system error is concerning (potential data loss)
- If WARNING → add "fs" to `deep_recommended`

---

### 4. Authentication Failures Count (Last Hour)

**Command**:
```bash
# Linux
AUTH_LOG="/var/log/auth.log"
[ ! -f "$AUTH_LOG" ] && AUTH_LOG="/var/log/secure"
grep "Failed password" "$AUTH_LOG" 2>/dev/null | grep "$(date '+%b %e %H')" | wc -l

# macOS
log show --predicate 'eventMessage contains "authentication failed"' --last 1h 2>/dev/null | wc -l

# Windows
(Get-EventLog -LogName Security -InstanceId 4625 -Newest 50 -ErrorAction SilentlyContinue).Count
```

**Thresholds**:
```yaml
CRITICAL: > 50 (likely attack)
WARNING: 11-50
OK: 0-10
```

**AI Interpretation**:
- 50+ failures/hour typically indicates brute-force attack
- 10-50 may be user mistakes or reconnaissance
- If WARNING/CRITICAL → add "auth" to `deep_recommended`

---

### 5. Failed Services Count

**Command**:
```bash
# Linux
systemctl --failed --no-legend 2>/dev/null | wc -l

# macOS
launchctl list 2>/dev/null | grep -v "^-\|0$" | wc -l

# Windows
(Get-Service | Where-Object {$_.Status -ne "Running" -and $_.StartType -eq "Automatic"}).Count
```

**Thresholds**:
```yaml
WARNING: > 0
OK: 0
```

**AI Interpretation**:
- Any failed service should be investigated
- If WARNING → add "service" to `deep_recommended`

---

## 📊 Quick Mode Complete Script

```bash
#!/bin/bash
# Quick Mode: Error count only (10 seconds)

echo "=== Quick Mode: System Log Check ==="

# 1. Kernel Errors
KERNEL_ERRORS=$(dmesg -l err,crit,alert,emerg 2>/dev/null | wc -l)
[ "$KERNEL_ERRORS" -gt 10 ] && K_STATUS="CRITICAL" || [ "$KERNEL_ERRORS" -gt 0 ] && K_STATUS="WARNING" || K_STATUS="OK"
echo "Kernel: $KERNEL_ERRORS errors [$K_STATUS]"

# 2. OOM Events
OOM_COUNT=$(dmesg 2>/dev/null | grep -c "Out of memory")
[ "$OOM_COUNT" -gt 5 ] && O_STATUS="CRITICAL" || [ "$OOM_COUNT" -gt 0 ] && O_STATUS="WARNING" || O_STATUS="OK"
echo "OOM: $OOM_COUNT events [$O_STATUS]"

# 3. FS Errors
FS_ERRORS=$(dmesg 2>/dev/null | grep -i "ext4\|xfs" | grep -ci error)
[ "$FS_ERRORS" -gt 0 ] && F_STATUS="WARNING" || F_STATUS="OK"
echo "File System: $FS_ERRORS errors [$F_STATUS]"

# 4. Auth Failures
AUTH_LOG="/var/log/auth.log"
[ ! -f "$AUTH_LOG" ] && AUTH_LOG="/var/log/secure"
FAILED_LOGINS=$(grep "Failed password" "$AUTH_LOG" 2>/dev/null | grep "$(date '+%b %e %H')" | wc -l)
[ "$FAILED_LOGINS" -gt 50 ] && A_STATUS="CRITICAL" || [ "$FAILED_LOGINS" -gt 10 ] && A_STATUS="WARNING" || A_STATUS="OK"
echo "Auth Failures: $FAILED_LOGINS/hour [$A_STATUS]"

# 5. Failed Services
FAILED_SERVICES=$(systemctl --failed --no-legend 2>/dev/null | wc -l)
[ "$FAILED_SERVICES" -gt 0 ] && S_STATUS="WARNING" || S_STATUS="OK"
echo "Services: $FAILED_SERVICES failed [$S_STATUS]"

# Overall Status
if [[ "$K_STATUS" == "CRITICAL" || "$O_STATUS" == "CRITICAL" || "$A_STATUS" == "CRITICAL" ]]; then
  echo "OVERALL: CRITICAL - Deep mode recommended"
elif [[ "$K_STATUS" == "WARNING" || "$O_STATUS" == "WARNING" || "$F_STATUS" == "WARNING" || "$A_STATUS" == "WARNING" || "$S_STATUS" == "WARNING" ]]; then
  echo "OVERALL: WARNING - Consider deep mode"
else
  echo "OVERALL: OK - No issues detected"
fi
```

---

## 📋 Quick Mode Output Template

**AI should generate**:

```json
{
  "mode": "quick",
  "duration": "10s",
  "timestamp": "<ISO 8601>",
  "findings": {
    "kernel": {"count": 3, "status": "WARNING"},
    "oom": {"count": 0, "status": "OK"},
    "fs": {"count": 0, "status": "OK"},
    "auth": {"count": 5, "status": "OK"},
    "service": {"count": 1, "status": "WARNING"}
  },
  "deep_recommended": ["kernel", "service"],
  "summary": "2 warnings detected (kernel, service), recommend deep analysis"
}
```

**Human-friendly format**:

```
⚡ Quick Log Scan Results (10s)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  Kernel: 3 errors [WARNING]
✅ OOM: 0 events [OK]
✅ File System: 0 errors [OK]
✅ Auth: 5 failures/hour [OK]
⚠️  Services: 1 failed [WARNING]

🔬 Recommended: Deep Kernel + Service analysis
```

---

## 🔗 Next Steps

**Based on Quick Mode results**:

- If **kernel** = WARNING/CRITICAL → Read `system-logs-deep-kernel.md`
- If **oom** = WARNING/CRITICAL → Read `system-logs-deep-oom.md`
- If **fs** = WARNING/CRITICAL → Read `system-logs-deep-fs.md`
- If **auth** = WARNING/CRITICAL → Read `system-logs-deep-auth.md`
- If **service** = WARNING/CRITICAL → Read `system-logs-deep-service.md`
- If **all OK** → Report healthy status, no further action needed

---

## 💡 Usage Examples

### Example 1: User Reports "系统有错误"

**AI Workflow**:
```
1. Execute Quick Mode (all 5 checks)
   Duration: 10s
   
2. Quick Results:
   Kernel: 3 errors [WARNING]
   OOM: 0 events [OK]
   FS: 0 errors [OK]
   Auth: 5/hour [OK]
   Services: 1 failed [WARNING]
   
3. Decision: 2 warnings → Read system-logs-deep-kernel.md + system-logs-deep-service.md
   
Total Duration: 10 seconds
Total Token: ~600 (this file)
```

---

### Example 2: Health Check (All OK)

**AI Workflow**:
```
1. Execute Quick Mode
   Duration: 10s
   
2. Quick Results: All OK
   
3. Decision: No Deep needed
   
4. Report:
   系统日志检查完成 - 一切正常 ✅
   
Total Duration: 10 seconds
Total Token: ~600 (this file only)
```

---

**Last Updated**: 2026-03-24
**Compatibility**: Linux (primary), macOS/Windows (partial)
**Dependencies**: dmesg, systemctl/launchctl (standard)
**Token Estimate**: ~600 tokens
