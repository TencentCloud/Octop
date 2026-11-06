---
name: resource-saturation-deep-combined
description: Multi-component correlation analysis with decision tree logic (30-45 seconds)
category: standalone-checks
mode: deep
component: combined
---

# Resource Saturation Deep Analysis - Combined

**Purpose**: Identify root cause when multiple system components show abnormal metrics through correlation analysis.

**Duration**: ~30-45 seconds

**Trigger**: Quick Mode shows 2+ components with WARNING/CRITICAL OR user reports complex symptoms ("slow but metrics look normal")

---

## 🎯 When to Use This Module

**Use Combined Analysis if ANY of these:**
1. Quick Mode flags 2+ components (e.g., CPU + Memory both yellow/red)
2. User describes cascading issues ("memory high, then swap starts, then disk slow")
3. Single-component Deep Mode fails to explain the symptom
4. User explicitly asks "what's the root cause of everything"

**Skip Combined if:**
- Only 1 component is abnormal → Use single-component Deep Mode
- All metrics are green → No issue detected

---

## ⚡ 脚本优先路径（Script-First Path）

若 `scripts/combined_analysis.sh` 存在，**优先调用脚本执行决策树**，跳过手动逐分支判断：

```bash
bash scripts/combined_analysis.sh \
  --mem-pct <mem_pct> \
  --swap-gb <swap_used_gb> \
  --iowait <iowait_pct> \
  --cpu-pct <cpu_pct> \
  --load-ratio <load_ratio> \
  --disk-pct <disk_root_pct> \
  --sys-pct <sys_pct> \
  --net-throughput-mbps <net_mbps> \
  --user-pct <user_pct> \
  --cpu-freq-ratio <current_mhz/max_mhz> \
  --cpu-temp <cpu_temp_celsius>
```

脚本输出 branch 编号、root_cause 键、置信度、匹配条件及推荐深度分析文件。
收到 JSON 后，直接套用对应 branch 的叙述模板生成报告，跳过以下手动决策树。

若脚本不存在，按以下手动决策树执行。

---

## 🧬 Decision Tree Logic

### Branch 1: Memory-Triggered Cascade

**Pattern Recognition**:
```yaml
IF Memory >= 90% AND Swap > 1GB AND I/O wait > 20%:
  ROOT_CAUSE: Memory shortage cascading to disk thrashing
  
  EVIDENCE_CHAIN:
    1. System runs out of RAM
    2. Kernel swaps inactive pages to disk
    3. Disk I/O spikes (swap in/out)
    4. CPU wait% increases (waiting for disk)
    5. Applications slow down (page faults)
  
  PRIMARY_FIX: Add RAM (priority #1)
  SECONDARY_FIX: Reduce memory-hungry processes
  WRONG_FIX: ❌ Do NOT add CPU (won't help)
```

**Diagnostic Commands**:
```bash
# Step 1: Confirm memory pressure
free -h
vmstat 1 5 | tail -4

# Step 2: Verify swap activity
vmstat -s | grep -E "swap|page"

# Step 3: Identify memory hogs
ps aux --sort=-%mem | head -10 | awk '{printf "%-10s %6s %6s %s\n", $1, $3, $4, $11}'

# Step 4: Check OOM killer activity
dmesg | tail -100 | grep -i "out of memory\|oom\|kill" | tail -5
```

**AI Analysis**:
- Calculate memory pressure: (Used - Buffers - Cached) / Total
- If Swap usage > 50% of RAM → severe memory shortage
- If `vmstat` shows high `si` (swap in) or `so` (swap out) → active thrashing
- If dmesg shows OOM kills → system already killed processes

---

### Branch 2: CPU-Triggered Load Spike

**Pattern Recognition**:
```yaml
IF CPU > 80% AND Load Average > (Cores * 2) AND Memory < 70%:
  ROOT_CAUSE: CPU bottleneck (insufficient compute capacity)
  
  EVIDENCE_CHAIN:
    1. Process/threads demand exceeds CPU cores
    2. Load average climbs (runnable processes queued)
    3. Context switching increases
    4. Applications experience delays
  
  PRIMARY_FIX: Optimize hot processes OR add CPU cores
  SECONDARY_FIX: Move workload to another server
  WRONG_FIX: ❌ Adding RAM won't help if memory is OK
```

