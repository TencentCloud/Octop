---
name: resource-saturation-deep-cpu
description: Deep CPU analysis with root cause inference (20 seconds)
category: standalone-checks
mode: deep
component: cpu
---

# Resource Saturation Deep Analysis - CPU

**Purpose**: Root cause analysis and actionable recommendations for CPU issues.

**Duration**: ~20 seconds

**Trigger**: Quick Mode CPU = WARNING/CRITICAL OR user requests CPU analysis

---

## ⚡ 脚本优先路径（Script-First Path）

若 `scripts/deep_scan.sh` 存在，**优先执行脚本采集**，跳过以下手动步骤：

```bash
bash scripts/deep_scan.sh cpu --output json
```

脚本会一次性采集所有 CPU 数据（top consumers / 频率 / 热节流 / load trend / PSI）并输出结构化 JSON。
收到 JSON 后，直接跳至 **"根因推断"** 部分，用输出数据填入模板。

若脚本不存在，按以下手动步骤采集。

---

## 🔬 Deep Analysis Steps

### Step 1: Identify Top CPU Consumers

**Command**:
```bash
# Linux
ps aux --sort=-%cpu | head -20 | awk 'BEGIN {print "PID\tUSER\tCPU%\tMEM%\tCOMMAND"} NR>1 {printf "%s\t%s\t%s%%\t%s%%\t%s\n", $2, $1, $3, $4, $11}'

# macOS
ps aux -r | head -20 | awk 'BEGIN {print "PID\tUSER\tCPU%\tMEM%\tCOMMAND"} NR>1 {printf "%s\t%s\t%s%%\t%s%%\t%s\n", $2, $1, $3, $4, $11}'

# Windows (PowerShell)
Get-Process | Sort-Object CPU -Descending | Select-Object -First 20 | Format-Table Id,ProcessName,@{Label="CPU(s)";Expression={$_.CPU}},@{Label="Mem(MB)";Expression={[math]::Round($_.WorkingSet64/1MB,2)}} -AutoSize
```

**AI Analysis**:
- Identify processes with CPU > 50%
- Note if single process dominates (>70% on multi-core)
- Note if many processes evenly loaded

---

### Step 2: Check CPU Frequency & Thermal Throttling

**Command**:
```bash
# Linux: Current CPU frequency
cat /proc/cpuinfo 2>/dev/null | grep "MHz" | head -4

# Thermal sensors (if available)
if command -v sensors &> /dev/null; then
  sensors | grep -E "Core |Package" | head -8
else
  echo "lm-sensors not installed"
fi

# Check if thermal throttling occurred
dmesg | tail -100 | grep -i "thermal\|throttle" | tail -5
```

```bash
# macOS: CPU frequency and temperature
sysctl -n hw.cpufrequency hw.cpufrequency_max 2>/dev/null
sudo powermetrics -n 1 --samplers smc 2>/dev/null | grep -E "CPU die temperature|Package" | head -5
```

```powershell
# Windows: CPU frequency and temperature
# CPU frequency
Get-WmiObject Win32_Processor | Select-Object Name,CurrentClockSpeed,MaxClockSpeed | Format-Table -AutoSize

# Temperature (requires admin)
Get-WmiObject -Namespace "root\wmi" -Class MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | Select-Object @{Name="Temperature(C)";Expression={($_.CurrentTemperature/10)-273.15}}
```

**AI Analysis**:
- Compare current MHz to nominal frequency
- If MHz < 80% of nominal → likely thermal throttling
- If temperature > 80°C → thermal issue
- Check dmesg for throttling events

---

### Step 3: Load Average Trend

**Command**:
```bash
# Linux / macOS
uptime
echo "Load average interpretation: 1min / 5min / 15min"
echo "CPU cores: $(nproc 2>/dev/null || sysctl -n hw.ncpu)"
```

```powershell
# Windows (no direct load average, use CPU queue length)
Get-Counter '\System\Processor Queue Length' -SampleInterval 1 -MaxSamples 5 | ForEach-Object {$_.CounterSamples.CookedValue}
$cpuCores = (Get-WmiObject Win32_Processor).NumberOfLogicalProcessors
Write-Host "CPU Cores: $cpuCores"
Write-Host "Note: Windows doesn't have load average. Queue length > $($cpuCores*2) indicates overload"
```

