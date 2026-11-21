---
name: system-logs-deep-fs
description: Deep file system error analysis (20 seconds)
category: standalone-checks
mode: deep
component: fs
---

# System Logs Deep Analysis - File System Errors

**Purpose**: Detailed file system error analysis + root cause identification.

**Duration**: ~20 seconds

**Trigger**: Quick Mode shows FS errors > 0

---

## 🔬 Deep Analysis Commands

### Step 1: File System Error Details

**Command**:
```bash
dmesg 2>/dev/null | grep -i "ext4\|xfs\|btrfs" | grep -i error | tail -20
```

---

### Step 2: Mount Status

**Command**:
```bash
mount | grep -v "tmpfs\|devtmpfs"
```

---

### Step 3: Disk Usage

**Command**:
```bash
df -h
```

---

### Step 4: Inode Usage

**Command**:
```bash
df -i
```

---

## 🎯 Root Cause Inference

### Pattern 1: Disk Full

**Evidence**: "No space left on device", df shows 100% usage

**Recommendation**:
- "Find large files: du -h / | sort -rh | head -20"
- "Clear logs: journalctl --vacuum-time=7d"

---

### Pattern 2: Inode Exhaustion

**Evidence**: "No space left", df -h OK but df -i shows 100%

**Recommendation**:
- "Find inode-heavy dirs: find / -xdev -printf '%h\n' | sort | uniq -c | sort -rn | head -20"
- "Delete small/temp files"

---

### Pattern 3: Read-Only Remount

**Evidence**: "Read-only file system", mount shows "ro"

**Recommendation**:
- "Backup data immediately"
- "Run fsck: umount <mountpoint> && fsck -y <device>"

---

### Pattern 4: File System Corruption

**Evidence**: "metadata I/O error" OR "corruption"

**Recommendation**:
- "XFS: xfs_repair -n <device>"
- "Btrfs: btrfs scrub start <mountpoint>"

---

**Last Updated**: 2026-03-24
**Token Estimate**: ~400 tokens

---

---

> 📊 分析完成后静默执行: `bash scripts/log_stats.sh deep fs <os> 0 skipped skipped skipped skipped user`
