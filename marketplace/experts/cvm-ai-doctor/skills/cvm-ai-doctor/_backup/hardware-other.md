---
name: hardware-health-check
description: Monitor CPU temperature, memory ECC errors, RAID status, power supply health
category: standalone-checks
---

# Hardware Health Check (CPU/Memory/RAID/Power)

**Purpose**: Monitor non-disk hardware health - CPU temperature, memory ECC errors, RAID status, power supply.

**Why critical**: Hardware failures often show early warning signs that can prevent catastrophic outages.

**Aligns with USE Method**: Errors dimension for hardware resources.

---

## 🎯 AI Usage Guide

### Quick/Deep Workflow

```mermaid
User Question → Quick Mode (10s) → Analyze → Deep Mode (20-40s, if issues)
```

**When to use each mode**:

| Mode | Duration | Purpose | When to Use |
|------|----------|---------|-------------|
| **Quick** | 10s | Check status of all 4 components | Health check, "检查硬件", daily routine |
| **Deep** | 20-40s | Detailed analysis + troubleshooting | Quick shows issues, specific problem |

**Decision Logic**:
```yaml
Quick Mode Results:
  - All OK → Stop, report healthy
  - CPU CRITICAL (>95°C) → Deep Mode: CPU temperature
  - Memory CRITICAL (UE > 0) → Deep Mode: Memory errors
  - RAID degraded → Deep Mode: RAID status
  - Any WARNING → User decides if Deep needed

Components:
  1. CPU Temperature (overheating → throttling)
  2. Memory ECC Errors (data corruption → crashes)
  3. RAID Status (degradation → data loss risk)
  4. Battery/Power (for laptops/UPS)
```

**Output Format**:

```yaml
# Quick Mode
status: OK | WARNING | CRITICAL
components:
  cpu_temp: {max: N°C, status: OK/WARNING/CRITICAL}
  memory_ecc: {ce: N, ue: N, status: OK/WARNING/CRITICAL}
  raid: {state: optimal/degraded/failed, status: OK/WARNING/CRITICAL}
  battery: {health: N%, status: OK/WARNING}
next_action: "stop" | "deep_cpu" | "deep_memory" | "deep_raid"

# Deep Mode
component: cpu | memory | raid | battery
root_cause: "Identified issue"
evidence: ["detail 1", "detail 2"]
impact: "What will happen"
recommendation: ["immediate action", "long-term fix"]
```

---

## ⚡ Quick Mode (10s)

**Purpose**: Status check for 4 hardware components

---

### 1. CPU Temperature Check

```bash
# Linux (lm-sensors)
if command -v sensors &>/dev/null; then
  MAX_TEMP=$(sensors 2>/dev/null | grep -i "core\|package" | grep -oP '\+\K[0-9]+' | sort -rn | head -1)
  if [ -n "$MAX_TEMP" ]; then
    echo "CPU: ${MAX_TEMP}°C"
    [ "$MAX_TEMP" -gt 95 ] && echo "[CRITICAL]" || [ "$MAX_TEMP" -gt 80 ] && echo "[WARNING]" || echo "[OK]"
  else
    echo "CPU: Temperature unavailable"
  fi
else
  echo "CPU: lm-sensors not installed"
fi

# Alternative: sysfs thermal zones
if [ ! -x "$(command -v sensors)" ]; then
  for zone in /sys/class/thermal/thermal_zone*/temp; do
    if [ -r "$zone" ]; then
      TEMP_C=$(($(cat "$zone") / 1000))
      echo "Thermal zone: ${TEMP_C}°C"
    fi
  done
fi
```

```bash
# macOS
if command -v powermetrics &>/dev/null; then
  sudo powermetrics --samplers smc -i1 -n1 2>/dev/null | grep -i "CPU die temperature" | head -1
else
  echo "CPU: powermetrics requires root"
fi
```

```powershell
# Windows
$thermalInfo = Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi -ErrorAction SilentlyContinue
if ($thermalInfo) {
  $tempC = ($thermalInfo[0].CurrentTemperature / 10.0) - 273.15
  Write-Host "CPU: $([math]::Round($tempC, 1))°C"
}
```

**Thresholds**:
```yaml
CRITICAL: > 95°C (thermal throttling/damage)
WARNING: 80-95°C (elevated)
OK: < 80°C
```

---

### 2. Memory ECC Errors Check