**AI Analysis**:
- 1-min > 5-min > 15-min → load is decreasing (improving)
- 1-min < 5-min < 15-min → load is increasing (worsening)
- Load > 2x cores for 15min → sustained overload

---

## 🎯 Root Cause Inference

**AI should apply the following templates**:

### Scenario 1: Process Runaway

**Conditions**:
- Single process CPU > 50%
- Run queue high
- Process not expected to consume CPU

**Root Cause**: "Process <name> (PID <pid>) consuming <cpu>% CPU"

**Immediate Fix**:
- "Restart process: sudo systemctl restart <service>"
- "Or kill: sudo kill -9 <pid>"

**Long-term Fix**:
- "Investigate why process is consuming CPU"
- "Check for infinite loops in application code"
- "Review recent code changes"

---

### Scenario 2: Thermal Throttling

**Conditions**:
- CPU frequency < 80% of nominal
- Temperature > 80°C
- Run queue moderate

**Root Cause**: "CPU thermal throttling due to overheating"

**Immediate Fix**:
- "Improve airflow around server"
- "Clean dust from heatsink/fans"

**Long-term Fix**:
- "Replace thermal paste"
- "Upgrade cooling solution"
- "Reduce ambient temperature"

---

### Scenario 3: Sustained Overload

**Conditions**:
- Multiple processes evenly loaded
- 15-min load > 2x cores
- No single culprit

**Root Cause**: "Legitimate workload exceeding CPU capacity"

**Immediate Fix**:
- "Defer non-critical tasks"
- "Temporarily disable background jobs"

**Long-term Fix**:
- "Add more CPU cores (vertical scaling)"
- "Distribute load (horizontal scaling)"
- "Optimize application efficiency"

---

### Scenario 4: Context Switching Storm

**Conditions**:
- High run queue
- Many lightweight processes
- Low individual CPU usage

**Root Cause**: "Excessive context switching overhead"

**Immediate Fix**:
- "Consolidate processes if possible"
- "Check for fork bombs: ps aux | wc -l"

**Long-term Fix**:
- "Increase process niceness for background tasks"
- "Use process pooling instead of spawning"

---

## 📋 Output Template

**AI should generate**:

```json
{
  "mode": "deep",
  "component": "cpu",
  "duration": "20s",
  "root_cause": "<inferred cause>",
  "evidence": [
    "Process X consuming 85% CPU",
    "Run queue 24 (8 cores)",
    "Load average increasing: 8.5, 12.3, 15.8"
  ],
  "immediate_fix": [
    "sudo systemctl restart <service>",
    "Or: sudo kill -9 <pid>"
  ],
  "long_term_fix": [
    "Investigate application code for infinite loops",
    "Review recent changes",
    "Add monitoring alerts for CPU > 80%"
  ]
}
```

**Human-friendly format**:

```
🔬 Deep CPU Analysis (20s)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 Root Cause: Process Runaway
   node (PID 12345) consuming 85% CPU

📊 Evidence:
   • Process: node (PID 12345)
   • CPU Usage: 85%
   • Run Queue: 24 (8 cores = 3x overload)
   • Load Trend: Increasing (8.5 → 12.3 → 15.8)

⚡ Immediate Fix:
   sudo systemctl restart node-app
   # Or: sudo kill -9 12345

🔧 Long-term Fix:
   1. Debug application for infinite loops
   2. Review recent code changes
   3. Add CPU monitoring alerts (threshold: 80%)
```

---

## 🔗 Related Checks

**After CPU analysis, consider**:
- If thermal issues → Run `hardware-other.md` for detailed thermal monitoring
- If crashes/restarts → Run `system-logs.md` for error logs
- If I/O wait also high → Run `resource-saturation-deep-disk.md`

---

**Last Updated**: 2026-03-25
**Compatibility**: Linux, macOS, Windows (full support)
**Dependencies**: ps, uptime (standard), sensors (optional for Linux), powermetrics (macOS)
**Token Estimate**: ~600 tokens

---

---

> 📊 分析完成后静默执行: `bash scripts/log_stats.sh deep cpu_high <os> 0 <severity> skipped skipped skipped user`
