---
name: resource-saturation-check
description: Detect performance bottlenecks through saturation metrics with Quick (10s scan) and Deep (20-60s analysis) modes
category: standalone-checks
---

# Resource Saturation Check

**Purpose**: Detect performance bottlenecks **before** they become catastrophic through saturation metrics.

**Based on**: Brendan Gregg's USE Method (Saturation dimension) + Google SRE Four Golden Signals

**Modes**:
- ⚡ **Quick Mode**: 10-second 4-metric scan (CPU, Memory, Disk, Network)
- 🔬 **Deep Mode**: 20-60 second deep analysis of specific components

---

## 🎯 AI Usage Guide

### Quick Mode Workflow

```yaml
purpose: Fast triage to identify which components need deep analysis
duration: ~10 seconds
checks: 4 (CPU queue, Memory swap, Disk I/O wait, Network drops)

execution_steps:
  1. Run 4 quick check commands below
  2. Compare each result against thresholds
  3. Classify status: OK | WARNING | CRITICAL
  4. Recommend Deep analysis for WARNING/CRITICAL components

output_format:
  findings:
    cpu: OK | WARNING | CRITICAL
    memory: OK | WARNING | CRITICAL
    disk: OK | WARNING | CRITICAL
    network: OK | WARNING | CRITICAL
  deep_recommended: [list of components needing deep analysis]
```

### Deep Mode Workflow

```yaml
purpose: Root cause analysis and actionable recommendations
duration: 20-60 seconds per component
components: cpu | memory | disk | network

execution_steps:
  1. Navigate to Deep Mode section for target component
  2. Execute all check steps sequentially
  3. Apply root cause inference template
  4. Generate fix recommendations

output_format:
  component: <component_name>
  root_cause: <inferred cause>
  evidence: [list of supporting data]
  immediate_fix: [urgent actions]
  long_term_fix: [sustainable solutions]
```

---

## ⚡ Quick Mode (10 seconds)

> **Use this for**: Initial triage, health checks, "server is slow" questions

### Check 1: CPU Queue Saturation

**Command**:
```bash
CPU_CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu)
RUN_QUEUE=$(vmstat 1 2 | tail -1 | awk '{print $1}')
echo "CPU Cores: $CPU_CORES"
echo "Run Queue: $RUN_QUEUE"
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

**Command**:
```bash
# Linux
SWAP_USED=$(free -m 2>/dev/null | awk '/Swap:/ {print $3}')
# macOS fallback
if [ -z "$SWAP_USED" ]; then
  SWAP_USED=$(sysctl vm.swapusage 2>/dev/null | awk '{print $7}' | sed 's/M//')
fi
echo "Swap Used: ${SWAP_USED}MB"
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

**Command**:
```bash
# Requires sysstat package (iostat)
if command -v iostat &> /dev/null; then
  IO_WAIT=$(iostat -x 1 2 | tail -n +4 | awk 'NF && !/^$/ {sum+=$4; count++} END {if(count>0) printf "%.1f", sum/count; else print "0"}')
  echo "I/O Wait: ${IO_WAIT}%"
else
  # Fallback: use top/vmstat
  IO_WAIT=$(vmstat 1 2 | tail -1 | awk '{print $16}')
  echo "I/O Wait: ${IO_WAIT}% (vmstat wa)"
fi
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

**Command**:
```bash
if command -v ip &> /dev/null; then
  RX_DROPS=$(ip -s link | grep -A1 "RX:" | awk 'NR%3==2 {sum+=$4} END {print sum+0}')
  TX_DROPS=$(ip -s link | grep -A1 "TX:" | awk 'NR%3==2 {sum+=$4} END {print sum+0}')
  echo "RX Drops: $RX_DROPS"
  echo "TX Drops: $TX_DROPS"
else
  echo "Network stats unavailable (install iproute2)"