**Diagnostic Commands**:
```bash
# Step 1: Confirm CPU saturation
uptime  # Check load average vs CPU cores
mpstat -P ALL 1 3 | tail -10  # Per-core usage

# Step 2: Identify CPU hogs
ps aux --sort=-%cpu | head -10 | awk '{printf "%-10s %6s %6s %s\n", $1, $3, $4, $11}'

# Step 3: Check context switching rate
vmstat 1 5 | tail -4  # High 'cs' column = excessive switching

# Step 4: Verify I/O is not blocking CPU
iostat -x 2 3 | grep -E "Device|avg"  # Check %iowait
```

**AI Analysis**:
- If load average > (cores × 1.5) → CPU overloaded
- If context switches > 10,000/sec → possible lock contention
- If %iowait < 10% → confirms CPU-bound (not I/O-bound)
- If single process uses > 95% on 1 core → check for infinite loop

---

### Branch 3: Disk I/O Cascade

**Pattern Recognition**:
```yaml
IF Disk util > 90% AND I/O wait > 30% AND Memory OK AND Swap OK:
  ROOT_CAUSE: Disk bottleneck (slow storage or excessive I/O)
  
  EVIDENCE_CHAIN:
    1. Application/kernel generates heavy I/O
    2. Disk queue depth increases (await > 50ms)
    3. CPU enters I/O wait state (blocked)
    4. Applications slow down (waiting for disk)
  
  PRIMARY_FIX: Identify I/O source (process/file) and optimize
  SECONDARY_FIX: Upgrade to faster storage (SSD/NVMe)
  WRONG_FIX: ❌ Adding CPU/RAM won't help disk bottleneck
```

**Diagnostic Commands**:
```bash
# Step 1: Confirm disk saturation
iostat -x 2 3 | grep -E "Device|avg"  # Check %util and await

# Step 2: Find I/O-heavy processes
iotop -b -n 3 -d 2 -P -o 2>/dev/null || echo "iotop not installed, using backup method"
pidstat -d 2 3 | grep -v "^#" | tail -10

# Step 3: Check disk queue depth
cat /proc/diskstats | awk '{if ($4 > 0) printf "%s: %d reads, %d writes, %d in-flight\n", $3, $4, $8, $9}'

# Step 4: Verify filesystem health
df -h  # Check if any partition near full
mount | grep -E "ext4|xfs" | head -5
```

**AI Analysis**:
- If `await` > 100ms → extremely slow disk
- If `%util` = 100% sustained → disk saturated
- If I/O wait% > 50% → CPU mostly waiting for disk
- If `/` partition > 90% full → may trigger CoW/journal slowdown

---

### Branch 4: Network + CPU Combined Load

**Pattern Recognition**:
```yaml
IF CPU sys% > 40% AND Network throughput high AND CPU user% < 30%:
  ROOT_CAUSE: Network interrupt storm overloading kernel
  
  EVIDENCE_CHAIN:
    1. High network traffic triggers interrupts
    2. CPU spends time in kernel space (sys%)
    3. User processes starved (low user%)
    4. softirq% increases (network stack processing)
  
  PRIMARY_FIX: Enable IRQ affinity OR use NAPI
  SECONDARY_FIX: Offload network processing (hardware offload)
  WRONG_FIX: ❌ Killing user processes won't help (they're not the cause)
```

**Diagnostic Commands**:
```bash
# Step 1: Confirm sys% dominance
mpstat 1 3 | tail -3  # Check %sys vs %usr

# Step 2: Check interrupt rate
cat /proc/interrupts | grep -E "eth|ens|eno" | head -5
vmstat 1 3 | tail -3  # Check 'in' column (interrupts/sec)

# Step 3: Identify network throughput
sar -n DEV 1 3 | grep -v "^$" | tail -10

# Step 4: Check softirq CPU time
mpstat -I SUM 1 3 | tail -3  # Look for high %soft
```

