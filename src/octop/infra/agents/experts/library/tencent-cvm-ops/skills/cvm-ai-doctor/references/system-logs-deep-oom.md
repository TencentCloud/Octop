---
name: system-logs-deep-oom
description: Deep OOM event analysis with memory leak detection (25 seconds)
category: standalone-checks
mode: deep
component: oom
---

# System Logs Deep Analysis - OOM Killer Events

**Purpose**: Detailed OOM event analysis + memory leak identification.

**Duration**: ~25 seconds

**Trigger**: Quick Mode shows OOM count > 0

---

## 🔬 Deep Analysis Commands

### Step 1: OOM Event Timeline

**Command**:
```bash
dmesg -T 2>/dev/null | grep -i "out of memory\|killed process" | tail -20
```

**AI Analysis**:
- Extract timestamps and killed processes
- Identify recurring victims
- Note frequency pattern

---

### Step 2: Which Processes Were Killed

**Command**:
```bash
dmesg 2>/dev/null | grep "killed process" | awk '{print $(NF-7), $(NF-1)}' | tail -10
```

**AI Analysis**:
- List killed process names and PIDs
- Count occurrences per process
- Identify repeat offenders

---

### Step 3: Current Memory State

**Command**:
```bash
free -h
```

**AI Analysis**:
- Check if swap is configured
- Note current memory usage
- Assess if issue persists

---

### Step 4: Top Memory Consumers

**Command**:
```bash
ps aux --sort=-%mem | head -10
```

**AI Analysis**:
- Identify current memory hogs
- Compare with killed processes
- Flag suspicious growth

---

## 🎯 Root Cause Inference

### Pattern 1: Memory Leak

**Evidence**:
- Same process killed repeatedly (e.g., "java" 3 times)
- OOM events increasing over time

**Root Cause**: "Memory leak in <process_name>"

**Recommendation**:
- "Restart <process_name>"
- "Check application logs for memory growth"
- "Use 'ps aux' to monitor memory usage over time"
- "Consider profiling with valgrind or heaptrack"

---

### Pattern 2: Insufficient Memory

**Evidence**:
- Different processes killed
- Total memory usage consistently near 100%

**Root Cause**: "System memory insufficient for workload"

**Recommendation**:
- "Add more RAM"
- "Enable swap if not present"
- "Reduce concurrent processes"
- "Current memory: <X>GB, Recommended: <Y>GB"

---

### Pattern 3: Burst Traffic

**Evidence**:
- Multiple processes killed at same timestamp
- Timestamps align with traffic spike

**Root Cause**: "Sudden memory spike from traffic burst"

**Recommendation**:
- "Implement rate limiting"
- "Add auto-scaling if cloud-based"
- "Optimize application memory usage"

---

### Pattern 4: No Swap

**Evidence**:
- Swap = 0 in 'free -h' output
- Physical memory hit 100%

**Root Cause**: "No swap space configured"

**Recommendation**:
- "Add swap file: fallocate -l 2G /swapfile && mkswap /swapfile && swapon /swapfile"
- "Make persistent: echo '/swapfile none swap sw 0 0' >> /etc/fstab"

---

## 📋 Output Template

```json
{
  "mode": "deep",
  "component": "oom",
  "duration": "25s",
  "root_cause": "Memory leak in java",
  "evidence": [
    "java killed 8 times",
    "Memory usage 95%",
    "No swap configured"
  ],
  "immediate_fix": [
    "Restart java application",
    "Add 2GB swap file"
  ],
  "long_term_fix": [
    "Fix memory leak in application",
    "Add more RAM",
    "Monitor memory with alerts"
  ]
}
```

---

**Last Updated**: 2026-03-24
**Compatibility**: Linux (primary), macOS/Windows (partial)
**Dependencies**: dmesg, free, ps (standard)
**Token Estimate**: ~500 tokens

---

---

> 📊 分析完成后静默执行: `bash scripts/log_stats.sh deep oom <os> 0 skipped skipped skipped skipped user`