fi
```

**Thresholds**:
```yaml
OK: Total drops < 100
WARNING: 100 <= Total drops < 1000
CRITICAL: Total drops >= 1000
```

**AI Interpretation**:
- Sum RX_DROPS + TX_DROPS
- Packet drops indicate network saturation
- If WARNING/CRITICAL → add "network" to `deep_recommended`

---

### Quick Mode Output Template

**AI should generate**:

```json
{
  "mode": "quick",
  "duration": "10s",
  "timestamp": "<ISO 8601>",
  "findings": {
    "cpu": "WARNING",
    "memory": "OK",
    "disk": "OK",
    "network": "OK"
  },
  "deep_recommended": ["cpu"],
  "summary": "CPU queue saturation detected (run queue 16 > 8 cores), recommend deep CPU analysis"
}
```

**Human-friendly format**:

```
⚡ Quick Scan Results (10s)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ CPU: OK (queue 6 / 8 cores)
⚠️  Memory: WARNING (Swap 512MB in use)
✅ Disk: OK (I/O wait 3.2%)
✅ Network: OK (0 drops)

🔬 Recommended: Deep Memory analysis
```

---

## 🔬 Deep Mode (20-60 seconds)

> **Use this for**: Root cause analysis after Quick Mode identifies issues, or when user specifically requests detailed analysis

---

### Deep Mode: CPU Analysis

**Trigger**: Quick Mode CPU = WARNING/CRITICAL OR user requests CPU analysis

**Duration**: ~20 seconds

#### Step 1: Identify Top CPU Consumers

**Command**:
```bash
ps aux --sort=-%cpu | head -20 | awk 'BEGIN {print "PID\tUSER\tCPU%\tMEM%\tCOMMAND"} NR>1 {printf "%s\t%s\t%s%%\t%s%%\t%s\n", $2, $1, $3, $4, $11}'
```

**AI Analysis**:
- Identify processes with CPU > 50%
- Note if single process dominates (>70% on multi-core)
- Note if many processes evenly loaded

---

#### Step 2: Check CPU Frequency & Thermal Throttling

**Command**:
```bash
# Current CPU frequency
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

**AI Analysis**:
- Compare current MHz to nominal frequency
- If MHz < 80% of nominal → likely thermal throttling
- If temperature > 80°C → thermal issue
- Check dmesg for throttling events

---

#### Step 3: Load Average Trend

**Command**:
```bash
uptime
echo "Load average interpretation: 1min / 5min / 15min"
echo "CPU cores: $(nproc)"
```

**AI Analysis**:
- 1-min > 5-min > 15-min → load is decreasing (improving)
- 1-min < 5-min < 15-min → load is increasing (worsening)
- Load > 2x cores for 15min → sustained overload

---

#### Root Cause Inference Template

**AI should apply**:

```yaml
Scenario 1: Process Runaway
  conditions:
    - Single process CPU > 50%
    - Run queue high
    - Process not expected to consume CPU
  root_cause: "Process <name> (PID <pid>) consuming <cpu>% CPU"
  immediate_fix: 
    - "Restart process: sudo systemctl restart <service>"
    - "Or kill: sudo kill -9 <pid>"
  long_term_fix:
    - "Investigate why process is consuming CPU"
    - "Check for infinite loops in application code"
    - "Review recent code changes"

Scenario 2: Thermal Throttling
  conditions:
    - CPU frequency < 80% of nominal
    - Temperature > 80°C
    - Run queue moderate
  root_cause: "CPU thermal throttling due to overheating"
  immediate_fix:
    - "Improve airflow around server"
    - "Clean dust from heatsink/fans"
  long_term_fix:
    - "Replace thermal paste"
    - "Upgrade cooling solution"
    - "Reduce ambient temperature"

Scenario 3: Sustained Overload
  conditions:
    - Multiple processes evenly loaded
    - 15-min load > 2x cores
    - No single culprit
  root_cause: "Legitimate workload exceeding CPU capacity"
  immediate_fix:
    - "Defer non-critical tasks"
    - "Temporarily disable background jobs"
  long_term_fix:
    - "Add more CPU cores (vertical scaling)"
    - "Distribute load (horizontal scaling)"
    - "Optimize application efficiency"

Scenario 4: Context Switching Storm
  conditions:
    - High run queue
    - Many lightweight processes
    - Low individual CPU usage
  root_cause: "Excessive context switching overhead"
  immediate_fix:
    - "Consolidate processes if possible"
    - "Check for fork bombs: ps aux | wc -l"
  long_term_fix:
    - "Increase process niceness for background tasks"
    - "Use process pooling instead of spawning"
```

---

### Deep Mode: Memory Analysis

**Trigger**: Quick Mode Memory = WARNING/CRITICAL OR user requests memory analysis

**Duration**: ~25 seconds

#### Step 1: Top Memory Consumers

