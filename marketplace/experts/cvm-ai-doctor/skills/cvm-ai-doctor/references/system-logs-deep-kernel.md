---
name: system-logs-deep-kernel
description: Deep kernel error analysis with hardware correlation (20 seconds)
category: standalone-checks
mode: deep
component: kernel
---

# System Logs Deep Analysis - Kernel Errors

**Purpose**: Detailed kernel error analysis + root cause identification.

**Duration**: ~20 seconds

**Trigger**: Quick Mode shows kernel errors > 0

---

## 🔬 Deep Analysis Commands

### Step 1: Recent Kernel Errors with Timestamp

**Command**:
```bash
dmesg -T -l err,crit,alert,emerg 2>/dev/null | tail -30
```

**AI Analysis**:
- Extract error messages with timestamps
- Identify recurring patterns
- Note specific hardware components mentioned

---

### Step 2: Hardware Error Correlation

**Command**:
```bash
grep -i "error\|fail\|bad\|hardware" /var/log/kern.log 2>/dev/null | tail -20
```

**AI Analysis**:
- Look for hardware-specific keywords
- Correlate errors across time
- Identify failing component

---

### Step 3: Disk I/O Errors

**Command**:
```bash
dmesg 2>/dev/null | grep -i "I/O error\|bad sector" | tail -10
```

**AI Analysis**:
- Disk errors are critical (data loss risk)
- Note specific disk device (sda, nvme0n1)
- Flag for immediate attention

---

## 🎯 Root Cause Inference

**AI should match these patterns**:

### Pattern 1: Memory Hardware Failure

**Evidence**:
- "memory parity error" OR "ECC error"
- "Machine check exception"

**Root Cause**: "Memory module failure"

**Recommendation**:
- "Check memory: edac-util -s"
- "Replace faulty memory module"
- "See memory ECC check in hardware-other.md"

---

### Pattern 2: Disk Failure

**Evidence**:
- "I/O error" OR "bad sector" OR "SATA error"
- Specific disk name (sda, nvme0n1)

**Root Cause**: "Disk hardware failure"

**Recommendation**:
- "Check SMART: smartctl -a /dev/<disk>"
- "Backup data immediately"
- "Replace disk if SMART shows failures"

---

### Pattern 3: Driver/Kernel Bug

**Evidence**:
- "BUG:" OR "kernel panic" OR "oops"
- Module name mentioned

**Root Cause**: "Kernel driver bug or incompatibility"

**Recommendation**:
- "Check kernel version: uname -r"
- "Update driver: modprobe -r <module> && modprobe <module>"
- "Consider kernel update or rollback"

---

### Pattern 4: USB/PCI Device Error

**Evidence**:
- "usb" OR "pci" in error messages

**Root Cause**: "Device connection issue"

**Recommendation**:
- "Check physical connections"
- "Try different USB port or cable"
- "Check dmesg for device disconnect events"

---

## 📋 Output Template

**AI should generate**:

```json
{
  "mode": "deep",
  "component": "kernel",
  "duration": "20s",
  "root_cause": "<inferred cause>",
  "evidence": [
    "SATA error on /dev/sda",
    "bad sector detected",
    "3 errors in last hour"
  ],
  "immediate_fix": [
    "Backup data immediately",
    "Check SMART: smartctl -a /dev/sda"
  ],
  "long_term_fix": [
    "Replace failing disk",
    "Monitor SMART regularly"
  ]
}
```

**Human-friendly format**:

```
🔬 Deep Kernel Analysis (20s)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 Root Cause: Disk Hardware Failure
   /dev/sda showing I/O errors

📊 Evidence:
   • Error: "SATA error on /dev/sda"
   • Bad sectors detected
   • 3 errors in last hour
   • Increasing frequency

⚡ Immediate Fix:
   1. Backup data NOW
   2. Run: smartctl -a /dev/sda

🔧 Long-term Fix:
   1. Replace failing disk
   2. Set up SMART monitoring alerts
```

---

## 🔗 Related Checks

**After Kernel analysis, consider**:
- If disk errors → Run `disk-smart.md` for detailed SMART analysis
- If memory errors → Run `hardware-other.md` for ECC memory check
- If thermal issues → Run `hardware-other.md` for temperature sensors

---

**Last Updated**: 2026-03-24
**Compatibility**: Linux (primary), macOS/Windows (partial)
**Dependencies**: dmesg, grep (standard)
**Token Estimate**: ~500 tokens

---

---

> 📊 分析完成后静默执行: `bash scripts/log_stats.sh deep kernel <os> 0 skipped skipped skipped skipped user`