**AI Analysis**:
- If sys% > 3× usr% → kernel bottleneck
- If interrupts > 50,000/sec → possible interrupt storm
- If softirq% > 20% → network stack overloaded
- If specific NIC shows high packet rate → focus on that interface

---

### Branch 5: Thermal Throttling Chain

**Pattern Recognition**:
```yaml
IF CPU frequency < 80% nominal AND CPU temp > 80°C AND load exists:
  ROOT_CAUSE: Thermal throttling reducing performance
  
  EVIDENCE_CHAIN:
    1. CPU heats up under load
    2. Thermal protection throttles frequency
    3. Performance drops (lower MHz)
    4. Tasks take longer (higher wait time)
  
  PRIMARY_FIX: Improve cooling (clean fans, airflow)
  SECONDARY_FIX: Reduce workload temporarily
  WRONG_FIX: ❌ Software optimization won't help hardware thermal issue
```

**Diagnostic Commands**:
```bash
# Step 1: Check current CPU frequency
cat /proc/cpuinfo | grep "MHz" | head -4
lscpu | grep "MHz"

# Step 2: Check thermal sensors
sensors 2>/dev/null | grep -E "Core |Package" || echo "lm-sensors not installed"

# Step 3: Check throttling events
dmesg | tail -100 | grep -i "thermal\|throttle" | tail -5

# Step 4: Verify power management state
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | head -4
```

**AI Analysis**:
- Compare current MHz to `lscpu | grep "max MHz"`
- If current < 80% max → throttling active
- If dmesg shows "temperature above threshold" → thermal issue confirmed
- If governor = "powersave" → may be intentionally limited

---

## 📊 Multi-Component Summary Template

After running decision tree, provide this summary:

```markdown
## 🎯 Root Cause Analysis

**Primary Issue**: [Memory shortage / CPU overload / Disk bottleneck / Network storm / Thermal throttling]

**Evidence Chain**:
1. [First metric that triggered the cascade]
2. [Secondary effect observed]
3. [Final symptom user experienced]

**Why Other Components Are Affected**:
- Component A is [high/slow] BECAUSE [explanation]
- Component B is [affected] AS A RESULT OF [root cause]

**Priority Fix**:
```bash
[Exact command or action to resolve root cause]
```

**Expected Outcome**: [What user should see after fix]

**Wrong Approaches to Avoid**:
- ❌ [Common but ineffective fix]
- ❌ [Another misguided attempt]
```

---

## 🔄 Workflow Integration

**In SKILL.md workflow**:
```yaml
Step 3: Deep Analysis Decision
  
  IF Quick Mode shows 1 component abnormal:
    → Use single-component Deep (cpu/memory/disk/network)
  
  ELSE IF Quick Mode shows 2+ components abnormal:
    → Use Combined Deep (this module)
  
  ELSE IF user says "everything looks normal but it's slow":
    → Run Quick Mode again AND review Combined Deep decision tree
```

---

## ⚠️ Important Notes

1. **Always verify assumptions**: Decision tree provides hypothesis, not guaranteed truth
2. **Check temporal sequence**: Which metric spiked first? (use `sar -A` for history)
3. **Consider external factors**: Cron jobs, backups, or external network events
4. **User confirmation**: Ask user if fix aligns with their symptom timeline
5. **Document baseline**: Compare current state to historical normal values if available

---

## 📚 References

For single-component analysis, refer to:
- CPU only: `resource-saturation-deep-cpu.md`
- Memory only: `resource-saturation-deep-memory.md`
- Disk only: `resource-saturation-deep-disk.md`
- Network only: `resource-saturation-deep-network.md`

---

---

> 📊 分析完成后静默执行: `bash scripts/log_stats.sh deep combined <os> 0 <cpu> <mem> <disk> <net> user`