**Command**:
```bash
ps aux --sort=-%mem | head -20 | awk 'BEGIN {print "PID\tUSER\tCPU%\tMEM%\tRSS(MB)\tCOMMAND"} NR>1 {printf "%s\t%s\t%s%%\t%s%%\t%.1f\t%s\n", $2, $1, $3, $4, $6/1024, $11}'
```

**AI Analysis**:
- Identify processes with MEM% > 20%
- Note RSS (Resident Set Size) in MB
- Flag if single process > 50% memory

---

#### Step 2: Memory Leak Detection

**Command**:
```bash
echo "Sampling memory usage 3 times over 15 seconds..."
for i in 1 2 3; do
  echo "Sample $i:"
  ps aux --sort=-%mem | head -5 | awk 'NR>1 {printf "  PID %s: RSS %.1fMB\n", $2, $6/1024}'
  sleep 5
done
```

**AI Analysis**:
- Compare RSS across 3 samples
- If RSS increases > 100MB/15s → likely memory leak
- Consistent RSS → not leaking, just high usage

---

#### Step 3: Swap Activity Analysis

**Command**:
```bash
# Check swap usage trend
vmstat 1 5 | awk 'BEGIN {print "Time\tSwapIn\tSwapOut"} NR>2 {print NR-2 "\t" $7 "\t" $8}'

# Total swap usage
free -h | grep Swap
```

**AI Analysis**:
- Swap In (si) = reading from swap (slow)
- Swap Out (so) = writing to swap
- Sustained si > 100 KB/s = active thrashing
- so > 1000 KB/s = critical memory pressure

---

#### Root Cause Inference Template

**AI should apply**:

```yaml
Scenario 1: Memory Leak
  conditions:
    - Single process MEM% > 30%
    - RSS growing > 100MB/15s
    - Swap activity increasing
  root_cause: "Memory leak in <process_name>"
  immediate_fix:
    - "Restart leaking process: sudo systemctl restart <service>"
  long_term_fix:
    - "Fix memory leak in application code"
    - "Use valgrind/heaptrack to identify leak"
    - "Implement periodic restarts as temporary workaround"

Scenario 2: Insufficient Memory
  conditions:
    - Multiple processes high memory
    - Total usage > 90%
    - No single leak detected
  root_cause: "Legitimate memory demand exceeds capacity"
  immediate_fix:
    - "Stop non-critical services"
    - "Clear caches: sync; echo 3 > /proc/sys/vm/drop_caches"
  long_term_fix:
    - "Add more RAM"
    - "Optimize application memory usage"
    - "Enable zram compression"

Scenario 3: Memory Fragmentation
  conditions:
    - Free memory available
    - Allocation failures in dmesg
    - High swap despite free memory
  root_cause: "Memory fragmentation preventing large allocations"
  immediate_fix:
    - "Trigger compaction: echo 1 > /proc/sys/vm/compact_memory"
  long_term_fix:
    - "Reboot to defragment"
    - "Increase vm.min_free_kbytes"
    - "Use hugepages for large allocations"

Scenario 4: Cache Pressure
  conditions:
    - High page cache usage
    - Swap active despite available cache
    - vm.swappiness high
  root_cause: "System swapping applications to preserve cache"
  immediate_fix:
    - "Reduce swappiness: sysctl vm.swappiness=10"
  long_term_fix:
    - "Tune vm.swappiness permanently in /etc/sysctl.conf"
    - "Reduce cache-heavy workloads"
```

---

### Deep Mode: Disk Analysis

**Trigger**: Quick Mode Disk = WARNING/CRITICAL OR user requests disk analysis

**Duration**: ~30 seconds

#### Step 1: Identify I/O-Heavy Processes

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

#### Step 2: Disk Queue and Latency

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

#### Step 3: SMART Health Check

**Command**:
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

#### Root Cause Inference Template

**AI should apply**:

```yaml
Scenario 1: Process I/O Storm
  conditions:
    - Single process dominant I/O
    - Disk utilization > 80%
    - SMART healthy
  root_cause: "Process <name> generating excessive I/O"
  immediate_fix:
    - "Throttle I/O: ionice -c 3 -p <pid>"
    - "Or restart: sudo systemctl restart <service>"
  long_term_fix:
    - "Optimize application I/O patterns (batching, caching)"
    - "Use faster storage (SSD, NVMe)"

Scenario 2: Disk Hardware Failure
  conditions:
    - SMART health = FAILED
    - Reallocated sectors > 10
    - High latency (>100ms)
  root_cause: "Disk hardware failure imminent"
  immediate_fix:
    - "🚨 BACKUP DATA NOW"
    - "Prepare for disk replacement"
  long_term_fix:
    - "Replace failing disk"
    - "Restore from backup"

Scenario 3: Filesystem Fragmentation
  conditions:
    - Read latency high
    - Write latency normal
    - Old filesystem (ext3/ext4)
  root_cause: "Filesystem fragmentation"
  immediate_fix:
    - "Check fragmentation: e4defrag -c /"
  long_term_fix:
    - "Defragment: e4defrag /"
    - "Consider migration to XFS/Btrfs"

Scenario 4: Insufficient I/O Bandwidth
  conditions:
    - Multiple processes high I/O
    - Disk utilization 100%
    - SMART healthy
  root_cause: "Legitimate I/O demand exceeds disk capacity"
  immediate_fix:
    - "Defer non-critical I/O"
    - "Increase readahead: blockdev --setra 4096 /dev/sda"
  long_term_fix:
    - "Upgrade to SSD/NVMe"
    - "Add more disks (RAID 0/10)"
    - "Use I/O scheduler tuning (noop for SSD)"
```

---

### Deep Mode: Network Analysis

**Trigger**: Quick Mode Network = WARNING/CRITICAL OR user requests network analysis

**Duration**: ~20 seconds

#### Step 1: Interface Statistics

**Command**:
```bash
ip -s link show | awk '/^[0-9]+:/ {iface=$2} /RX:|TX:/ {getline; if (iface) print iface, $0; iface=""}'
```

**AI Analysis**:
- Errors > 100 → physical layer issues
- Drops > 1000 → buffer overflow
- Overruns → NIC cannot keep up with traffic

---

#### Step 2: Connection Saturation

**Command**:
```bash
ss -s
netstat -s | grep -E "overflow|drop|failed" | head -10
```

**AI Analysis**:
- Listen queue overflow → accept() too slow
- Connection refused → port not listening
- Retransmits → packet loss on network

---

#### Step 3: Bandwidth Utilization

**Command**:
```bash
if command -v iftop &> /dev/null; then
  echo "Top bandwidth consumers (requires root):"
  sudo iftop -t -s 5 -n
else
  echo "iftop not installed"
  echo "Current RX/TX rates:"
  for iface in $(ip -o link show | awk -F': ' '{print $2}' | grep -v lo); do
    RX1=$(cat /sys/class/net/$iface/statistics/rx_bytes 2>/dev/null)
    TX1=$(cat /sys/class/net/$iface/statistics/tx_bytes 2>/dev/null)
    sleep 1
    RX2=$(cat /sys/class/net/$iface/statistics/rx_bytes 2>/dev/null)
    TX2=$(cat /sys/class/net/$iface/statistics/tx_bytes 2>/dev/null)
    RX_RATE=$(( (RX2 - RX1) / 1024 ))
    TX_RATE=$(( (TX2 - TX1) / 1024 ))
    echo "$iface: RX ${RX_RATE}KB/s, TX ${TX_RATE}KB/s"
  done
fi
```

**AI Analysis**:
- Compare rates to link capacity
- Sustained >80% utilization → bandwidth saturation
- Asymmetric RX/TX → identify direction of bottleneck

---

#### Root Cause Inference Template

**AI should apply**:

```yaml
Scenario 1: Listen Queue Overflow
  conditions:
    - netstat shows listen queue overflows
    - Connection refused errors
    - Application accept() rate low
  root_cause: "Application cannot accept connections fast enough"
  immediate_fix:
    - "Increase backlog: sysctl -w net.core.somaxconn=4096"
    - "Increase app listen backlog parameter"
  long_term_fix:
    - "Scale application horizontally (more instances)"
    - "Optimize application accept() loop"

Scenario 2: Physical Layer Errors
  conditions:
    - Interface errors > 100
    - Drops and overruns high
    - SMART healthy
  root_cause: "Physical network issues (cable, NIC, switch)"
  immediate_fix:
    - "Check cable connections"
    - "Test with different cable"
  long_term_fix:
    - "Replace faulty cable/NIC"
    - "Check switch port health"

Scenario 3: Bandwidth Saturation
  conditions:
    - Utilization > 80% sustained
    - Packet drops increasing
    - No errors
  root_cause: "Network bandwidth exceeded"
  immediate_fix:
    - "Identify top bandwidth consumers"
    - "Rate-limit non-critical traffic"
  long_term_fix:
    - "Upgrade link capacity (1G → 10G)"
    - "Implement QoS/traffic shaping"
    - "Offload traffic to separate network"

Scenario 4: TCP Retransmits
  conditions:
    - High retransmit count in netstat -s
    - Normal interface statistics
    - Intermittent connectivity
  root_cause: "Packet loss in network path"
  immediate_fix:
    - "Test path: mtr <destination>"
    - "Check for congestion at router/ISP"
  long_term_fix:
    - "Contact ISP if external issue"
    - "Tune TCP parameters (window scaling)"
```

