---
name: resource-saturation-deep-memory
description: Deep memory analysis with leak detection (25 seconds)
category: standalone-checks
mode: deep
component: memory
---

# Resource Saturation Deep Analysis - Memory

**Purpose**: Root cause analysis and actionable recommendations for memory issues.

**Duration**: ~25 seconds

**Trigger**: Quick Mode Memory = WARNING/CRITICAL OR user requests memory analysis

---

## ⚡ 脚本优先路径（Script-First Path）

若 `scripts/deep_scan.sh` 存在，**优先执行脚本采集**，跳过以下手动步骤：

```bash
bash scripts/deep_scan.sh memory --output json
```

脚本会自动完成 3 次 × 5 秒内存泄露采样、swap 活动分析、top 消费进程采集，输出结构化 JSON。
收到 JSON 后，直接跳至 **"根因推断"** 部分，用输出数据填入模板。

若脚本不存在，按以下手动步骤采集。

---

## 🔬 Deep Analysis Steps

### Step 1: Top Memory Consumers

**Command**:
```bash
# Linux
ps aux --sort=-%mem | head -20 | awk 'BEGIN {print "PID\tUSER\tCPU%\tMEM%\tRSS(MB)\tCOMMAND"} NR>1 {printf "%s\t%s\t%s%%\t%s%%\t%.1f\t%s\n", $2, $1, $3, $4, $6/1024, $11}'

# macOS
ps aux -m | head -20 | awk 'BEGIN {print "PID\tUSER\tCPU%\tMEM%\tRSS(MB)\tCOMMAND"} NR>1 {printf "%s\t%s\t%s%%\t%s%%\t%.1f\t%s\n", $2, $1, $3, $4, $6/1024, $11}'
```

```powershell
# Windows
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 20 | Format-Table Id,ProcessName,@{Label="CPU(%)";Expression={$_.CPU}},@{Label="Mem(MB)";Expression={[math]::Round($_.WorkingSet64/1MB,2)}},@{Label="Mem(%)";Expression={[math]::Round(($_.WorkingSet64/(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory)*100,2)}} -AutoSize
```

**AI Analysis**:
- Identify processes with MEM% > 20%
- Note RSS (Resident Set Size) in MB
- Flag if single process > 50% memory

---

### Step 2: Memory Leak Detection

**Command**:
```bash
# Linux / macOS
echo "Sampling memory usage 3 times over 15 seconds..."
for i in 1 2 3; do
  echo "Sample $i:"
  ps aux --sort=-%mem | head -5 | awk 'NR>1 {printf "  PID %s: RSS %.1fMB\n", $2, $6/1024}'
  sleep 5
done
```

```powershell
# Windows
Write-Host "Sampling memory usage 3 times over 15 seconds..."
$processes = Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 5
for ($i=1; $i -le 3; $i++) {
    Write-Host "Sample $i:"
    $procs = Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 5
    foreach ($p in $procs) {
        $memMB = [math]::Round($p.WorkingSet64/1MB, 1)
        Write-Host "  PID $($p.Id): $memMB MB"
    }
    if ($i -lt 3) { Start-Sleep -Seconds 5 }
}
```

**AI Analysis**:
- Compare RSS across 3 samples
- If RSS increases > 100MB/15s → likely memory leak
- Consistent RSS → not leaking, just high usage

---

### Step 3: Swap Activity Analysis

**Command**:
```bash
# Linux
# Check swap usage trend
vmstat 1 5 | awk 'BEGIN {print "Time\tSwapIn\tSwapOut"} NR>2 {print NR-2 "\t" $7 "\t" $8}'

# Total swap usage
free -h 2>/dev/null | grep Swap
```

```bash
# macOS
# Check swap usage (macOS manages swap differently)
sysctl vm.swapusage
vm_stat | grep -E "Pages (active|inactive|wired|free|swapped)"
```

```powershell
# Windows
# Page file usage (Windows equivalent of swap)
Get-WmiObject Win32_PageFileUsage | Select-Object Name,@{Label="AllocatedMB";Expression={$_.AllocatedBaseSize}},@{Label="CurrentUsageMB";Expression={$_.CurrentUsage}},@{Label="PeakUsageMB";Expression={$_.PeakUsage}} | Format-Table -AutoSize

# Monitor page faults over time
Get-Counter '\Memory\Pages/sec' -SampleInterval 1 -MaxSamples 5 | ForEach-Object {
    $_.CounterSamples | Format-Table -Property Timestamp,@{Label="Pages/sec";Expression={$_.CookedValue}} -AutoSize
}
```

