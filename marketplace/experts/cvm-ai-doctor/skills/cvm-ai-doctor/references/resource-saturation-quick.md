---
name: resource-saturation-quick
description: Fast 3-second triage scan to identify which components need deep analysis
category: standalone-checks
mode: quick
---

# Resource Saturation Quick Check

**Purpose**: Fast triage to identify which components need deep analysis (3 seconds).

**Based on**: Brendan Gregg's USE Method (Saturation dimension) + Google SRE Four Golden Signals

---

## 🎯 AI Usage Guide

### Quick Mode Workflow

```yaml
purpose: Fast triage to identify which components need deep analysis
duration: ~3 seconds (or 10 seconds fallback)
checks: 4 (CPU queue, Memory swap, Disk I/O wait, Network drops)

execution_steps:
  PREFERRED (Quick Scan Script):
    1. Check OS type and select script:
       - Windows: pwsh {skill_base_dir}/scripts/quick_scan.ps1
       - Linux/macOS: bash {skill_base_dir}/scripts/quick_scan.sh
    2. Execute the script
    3. Parse structured output (Status: OK/WARNING/CRITICAL per component)
    4. Build deep_recommended array from WARNING/CRITICAL components
    5. Generate summary and next-step recommendations
  
  FALLBACK (Individual Commands):
    1. If script not available or execution fails
    2. Run 4 quick check commands in sections below
    3. Compare each result against thresholds manually
    4. Classify status: OK | WARNING | CRITICAL
    5. Recommend Deep analysis for WARNING/CRITICAL components

output_format:
  findings:
    cpu: OK | WARNING | CRITICAL
    memory: OK | WARNING | CRITICAL
    disk: OK | WARNING | CRITICAL
    network: OK | WARNING | CRITICAL
  deep_recommended: [list of components needing deep analysis]
  
special_cases:
  if_lightclaw_process_abnormal:
    # If top CPU/memory consuming process contains "lightclaw" or "uvicorn"
    suggest: "Detected LightClaw process anomaly. Consider running 'health-check' skill for platform diagnostics."
  
  if_all_ok_and_user_asked_generic_health:
    # If user said "检查系统" without specific symptoms and all Quick checks pass
    suggest: "System performance is healthy. Need LightClaw platform security audit?"
```

---

## 🚀 Quick Scan Script (Recommended)

**Location**: 
- Windows: `scripts/quick_scan.ps1`
- Linux/macOS: `scripts/quick_scan.sh`

**AI Execution**:
```bash
# Windows
pwsh {skill_base_dir}/scripts/quick_scan.ps1

# Linux/macOS
bash {skill_base_dir}/scripts/quick_scan.sh
```

**Output Format** (structured, machine-parseable):
```
=== CVM QUICK HEALTH CHECK ===
Platform: Linux
Timestamp: 2026-03-27T10:30:00Z

--- CPU CHECK ---
CPU Cores: 8
Run Queue: 6
Status: OK

--- MEMORY CHECK ---
Swap Used: 512MB
Status: WARNING
Reason: Swap usage >= 100MB indicates memory pressure

--- DISK CHECK ---
I/O Wait: 3.2%
Status: OK

--- NETWORK CHECK ---
RX Drops: 0
TX Drops: 0
Total Drops: 0
Status: OK

=== QUICK CHECK COMPLETE ===
```

**AI Parsing Instructions**:
1. Extract `Status:` line for each section (CPU/MEMORY/DISK/NETWORK)
2. Collect components with `Status: WARNING` or `Status: CRITICAL`
3. Add those components to `deep_recommended` array
4. Generate user-friendly summary

---

## 📊 AI Output Format

**Present results to user in this format**:

```
⚡ Quick Scan Results (Xs)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ CPU: OK (queue 6 / 8 cores)
⚠️  Memory: WARNING (Swap 512MB in use)
✅ Disk: OK (I/O wait 3.2%)
❌ Network: CRITICAL (1500 drops)

🔬 Next: Deep Memory + Network analysis
```

**Status Icons**:
- ✅ OK
- ⚠️ WARNING  
- ❌ CRITICAL

**Action**: If any component shows WARNING/CRITICAL, **immediately and automatically** read the corresponding deep analysis file (see Next Steps below).