```bash
# Linux (EDAC)
if [ -d /sys/devices/system/edac/mc ]; then
  TOTAL_CE=0
  TOTAL_UE=0
  for mc in /sys/devices/system/edac/mc/mc*/; do
    if [ -f "$mc/ce_count" ]; then
      CE=$(cat "$mc/ce_count")
      UE=$(cat "$mc/ue_count")
      TOTAL_CE=$((TOTAL_CE + CE))
      TOTAL_UE=$((TOTAL_UE + UE))
    fi
  done
  
  echo "Memory: CE=$TOTAL_CE, UE=$TOTAL_UE"
  [ "$TOTAL_UE" -gt 0 ] && echo "[CRITICAL]" || [ "$TOTAL_CE" -gt 1000 ] && echo "[WARNING]" || echo "[OK]"
else
  echo "Memory: EDAC not supported/loaded"
fi
```

```bash
# macOS
echo "Memory: ECC check not available on macOS"
```

```powershell
# Windows
$memory = Get-WmiObject Win32_PhysicalMemory | Select *ECC*
if ($memory) {
  Write-Host "Memory: ECC capable"
} else {
  Write-Host "Memory: Non-ECC memory"
}
```

**Thresholds**:
```yaml
CRITICAL: UE (Uncorrectable Errors) > 0
WARNING: CE (Correctable Errors) > 1000
OK: Low/no errors
```

---

### 3. RAID Status Check

```bash
# Linux Software RAID (mdadm)
if [ -f /proc/mdstat ]; then
  if grep -q "_" /proc/mdstat; then
    echo "RAID: DEGRADED [CRITICAL]"
  elif grep -q "recovering\|resyncing" /proc/mdstat; then
    PROGRESS=$(grep -oP '\[\K[0-9]+%' /proc/mdstat)
    echo "RAID: Rebuilding ${PROGRESS} [WARNING]"
  else
    echo "RAID: Optimal [OK]"
  fi
else
  echo "RAID: No software RAID detected"
fi

# Hardware RAID (MegaRAID example)
if command -v megacli &>/dev/null; then
  RAID_STATE=$(megacli -LDInfo -Lall -aAll 2>/dev/null | grep "State" | awk '{print $NF}')
  echo "RAID (Hardware): $RAID_STATE"
fi
```

```bash
# macOS
RAID_INFO=$(diskutil appleRAID list 2>/dev/null)
if [ -n "$RAID_INFO" ]; then
  echo "$RAID_INFO"
else
  echo "RAID: No Apple RAID configured"
fi
```

```powershell
# Windows Storage Spaces
$vdisks = Get-VirtualDisk -ErrorAction SilentlyContinue
if ($vdisks) {
  foreach ($vd in $vdisks) {
    Write-Host "RAID: $($vd.FriendlyName) - $($vd.HealthStatus)"
  }
} else {
  Write-Host "RAID: No virtual disks found"
}
```

**Thresholds**:
```yaml
CRITICAL: Degraded or Failed
WARNING: Rebuilding
OK: Optimal/Clean
```

---

### 4. Battery/Power Check

```bash
# Linux (laptops)
if command -v upower &>/dev/null; then
  if upower -d 2>/dev/null | grep -q "battery"; then
    HEALTH=$(upower -d 2>/dev/null | awk '/capacity:/ {print $2}' | head -1 | tr -d '%')
    PERCENT=$(upower -d 2>/dev/null | awk '/percentage:/ {print $2}' | head -1)
    echo "Battery: ${PERCENT}, Health: ${HEALTH}%"
    [ -n "$HEALTH" ] && [ "$HEALTH" -lt 50 ] && echo "[WARNING]" || echo "[OK]"
  else
    echo "Battery: No battery (desktop/server)"
  fi
else
  echo "Battery: upower not available"
fi
```

```bash
# macOS
pmset -g batt
```

```powershell
# Windows
$battery = Get-WmiObject Win32_Battery -ErrorAction SilentlyContinue
if ($battery) {
  Write-Host "Battery: $($battery.EstimatedChargeRemaining)%"
}
```

**Thresholds**:
```yaml
WARNING: Health < 50% (degraded battery)
OK: Health ≥ 50%
```

---

### Quick Mode Complete Script