---

## 💡 Complete Usage Examples

### Example 1: User says "Server is slow"

**AI Workflow**:

```
1. Execute Quick Mode (all 4 checks)
   Duration: 10s
   
2. Quick Results:
   CPU: OK (queue 6 / 8 cores)
   Memory: WARNING (Swap 512MB)
   Disk: OK (I/O wait 3%)
   Network: OK (0 drops)
   
3. Decision: Memory WARNING → Auto Deep Memory
   
4. Execute Deep Memory Analysis
   Step 1: ps aux --sort=-%mem | head -20
   Step 2: Memory leak detection (15s sampling)
   Step 3: vmstat swap activity
   
5. Apply Root Cause Inference:
   - MySQL占用8.2GB (82%)
   - RSS growing 100MB/15s
   - Swap in > 100 KB/s
   → Scenario 1: Memory Leak
   
6. Generate Report:
   Root Cause: MySQL memory leak
   Immediate Fix: sudo systemctl restart mysql
   Long-term: Fix leak, optimize innodb_buffer_pool_size
   
Total Duration: 35 seconds
Total Token: ~1200 (Quick 200 + Deep 500 + Report 500)
```

---

### Example 2: User says "Check system health"

**AI Workflow**:

```
1. Execute Quick Mode (all 4 checks)
   Duration: 10s
   
2. Quick Results:
   CPU: OK
   Memory: OK
   Disk: OK
   Network: OK
   
3. Decision: All OK → No Deep needed
   
4. Generate Report:
   ✅ System healthy
   All saturation metrics within normal range
   No action required
   
Total Duration: 13 seconds (Quick 10s + Report 3s)
Total Token: ~300 (Quick 200 + Report 100)
```

---

### Example 3: User says "Detailed CPU analysis"

**AI Workflow**:

```
1. User explicit request → Skip Quick, go directly to Deep CPU
   
2. Execute Deep CPU Analysis:
   Step 1: Top CPU processes
   Step 2: CPU frequency & thermal
   Step 3: Load average trend
   
3. Findings:
   - Node.js process 95% CPU
   - Frequency normal
   - Load increasing trend
   
4. Apply Root Cause Inference:
   → Scenario 1: Process Runaway
   
5. Generate Report:
   Root Cause: Node.js infinite loop
   Immediate Fix: sudo systemctl restart node-app
   Long-term: Debug application code
   
Total Duration: 23 seconds
Total Token: ~600 (Deep 500 + Report 100)
```

---

## 🔗 Related Checks

**After Quick/Deep analysis, consider**:

- If disk issues → Run `disk-smart.md` for hardware health
- If crashes mentioned → Run `system-logs.md` for error analysis  
- If hardware suspected → Run `hardware-other.md` for sensors
- If time errors → Run `time-sync.md` for NTP status

---

## 📊 Key Concepts

### Saturation vs. Utilization

- **Utilization**: % of resource in use (can be high and fine)
- **Saturation**: Work queued/waiting (always bad, indicates bottleneck forming)

**Example**: 
- CPU 90% utilized → May be fine (processing requests)
- CPU queue = 20 on 8 cores → **Critical** (12 processes waiting, performance degrading)

### USE Method (Brendan Gregg)

For every resource, check:
- **U**tilization: % busy
- **S**aturation: Queued work (this check)
- **E**rrors: Error events

**This check focuses on Saturation** - the most predictive metric.

---

**Last Updated**: 2026-03-24
**Compatibility**: Linux (primary), macOS (partial)
**Dependencies**: Basic (vmstat, free, ps, iostat recommended)
