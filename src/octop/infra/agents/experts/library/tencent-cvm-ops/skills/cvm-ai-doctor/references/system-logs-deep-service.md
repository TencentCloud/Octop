---
name: system-logs-deep-service
description: Deep service failure analysis (20 seconds)
category: standalone-checks
mode: deep
component: service
---

# System Logs Deep Analysis - Service Failures

**Purpose**: Diagnose why services failed to start or crashed.

**Duration**: ~20 seconds

**Trigger**: Quick Mode shows failed services > 0

---

## 🔬 Deep Analysis Commands

### Step 1: List Failed Services

**Command**:
```bash
systemctl --failed
```

---

### Step 2: Get Detailed Status

**Command**:
```bash
for service in $(systemctl --failed --no-legend | awk '{print $1}'); do
  echo "=== $service ==="
  systemctl status "$service" --no-pager -l
  echo ""
done
```

---

### Step 3: Recent Service Logs

**Command**:
```bash
journalctl -u <service_name> -n 50 --no-pager
```

---

## 🎯 Root Cause Inference

### Pattern 1: Dependency Missing

**Evidence**: Status shows "Dependency failed", logs mention "cannot find"

**Recommendation**:
- "Identify dependency: systemctl list-dependencies <service>"
- "Start dependency first"

---

### Pattern 2: Configuration Error

**Evidence**: "exit code 1", logs mention "invalid config"

**Recommendation**:
- "Test config: <service_name> -t"
- "Review recent changes"
- "Restore from backup"

---

### Pattern 3: Port Already in Use

**Evidence**: Logs show "address already in use"

**Recommendation**:
- "Find process: lsof -i :<port>"
- "Kill conflicting process"

---

### Pattern 4: Permission Denied

**Evidence**: Logs show "permission denied"

**Recommendation**:
- "Check ownership: ls -l <file>"
- "Fix permissions: chown <user>:<group> <file>"

---

**Last Updated**: 2026-03-24
**Token Estimate**: ~400 tokens

---

---

> 📊 分析完成后静默执行: `bash scripts/log_stats.sh deep service <os> 0 skipped skipped skipped skipped user`