```bash
#!/bin/bash
# Quick Mode: Hardware Health Check (10 seconds)

echo "=== Quick Mode: Hardware Health ==="

CRITICALS=0
WARNINGS=0

# 1. CPU Temperature
if command -v sensors &>/dev/null; then
  MAX_TEMP=$(sensors 2>/dev/null | grep -i "core\|package" | grep -oP '\+\K[0-9]+' | sort -rn | head -1)
  if [ -n "$MAX_TEMP" ]; then
    echo "CPU: ${MAX_TEMP}°C"
    if [ "$MAX_TEMP" -gt 95 ]; then
      echo "  [CRITICAL] Overheating"
      ((CRITICALS++))
    elif [ "$MAX_TEMP" -gt 80 ]; then
      echo "  [WARNING] Elevated temperature"
      ((WARNINGS++))
    else
      echo "  [OK]"
    fi
  fi
else
  echo "CPU: Sensor unavailable"
fi

# 2. Memory ECC
if [ -d /sys/devices/system/edac/mc ]; then
  TOTAL_CE=0
  TOTAL_UE=0
  for mc in /sys/devices/system/edac/mc/mc*/; do
    [ -f "$mc/ce_count" ] && CE=$(cat "$mc/ce_count") && TOTAL_CE=$((TOTAL_CE + CE))
    [ -f "$mc/ue_count" ] && UE=$(cat "$mc/ue_count") && TOTAL_UE=$((TOTAL_UE + UE))
  done
  
  echo "Memory: CE=$TOTAL_CE, UE=$TOTAL_UE"
  if [ "$TOTAL_UE" -gt 0 ]; then
    echo "  [CRITICAL] Uncorrectable errors"
    ((CRITICALS++))
  elif [ "$TOTAL_CE" -gt 1000 ]; then
    echo "  [WARNING] High correctable errors"
    ((WARNINGS++))
  else
    echo "  [OK]"
  fi
else
  echo "Memory: ECC not available"
fi

# 3. RAID
if [ -f /proc/mdstat ]; then
  if grep -q "_" /proc/mdstat; then
    echo "RAID: DEGRADED [CRITICAL]"
    ((CRITICALS++))
  elif grep -q "recovering\|resyncing" /proc/mdstat; then
    echo "RAID: Rebuilding [WARNING]"
    ((WARNINGS++))
  else
    echo "RAID: Optimal [OK]"
  fi
else
  echo "RAID: Not configured"
fi

# 4. Battery
if command -v upower &>/dev/null && upower -d 2>/dev/null | grep -q "battery"; then
  HEALTH=$(upower -d 2>/dev/null | awk '/capacity:/ {print $2}' | head -1 | tr -d '%')
  [ -n "$HEALTH" ] && echo "Battery: ${HEALTH}% health" && [ "$HEALTH" -lt 50 ] && echo "  [WARNING]" && ((WARNINGS++)) || echo "  [OK]"
fi

# Summary
echo ""
if [ "$CRITICALS" -gt 0 ]; then
  echo "OVERALL: CRITICAL - $CRITICALS critical issue(s) - Deep mode recommended"
elif [ "$WARNINGS" -gt 0 ]; then
  echo "OVERALL: WARNING - $WARNINGS warning(s) - Consider deep mode"
else
  echo "OVERALL: OK - All hardware healthy"
fi
```

**AI Instructions for Quick Mode**:
1. Execute script
2. Parse output for critical/warning counts
3. Decision logic:
   - Any CRITICAL → Deep Mode on that component
   - 2+ WARNINGS → Ask user if Deep mode needed
   - All OK → Stop

---

## 🔬 Deep Mode (20-40s)

---

### Deep Mode: CPU Temperature

**When**: Quick shows CPU > 80°C

