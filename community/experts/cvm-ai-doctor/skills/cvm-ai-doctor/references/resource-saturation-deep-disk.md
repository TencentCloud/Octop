---
name: resource-saturation-deep-disk
description: Deep disk I/O analysis with SMART health check (30 seconds)
category: standalone-checks
mode: deep
component: disk
---

# Resource Saturation Deep Analysis - Disk

**Purpose**: Root cause analysis and actionable recommendations for disk I/O issues.

**Duration**: ~30 seconds

**Trigger**: Quick Mode Disk = WARNING/CRITICAL OR user requests disk analysis

---

## ⚡ 脚本优先路径（Script-First Path）

若 `scripts/deep_scan.sh` 存在，**优先执行脚本采集**，跳过以下手动步骤：

```bash
bash scripts/deep_scan.sh disk --output json
```

脚本会自动采集 I/O 进程列表、iostat 队列深度/延迟、磁盘使用率、SMART 健康状态及 PSI，输出结构化 JSON。
收到 JSON 后，直接跳至 **"根因推断"** 部分，用输出数据填入模板。

若脚本不存在，按以下手动步骤采集。

---

## 🔬 Deep Analysis Steps

### Step 1: Identify I/O-Heavy Processes

**Command**:
```bash
if command -v iotop &> /dev/null; then
  echo "Top I/O processes (requires root):"
  sudo iotop -b -n 1 -o | head -15
else
  echo "iotop not installed, using pidstat..."
  if command -v pidstat &> /dev/null; then
    pidstat -d 1 3 | tail -20
  else
    echo "Install sysstat package for detailed I/O analysis"
  fi
fi
```

**AI Analysis**:
- Identify processes with high KB_READ or KB_WRTN
- Note if reads or writes dominate
- Flag if single process > 50% I/O bandwidth

---

### Step 2: Disk Queue and Latency

**Command**:
```bash
iostat -x 1 5 | awk 'BEGIN {print "Device\tUtil%\tAvgQu\tr_await\tw_await"} /^[sv]d[a-z]/ {printf "%s\t%.1f%%\t%.2f\t%.1fms\t%.1fms\n", $1, $14, $9, $10, $11}'
```

**AI Analysis**:
- Util% > 80% → disk is bottleneck
- AvgQu > 2 → requests queuing significantly
- r_await / w_await > 100ms → slow disk
- r_await > w_await → read-heavy, check read caching

---

### Step 3: Directory Size Analysis

**Purpose**: Identify which directories consume the most disk space (includes many small files).

**Command (Linux/macOS)**:
```bash
echo "=== Top 10 Largest Directories ==="
du -h --max-depth=2 / 2>/dev/null | sort -hr | head -10

echo ""
echo "=== Directories with Most Files (small file detection) ==="
find / -xdev -type d 2>/dev/null | while read dir; do
  file_count=$(find "$dir" -maxdepth 1 -type f 2>/dev/null | wc -l)
  if [ "$file_count" -gt 1000 ]; then
    size=$(du -sh "$dir" 2>/dev/null | cut -f1)
    echo "$file_count files - $size - $dir"
  fi
done | sort -rn | head -10
```

**Command (Windows PowerShell)**:
```powershell
Write-Output "=== Top 10 Largest Directories ==="
Get-ChildItem C:\ -Recurse -Depth 2 -ErrorAction SilentlyContinue | 
  Where-Object {$_.PSIsContainer} | 
  ForEach-Object {
    $size = (Get-ChildItem $_.FullName -Recurse -ErrorAction SilentlyContinue | 
             Measure-Object -Property Length -Sum).Sum
    [PSCustomObject]@{
      Path = $_.FullName
      SizeGB = [Math]::Round($size / 1GB, 2)
    }
  } | Sort-Object SizeGB -Descending | Select-Object -First 10

Write-Output "`n=== Directories with Most Files ==="
Get-ChildItem C:\ -Recurse -Depth 2 -Directory -ErrorAction SilentlyContinue | 
  ForEach-Object {
    $fileCount = (Get-ChildItem $_.FullName -File -ErrorAction SilentlyContinue).Count
    if ($fileCount -gt 1000) {
      [PSCustomObject]@{
        Path = $_.FullName
        FileCount = $fileCount
      }
    }
  } | Sort-Object FileCount -Descending | Select-Object -First 10
```

**AI Analysis**:
- Identify directories with unusually large size
- Flag directories with >10,000 small files (logs, cache, temp)
- Common culprits:
  - Linux: `/var/log`, `/tmp`, `/var/cache`, `~/.cache`
  - macOS: `~/Library/Caches`, `/private/var/log`
  - Windows: `C:\Windows\Temp`, `C:\Users\*\AppData\Local\Temp`, `C:\ProgramData`

---

### Step 4: SMART Health Check

**Command (Linux/macOS)**:
```bash
for disk in /dev/sd[a-z]; do
  if [ -b "$disk" ]; then
    echo "=== $disk ==="
    sudo smartctl -H "$disk" 2>/dev/null | grep -E "SMART overall|PASSED|FAILED"
    sudo smartctl -A "$disk" 2>/dev/null | grep -E "Reallocated_Sector|Current_Pending|Offline_Uncorrectable" | head -3
  fi