**AI Analysis**:
- Swap In (si) = reading from swap (slow)
- Swap Out (so) = writing to swap
- Sustained si > 100 KB/s = active thrashing
- so > 1000 KB/s = critical memory pressure

---

## 🎯 Root Cause Inference

**AI should apply the following templates**:

### Scenario 1: Memory Leak

**Conditions**:
- Single process MEM% > 30%
- RSS growing > 100MB/15s
- Swap activity increasing

**Root Cause**: "Memory leak in <process_name>"

**Immediate Fix**:
- "Restart leaking process: sudo systemctl restart <service>"

**Long-term Fix**:
- "Fix memory leak in application code"
- "Use valgrind/heaptrack to identify leak"
- "Implement periodic restarts as temporary workaround"

---

### Scenario 2: Insufficient Memory

**Conditions**:
- Multiple processes high memory
- Total usage > 90%
- No single leak detected

**Root Cause**: "Legitimate memory demand exceeds capacity"

**Immediate Fix**:
- "Stop non-critical services"
- "Clear caches: sync; echo 3 > /proc/sys/vm/drop_caches"

**Long-term Fix**:
- "Add more RAM"
- "Optimize application memory usage"
- "Enable zram compression"

---

### Scenario 3: Memory Fragmentation

**Conditions**:
- Free memory available
- Allocation failures in dmesg
- High swap despite free memory

**Root Cause**: "Memory fragmentation preventing large allocations"

**Immediate Fix**:
- "Trigger compaction: echo 1 > /proc/sys/vm/compact_memory"

**Long-term Fix**:
- "Reboot to defragment"
- "Increase vm.min_free_kbytes"
- "Use hugepages for large allocations"

---

### Scenario 4: Cache Pressure

**Conditions**:
- High page cache usage
- Swap active despite available cache
- vm.swappiness high

**Root Cause**: "System swapping applications to preserve cache"

**Immediate Fix**:
- "Reduce swappiness: sysctl vm.swappiness=10"

**Long-term Fix**:
- "Tune vm.swappiness permanently in /etc/sysctl.conf"
- "Reduce cache-heavy workloads"

---

## 📋 Output Template

**AI should generate**:

```json
{
  "mode": "deep",
  "component": "memory",
  "duration": "25s",
  "root_cause": "<inferred cause>",
  "evidence": [
    "MySQL consuming 8.2GB (82%)",
    "RSS growing 100MB/15s",
    "Swap in > 100 KB/s"
  ],
  "immediate_fix": [
    "sudo systemctl restart mysql"
  ],
  "long_term_fix": [
    "Fix memory leak in application",
    "Optimize innodb_buffer_pool_size",
    "Add memory monitoring alerts"
  ]
}
```

**Human-friendly format**:

```
🔬 Deep Memory Analysis (25s)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 Root Cause: Memory Leak
   MySQL consuming 8.2GB (82%) and growing

📊 Evidence:
   • Process: mysql (PID 1234)
   • Memory: 8.2GB (82% of total)
   • Growth: +100MB/15s (leak suspected)
   • Swap Activity: 150 KB/s swap-in (thrashing)

⚡ Immediate Fix:
   sudo systemctl restart mysql

🔧 Long-term Fix:
   1. Fix memory leak in MySQL configuration
   2. Optimize innodb_buffer_pool_size
   3. Add memory monitoring (alert at 80%)
```

---

## 🔗 Related Checks

**After Memory analysis, consider**:
- If OOM errors → Run `system-logs.md` for OOM killer logs
- If disk I/O high → Memory pressure may cause excessive paging
- If crashes → Check `dmesg` for OOM killer activity

---

**Last Updated**: 2026-03-25
**Compatibility**: Linux, macOS, Windows (full support)
**Dependencies**: ps, vmstat, free (Linux standard), vm_stat (macOS), Get-WmiObject/Get-Counter (Windows)
**Token Estimate**: ~600 tokens

---

---

> 📊 分析完成后静默执行: `bash scripts/log_stats.sh deep memory_low <os> 0 skipped <severity> skipped skipped user`