**Commands**:
```bash
#!/bin/bash
echo "=== Deep Mode: CPU Temperature Analysis ==="

# 1. Per-core temperatures
echo "[1/4] Per-Core Temperatures"
if command -v sensors &>/dev/null; then
  sensors | grep -i "core\|package" | grep "°C"
else
  echo "lm-sensors not installed"
fi

# 2. Check for thermal throttling
echo -e "\n[2/4] Thermal Throttling Check"
THROTTLE_EVENTS=$(dmesg | grep -c "cpu clock throttled")
if [ "$THROTTLE_EVENTS" -gt 0 ]; then
  echo "🔴 CRITICAL - CPU throttled $THROTTLE_EVENTS times"
  dmesg | grep "cpu clock throttled" | tail -5
else
  echo "✅ No throttling detected"
fi

# 3. CPU frequency (throttled if below max)
echo -e "\n[3/4] CPU Frequency"
if [ -f /proc/cpuinfo ]; then
  CURRENT_MHZ=$(grep "cpu MHz" /proc/cpuinfo | head -1 | awk '{print $4}' | cut -d. -f1)
  echo "Current: ${CURRENT_MHZ} MHz"
  
  # Get max frequency
  if [ -f /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq ]; then
    MAX_KHZ=$(cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq)
    MAX_MHZ=$((MAX_KHZ / 1000))
    echo "Maximum: ${MAX_MHZ} MHz"
    
    PERCENT=$((CURRENT_MHZ * 100 / MAX_MHZ))
    echo "Running at: ${PERCENT}%"
    
    if [ "$PERCENT" -lt 80 ]; then
      echo "⚠️  WARNING - CPU frequency reduced (likely thermal throttling)"
    fi
  fi
fi

# 4. Cooling system check
echo -e "\n[4/4] Fan Status"
if command -v sensors &>/dev/null; then
  FAN_SPEED=$(sensors | grep -i "fan" | head -1)
  if [ -n "$FAN_SPEED" ]; then
    echo "$FAN_SPEED"
  else
    echo "Fan data not available"
  fi
fi

echo ""
echo "========================================="
echo " Diagnosis & Recommendations"
echo "========================================="
```

**Root Cause Inference**:

```yaml
Pattern 1: Active Thermal Throttling
  Evidence:
    - Temperature > 95°C
    - Throttle events > 0
    - CPU frequency < 80% of max
  Root Cause: "CPU overheating, performance degraded by thermal throttling"
  Impact:
    - "Reduced CPU performance (50-80% of normal)"
    - "Application slowdown"
    - "Risk of system shutdown"
  Recommendation:
    - "IMMEDIATE: Check if fans are running"
    - "Clean dust from heatsink and fans"
    - "Verify thermal paste on CPU"
    - "Check case airflow"
    - "If server room: check AC temperature"

Pattern 2: High But Stable Temperature
  Evidence:
    - Temperature 80-95°C
    - No throttling events
    - CPU frequency normal
  Root Cause: "High ambient temperature or poor airflow"
  Impact: "Accelerated hardware aging, future throttling risk"
  Recommendation:
    - "Improve cooling within 1 week"
    - "Monitor for throttling"
    - "Target temperature: < 80°C"

Pattern 3: Fan Failure
  Evidence:
    - Temperature > 90°C
    - Fan speed = 0 RPM or not detected
  Root Cause: "CPU fan failed or disconnected"
  Impact: "Immediate shutdown risk, hardware damage possible"
  Recommendation:
    - "CRITICAL: Replace CPU fan immediately"
    - "Do not run server until fixed"
    - "Check fan power connection"
```

---

### Deep Mode: Memory ECC Errors

**When**: Quick shows UE > 0 or CE > 1000

**Commands**:
```bash
#!/bin/bash
echo "=== Deep Mode: Memory ECC Error Analysis ==="

# 1. EDAC error summary
echo "[1/4] Error Summary by Memory Controller"
if command -v edac-util &>/dev/null; then
  sudo edac-util -s
else
  echo "edac-util not installed (apt-get install edac-utils)"
  
  # Fallback: sysfs
  for mc in /sys/devices/system/edac/mc/mc*/; do
    if [ -d "$mc" ]; then
      MC_NAME=$(basename "$mc")
      CE=$(cat "$mc/ce_count" 2>/dev/null || echo 0)
      UE=$(cat "$mc/ue_count" 2>/dev/null || echo 0)
      echo "$MC_NAME: CE=$CE, UE=$UE"
    fi
  done
fi

# 2. Per-DIMM error counts
echo -e "\n[2/4] Per-DIMM Error Breakdown"
for dimm in /sys/devices/system/edac/mc/mc*/dimm*/; do
  if [ -d "$dimm" ]; then
    DIMM_NAME=$(basename "$dimm")
    LOC=$(cat "$dimm/dimm_location" 2>/dev/null)
    CE=$(cat "$dimm/dimm_ce_count" 2>/dev/null || echo 0)
    UE=$(cat "$dimm/dimm_ue_count" 2>/dev/null || echo 0)
    
    if [ "$CE" -gt 0 ] || [ "$UE" -gt 0 ]; then
      echo "$DIMM_NAME ($LOC): CE=$CE, UE=$UE"
      [ "$UE" -gt 0 ] && echo "  🔴 CRITICAL - Uncorrectable errors on this DIMM"
    fi
  fi
done

# 3. Kernel messages
echo -e "\n[3/4] Recent Kernel ECC Messages"
dmesg | grep -i "EDAC\|memory error" | tail -10

# 4. Memory module info
echo -e "\n[4/4] Installed Memory Modules"
if command -v dmidecode &>/dev/null; then
  sudo dmidecode -t memory | grep -E "Size:|Locator:|Type:|Speed:" | head -20
else
  echo "dmidecode not available"
fi

echo ""
echo "========================================="
echo " Diagnosis & Recommendations"
echo "========================================="
```