done
```

**AI Analysis**:
- SMART overall-health = FAILED → disk is failing
- Reallocated_Sector > 0 → bad sectors detected
- Current_Pending_Sector > 10 → imminent failure

---

## 🎯 Root Cause Inference

**AI should apply the following templates**:

### Scenario 1: Process I/O Storm

**Conditions**:
- Single process dominant I/O
- Disk utilization > 80%
- SMART healthy

**Root Cause**: "Process <name> generating excessive I/O"

**Immediate Fix**:
- "Throttle I/O: ionice -c 3 -p <pid>"
- "Or restart: sudo systemctl restart <service>"

**Long-term Fix**:
- "Optimize application I/O patterns (batching, caching)"
- "Use faster storage (SSD, NVMe)"

---

### Scenario 2: Disk Hardware Failure

**Conditions**:
- SMART health = FAILED
- Reallocated sectors > 10
- High latency (>100ms)

**Root Cause**: "Disk hardware failure imminent"

**Immediate Fix**:
- "🚨 BACKUP DATA NOW"
- "Prepare for disk replacement"

**Long-term Fix**:
- "Replace failing disk"
- "Restore from backup"

---

### Scenario 3: Filesystem Fragmentation

**Conditions**:
- Read latency high
- Write latency normal
- Old filesystem (ext3/ext4)

**Root Cause**: "Filesystem fragmentation"

**Immediate Fix**:
- "Check fragmentation: e4defrag -c /"

**Long-term Fix**:
- "Defragment: e4defrag /"
- "Consider migration to XFS/Btrfs"

---

### Scenario 4: Small Files Space Exhaustion

**Conditions**:
- Disk space low but no single large file found
- Directory has >10,000 small files
- Common in log/cache/temp directories

**Root Cause**: "Disk space consumed by numerous small files (logs, cache, temp)"

**Immediate Fix (Linux/macOS)**:
```bash
# Clean system logs
sudo journalctl --vacuum-time=7d
# Clean package cache
sudo apt clean  # Ubuntu/Debian
sudo yum clean all  # CentOS/RHEL
# Clean user cache
rm -rf ~/.cache/*
rm -rf /tmp/*
```

**Immediate Fix (Windows PowerShell)**:
```powershell
# Clean Windows temp
Remove-Item C:\Windows\Temp\* -Recurse -Force -ErrorAction SilentlyContinue
# Clean user temp
Remove-Item $env:TEMP\* -Recurse -Force -ErrorAction SilentlyContinue
# Clean Windows Update cache
Remove-Item C:\Windows\SoftwareDistribution\Download\* -Recurse -Force -ErrorAction SilentlyContinue
```

**Long-term Fix**:
- "Configure log rotation: /etc/logrotate.conf"
- "Set cache size limits"
- "Schedule regular cleanup jobs (cron/Task Scheduler)"

---

### Scenario 5: Insufficient I/O Bandwidth

**Conditions**:
- Multiple processes high I/O
- Disk utilization 100%
- SMART healthy

**Root Cause**: "Legitimate I/O demand exceeds disk capacity"

**Immediate Fix**:
- "Defer non-critical I/O"
- "Increase readahead: blockdev --setra 4096 /dev/sda"

**Long-term Fix**:
- "Upgrade to SSD/NVMe"
- "Add more disks (RAID 0/10)"
- "Use I/O scheduler tuning (noop for SSD)"

---

## 📋 Output Template

**AI should generate**:

```json
{
  "mode": "deep",
  "component": "disk",
  "duration": "30s",
  "root_cause": "<inferred cause>",
  "evidence": [
    "mysqld generating 85MB/s writes",
    "sda utilization 95%",
    "Write latency 180ms"
  ],
  "immediate_fix": [
    "ionice -c 3 -p <pid>",
    "Or: sudo systemctl restart mysql"
  ],
  "long_term_fix": [
    "Optimize MySQL query patterns",
    "Enable query cache",
    "Upgrade to SSD storage"
  ]
}
```

**Human-friendly format**:

```
🔬 Deep Disk Analysis (30s)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 Root Cause: Process I/O Storm
   mysqld generating excessive writes

📊 Evidence:
   • Process: mysqld (PID 5678)
   • Write Rate: 85MB/s
   • Disk sda: 95% utilization
   • Write Latency: 180ms (slow)
   • SMART: Healthy

⚡ Immediate Fix:
   sudo ionice -c 3 -p 5678
   # Or: sudo systemctl restart mysql

🔧 Long-term Fix:
   1. Optimize MySQL I/O patterns
   2. Enable query cache
   3. Upgrade to SSD/NVMe storage
```

---

## 🔗 Related Checks

**After Disk analysis, consider**:
- If SMART failing → Run `disk-smart.md` for detailed SMART analysis
- If filesystem errors → Run `system-logs.md` for kernel error logs
- If high CPU wait → This confirms disk is the bottleneck

---

**Last Updated**: 2026-03-24
**Compatibility**: Linux (primary), macOS (partial)
**Dependencies**: iostat (sysstat), smartctl (smartmontools, optional), iotop/pidstat (optional)
**Token Estimate**: ~600 tokens

---

---

> 📊 分析完成后静默执行: `bash scripts/log_stats.sh deep disk_issue <os> 0 skipped skipped <severity> skipped user`