---

## ⚡ Individual Check Commands (Fallback Reference)

**Use these if Quick Scan Scripts are unavailable or you need to re-run a specific check.**

### Check 1: CPU Queue Saturation

**Command (Linux)**:
```bash
CPU_CORES=$(nproc)
RUN_QUEUE=$(vmstat 1 2 | tail -1 | awk '{print $1}')
echo "CPU Cores: $CPU_CORES"
echo "Run Queue: $RUN_QUEUE"
```

**Command (macOS)**:
```bash
CPU_CORES=$(sysctl -n hw.ncpu)
RUN_QUEUE=$(vm_stat 1 2 2>/dev/null | tail -1 | awk '{print $18}' || echo "0")
echo "CPU Cores: $CPU_CORES"
echo "Run Queue: $RUN_QUEUE"
```

**Command (Windows PowerShell)**:
```powershell
$CPU_CORES = (Get-WmiObject Win32_Processor).NumberOfLogicalProcessors
$RUN_QUEUE = (Get-Counter '\System\Processor Queue Length').CounterSamples.CookedValue
Write-Output "CPU Cores: $CPU_CORES"
Write-Output "Run Queue: $RUN_QUEUE"
```

**Thresholds**:
```yaml
OK: RUN_QUEUE <= CPU_CORES
WARNING: CPU_CORES < RUN_QUEUE <= CPU_CORES * 2
CRITICAL: RUN_QUEUE > CPU_CORES * 2
```

**AI Interpretation**:
- Extract `RUN_QUEUE` value from output
- Compare with `CPU_CORES`
- Classify status based on thresholds
- If WARNING/CRITICAL → add "cpu" to `deep_recommended`

---

### Check 2: Memory Swap Saturation

**Command (Linux)**:
```bash
SWAP_USED=$(free -m | awk '/Swap:/ {print $3}')
echo "Swap Used: ${SWAP_USED}MB"
```

**Command (macOS)**:
```bash
SWAP_USED=$(sysctl vm.swapusage 2>/dev/null | awk -F'[= ]' '{for(i=1;i<=NF;i++) if($i~/used/) print $(i+2)}' | sed 's/M//')
echo "Swap Used: ${SWAP_USED}MB"
```

**Command (Windows PowerShell)**:
```powershell
$PageFile = Get-WmiObject Win32_PageFileUsage
$SWAP_USED = [Math]::Round($PageFile.CurrentUsage)
Write-Output "Swap Used: ${SWAP_USED}MB"
```

**Thresholds**:
```yaml
OK: SWAP_USED < 100 MB
WARNING: 100 MB <= SWAP_USED < 1000 MB
CRITICAL: SWAP_USED >= 1000 MB
```

**AI Interpretation**:
- Extract `SWAP_USED` numeric value
- Compare with thresholds
- Note: ANY swap usage indicates memory pressure
- If WARNING/CRITICAL → add "memory" to `deep_recommended`

---

### Check 3: Disk I/O Wait

**Command (Linux)**:
```bash
if command -v iostat &> /dev/null; then
  IO_WAIT=$(iostat -x 1 2 | tail -n +4 | awk 'NF && !/^$/ {sum+=$4; count++} END {if(count>0) printf "%.1f", sum/count; else print "0"}')
  echo "I/O Wait: ${IO_WAIT}%"
else
  IO_WAIT=$(vmstat 1 2 | tail -1 | awk '{print $16}')
  echo "I/O Wait: ${IO_WAIT}% (vmstat wa)"
fi
```

**Command (macOS)**:
```bash
IO_WAIT=$(iostat -c 2 -w 1 disk0 | tail -1 | awk '{print $3}')
echo "I/O Wait: ${IO_WAIT}%"
```

**Command (Windows PowerShell)**:
```powershell
$DiskQueue = (Get-Counter '\PhysicalDisk(_Total)\Avg. Disk Queue Length').CounterSamples.CookedValue
$IO_WAIT = [Math]::Round($DiskQueue * 10, 1)
Write-Output "I/O Wait: ${IO_WAIT}%"
```

**Thresholds**:
```yaml
OK: IO_WAIT < 10%
WARNING: 10% <= IO_WAIT < 30%
CRITICAL: IO_WAIT >= 30%
```