**Root Cause Inference**:

```yaml
Pattern 1: Uncorrectable Error (Data Corruption)
  Evidence:
    - UE > 0
    - Specific DIMM identified
  Root Cause: "Memory module failure - data corruption has occurred"
  Impact:
    - "Data integrity compromised"
    - "System crashes likely"
    - "Database corruption risk"
  Recommendation:
    - "🔴 CRITICAL: Replace DIMM at location: <LOC>"
    - "Backup all data immediately"
    - "Run memtest86+ to verify other DIMMs"
    - "Check for application crashes after error timestamp"

Pattern 2: High Correctable Errors (Degrading)
  Evidence:
    - CE > 1000
    - Errors concentrated on one DIMM
    - No UE yet
  Root Cause: "Memory module degrading, may fail soon"
  Impact: "Increased UE risk, potential system instability"
  Recommendation:
    - "⚠️  WARNING: Replace DIMM within 1 month"
    - "Monitor daily: edac-util -s"
    - "Prepare for maintenance window"
    - "If CE rate increasing: replace sooner"

Pattern 3: System-Wide Low CE Count
  Evidence:
    - CE 100-1000
    - Distributed across multiple DIMMs
    - No UE
  Root Cause: "Normal ECC operation, cosmic rays"
  Impact: "No immediate concern, ECC working as designed"
  Recommendation:
    - "✅ Acceptable - ECC is correcting errors"
    - "Monitor monthly"
    - "If trend increases: investigate further"

Pattern 4: No ECC Support
  Evidence:
    - EDAC not available
    - Non-ECC memory detected
  Root Cause: "System does not have ECC memory"
  Impact: "No error detection/correction capability"
  Recommendation:
    - "ℹ️  Non-ECC system"
    - "Memory errors undetectable"
    - "Consider ECC upgrade for critical systems"
```

---

### Deep Mode: RAID Status

**When**: Quick shows RAID degraded/rebuilding

**Commands**:
```bash
#!/bin/bash
echo "=== Deep Mode: RAID Status Analysis ==="

# 1. Software RAID details
if [ -f /proc/mdstat ]; then
  echo "[1/4] RAID Array Status"
  cat /proc/mdstat
  
  echo -e "\n[2/4] Detailed Array Information"
  for array in /dev/md*; do
    if [ -b "$array" ]; then
      echo "=== $array ==="
      sudo mdadm --detail "$array" 2>/dev/null | grep -E "State|Active Devices|Failed Devices|Working Devices"
      echo ""
    fi
  done
  
  # 3. Identify failed disks
  echo "[3/4] Failed Disks"
  for array in /dev/md*; do
    if [ -b "$array" ]; then
      FAILED=$(sudo mdadm --detail "$array" 2>/dev/null | grep "faulty" | awk '{print $NF}')
      if [ -n "$FAILED" ]; then
        echo "$array: Failed disk = $FAILED"
        # Check SMART status of failed disk
        if command -v smartctl &>/dev/null; then
          echo "SMART status:"
          sudo smartctl -H "$FAILED" 2>/dev/null | grep "overall-health"
        fi
      fi
    fi
  done
  
  # 4. Rebuild progress
  echo -e "\n[4/4] Rebuild Progress"
  if grep -q "recovery\|resync" /proc/mdstat; then
    grep -A 1 "recovery\|resync" /proc/mdstat
    
    # Estimate completion time
    FINISH=$(grep "finish" /proc/mdstat | grep -oP 'finish=\K[^ ]+')
    [ -n "$FINISH" ] && echo "Estimated completion: $FINISH"
  else
    echo "No rebuild in progress"
  fi
else
  echo "No software RAID detected"
fi

# Hardware RAID (if applicable)
if command -v megacli &>/dev/null; then
  echo -e "\n=== Hardware RAID (MegaRAID) ==="
  megacli -LDInfo -Lall -aAll 2>/dev/null
  megacli -PDList -aAll 2>/dev/null | grep -E "Firmware state|Slot Number"
fi

echo ""
echo "========================================="
echo " Diagnosis & Recommendations"
echo "========================================="
```

**Root Cause Inference**:

```yaml
Pattern 1: Degraded Array (Disk Failed)
  Evidence:
    - State: degraded
    - Failed Devices: 1
    - Specific disk identified
  Root Cause: "Disk failure, array running without redundancy"
  Impact:
    - "NO REDUNDANCY - Next failure = data loss"
    - "Performance may be degraded"
  Recommendation:
    - "🔴 CRITICAL: Replace failed disk immediately"
    - "Steps:"
    - "  1. Order replacement disk"
    - "  2. Physically replace: <failed_disk>"
    - "  3. Add to array: mdadm --manage /dev/md0 --add /dev/<new_disk>"
    - "  4. Monitor rebuild: watch cat /proc/mdstat"
    - "DO NOT restart server until disk replaced"

Pattern 2: Rebuilding Array
  Evidence:
    - State: recovering/resyncing
    - Progress: X%
    - Finish time: <time>
  Root Cause: "Array rebuilding after disk replacement"
  Impact:
    - "Performance degraded during rebuild"
    - "Vulnerable to second failure"
  Recommendation:
    - "⚠️  Monitor rebuild progress"
    - "Avoid heavy I/O during rebuild if possible"
    - "Estimated completion: <time>"
    - "Do NOT shut down server during rebuild"
    - "Verify health after completion: mdadm --detail /dev/md0"

Pattern 3: Multiple Failed Disks (Data Loss)
  Evidence:
    - Failed Devices: 2+
    - State: failed/inactive
  Root Cause: "Multiple disk failures, RAID array failed"
  Impact: "DATA LOSS - Array is unrecoverable"
  Recommendation:
    - "🔴 CATASTROPHIC - Data loss has occurred"
    - "STOP all operations"
    - "DO NOT attempt repair"
    - "Restore from backup"
    - "Post-mortem: Why did multiple disks fail?"
    - "  - Power surge?"
    - "  - Same disk batch (early failure)?"
    - "  - Controller failure?"

Pattern 4: RAID Healthy
  Evidence:
    - State: clean/active/optimal
    - All devices working
  Root Cause: "RAID array healthy"
  Recommendation: "✅ No action required, continue monitoring"
```

---

### Deep Mode: Battery (Laptop/UPS)

**When**: Quick shows battery health < 50%

**Commands**:
```bash
#!/bin/bash
echo "=== Deep Mode: Battery Health Analysis ==="

if command -v upower &>/dev/null; then
  BATTERY_PATH=$(upower -e | grep battery | head -1)
  
  if [ -n "$BATTERY_PATH" ]; then
    echo "[1/3] Battery Details"
    upower -i "$BATTERY_PATH" | grep -E "state|percentage|capacity|voltage|energy|time|technology"
    
    echo -e "\n[2/3] Charge Cycles"
    CYCLES=$(upower -i "$BATTERY_PATH" | awk '/charge-cycles/ {print $2}')
    [ -n "$CYCLES" ] && echo "Charge cycles: $CYCLES"
    
    echo -e "\n[3/3] Health Assessment"
    HEALTH=$(upower -i "$BATTERY_PATH" | awk '/capacity:/ {print $2}' | tr -d '%')
    ORIGINAL=$(upower -i "$BATTERY_PATH" | awk '/energy-full-design:/ {print $2}')
    CURRENT=$(upower -i "$BATTERY_PATH" | awk '/energy-full:/ {print $2}')
    
    echo "Original capacity: $ORIGINAL"
    echo "Current capacity: $CURRENT"
    echo "Health: ${HEALTH}%"
  else
    echo "No battery detected"
  fi
else
  echo "upower not available"
fi
```

**Root Cause Inference**:

```yaml
Pattern 1: Severely Degraded Battery
  Evidence:
    - Health < 50%
    - Charge cycles > 500
  Root Cause: "Battery worn out from age/usage"
  Impact: "Reduced runtime, unexpected shutdowns"
  Recommendation:
    - "Replace battery"
    - "For laptops: Order OEM replacement"
    - "For UPS: Contact vendor for battery replacement"

Pattern 2: Normal Wear
  Evidence:
    - Health 50-80%
    - Device age 2-4 years
  Root Cause: "Normal battery aging"
  Recommendation:
    - "Monitor quarterly"
    - "Plan replacement when < 50%"
```

---

## 💡 Complete Usage Examples

### Example 1: User Reports "风扇很响"

**Step 1: Quick Mode**
```
CPU: 102°C [CRITICAL]
OVERALL: CRITICAL
```

**Step 2: Deep Mode - CPU**
```
Per-Core: 102°C, 98°C, 101°C, 99°C
Throttle events: 156
CPU frequency: 45% of maximum
Fan: 3200 RPM (normal)
```

**AI Inference**: Pattern 1 (Active Throttling)

**Final Report**:
```
🔴 CPU 严重过热并已降频

当前状态：
- 最高温度：102°C（严重超标）
- 降频事件：156 次
- 当前频率：仅为最大频率的 45%
- 风扇转速：3200 RPM（正常运转）

根因：散热系统失效
- 风扇运转正常，但散热不足
- 可能原因：散热器堵塞、硅脂老化

影响：
- CPU 性能降低 55%
- 应用程序运行缓慢
- 存在系统自动关机风险

立即行动：
1. 🔴 立即关机，清理散热器灰尘
2. 🔴 重新涂抹 CPU 硅脂
3. 检查机箱内空气流通
4. 启动后持续监控：watch -n 5 sensors
5. 目标：温度降至 80°C 以下
```

---

### Example 2: User Asks "RAID 是否正常"

**Step 1: Quick Mode**
```
RAID: Rebuilding 37% [WARNING]
```

**Step 2: Deep Mode - RAID**
```
Array: /dev/md0
State: recovering
Progress: 37% (125GB/337GB)
Finish: 2.5 hours
Failed disk: /dev/sdb (replaced)
```

**AI Inference**: Pattern 2 (Rebuilding)

**Final Report**:
```
⚠️  RAID 正在重建中

当前状态：
- 阵列状态：恢复中
- 完成进度：37%
- 剩余时间：约 2.5 小时
- 已更换磁盘：/dev/sdb

根因：磁盘故障后更换，正在重建冗余

注意事项：
- ⚠️  重建期间无冗余保护
- 如再有磁盘故障，将导致数据丢失
- 性能会有所下降

建议：
1. 让重建过程自然完成（请勿关机）
2. 避免重度 I/O 操作
3. 预计完成时间：今晚 23:30
4. 完成后验证：mdadm --detail /dev/md0
5. 所有磁盘显示 "active sync" 即正常
```

---

### Example 3: Health Check (All OK)

**Step 1: Quick Mode**
```
CPU: 45°C [OK]
Memory: CE=12, UE=0 [OK]
RAID: Optimal [OK]
Battery: No battery (desktop)
OVERALL: OK
```

**Final Report**:
```
硬件健康检查 - 一切正常 ✅

CPU：
- 温度：45°C（正常）
- 无降频事件

内存：
- 可纠正错误：12（正常范围）
- 无不可纠正错误

RAID：
- 状态：最佳
- 所有磁盘正常工作

结论：所有硬件健康，无需采取行动
```

---

## 🎯 Key Takeaways

### Hardware Monitoring Priorities
1. **CPU Temperature** → Immediate performance impact
2. **Memory UE** → Data corruption risk
3. **RAID Degraded** → Data loss risk
4. **Battery Health** → Unexpected shutdowns

### Critical Thresholds
- CPU: > 95°C = throttling
- Memory: UE > 0 = replace DIMM
- RAID: Degraded = no redundancy
- Battery: < 50% = plan replacement

### Predictive Maintenance
- Monitor hardware health quarterly
- Replace before failure when possible
- Hardware failures rarely happen without warning

---

**Integration**: Complements `disk-smart.md` (SMART monitoring) and `system-logs.md` (hardware error logs).

**Tools Required**:
- CPU: `lm-sensors` (Linux), `powermetrics` (macOS)
- Memory: `edac-utils` (Linux)
- RAID: `mdadm` (Linux), `megacli` (hardware RAID)