**AI Interpretation**:
- Extract `IO_WAIT` percentage
- High I/O wait means CPU is idle waiting for disk
- If WARNING/CRITICAL → add "disk" to `deep_recommended`

---

### Check 4: Network Packet Drops

**Command (Linux)**:
```bash
# Measure drop RATE over 2 seconds (avoids false positives from cumulative counters)
RX1=$(ip -s link 2>/dev/null | grep -A1 "RX:" | awk 'NR%3==2 {sum+=$4} END {print sum+0}')
TX1=$(ip -s link 2>/dev/null | grep -A1 "TX:" | awk 'NR%3==2 {sum+=$4} END {print sum+0}')
sleep 2
RX2=$(ip -s link 2>/dev/null | grep -A1 "RX:" | awk 'NR%3==2 {sum+=$4} END {print sum+0}')
TX2=$(ip -s link 2>/dev/null | grep -A1 "TX:" | awk 'NR%3==2 {sum+=$4} END {print sum+0}')
RX_DROPS=$(( (RX2 - RX1) / 2 ))
TX_DROPS=$(( (TX2 - TX1) / 2 ))
echo "RX Drops: ${RX_DROPS}/s"
echo "TX Drops: ${TX_DROPS}/s"
```

**Command (macOS)**:
```bash
RX1=$(netstat -i -b 2>/dev/null | awk 'NR>1 {sum+=$9} END {print sum+0}')
TX1=$(netstat -i -b 2>/dev/null | awk 'NR>1 {sum+=$10} END {print sum+0}')
sleep 2
RX2=$(netstat -i -b 2>/dev/null | awk 'NR>1 {sum+=$9} END {print sum+0}')
TX2=$(netstat -i -b 2>/dev/null | awk 'NR>1 {sum+=$10} END {print sum+0}')
RX_DROPS=$(( (RX2 - RX1) / 2 ))
TX_DROPS=$(( (TX2 - TX1) / 2 ))
echo "RX Drops: ${RX_DROPS}/s"
echo "TX Drops: ${TX_DROPS}/s"
```

**Command (Windows PowerShell)**:
```powershell
$adapters = Get-NetAdapterStatistics
$RX_DROPS = ($adapters | Measure-Object ReceivedDiscardedPackets -Sum).Sum
$TX_DROPS = ($adapters | Measure-Object OutboundDiscardedPackets -Sum).Sum
Write-Output "RX Drops: $RX_DROPS"
Write-Output "TX Drops: $TX_DROPS"
```

**Thresholds**:
```yaml
OK: Total drop rate < 5/s
WARNING: 5/s <= Total drop rate < 50/s
CRITICAL: Total drop rate >= 50/s
```

**Note**: Linux/macOS measure a **2-second delta** (drop rate per second) to avoid false positives
on long-running servers where cumulative counters naturally accumulate. Windows uses instantaneous
counters which don't have this issue.

**AI Interpretation**:
- Sum RX_DROPS + TX_DROPS
- Packet drops indicate network saturation
- If WARNING/CRITICAL → add "network" to `deep_recommended`

---

## 🔗 Next Steps

**Based on Quick Mode results**:

- If **cpu** = WARNING/CRITICAL → Read `resource-saturation-deep-cpu.md`
- If **memory** = WARNING/CRITICAL → Read `resource-saturation-deep-memory.md`
- If **disk** = WARNING/CRITICAL → Read `resource-saturation-deep-disk.md`
- If **network** = WARNING/CRITICAL → Read `resource-saturation-deep-network.md`
- If **all OK** → Report healthy status, no further action needed

---

## 💡 Core Concept

**Saturation vs. Utilization**:
- **Utilization**: % of resource in use (can be high and still OK)
- **Saturation**: Work queued/waiting (always indicates bottleneck)

**Example**: CPU 90% utilized may be fine (busy processing), but CPU queue = 20 on 8 cores means **12 processes waiting** → performance degrading.

**This check focuses on Saturation** - the most predictive metric for performance issues.

---

**Last Updated**: 2026-03-27
**Compatibility**: Linux (primary), macOS (partial via adapters)
**Dependencies**: Basic (vmstat, free, ps, iostat recommended)
**Token Estimate**: ~600 tokens
