---
name: hardware-health-quick
description: Fast check of CPU temp, memory ECC, RAID, battery (10 seconds)
category: standalone-checks
mode: quick
---

# Hardware Health Quick Check

**Purpose**: Status check for 4 hardware components (10 seconds).

**Components**: CPU temperature, Memory ECC errors, RAID status, Battery/Power

---

## ⚡ Quick Check Commands

### 1. CPU Temperature

```bash
# Linux
if command -v sensors &>/dev/null; then
  MAX_TEMP=$(sensors 2>/dev/null | grep -E "Core |Package" | awk '{print $3}' | sed 's/[^0-9.]//g' | sort -rn | head -1)
  echo "CPU Max: ${MAX_TEMP}°C"
else
  echo "lm-sensors not installed"
fi
```

```bash
# macOS
MAX_TEMP=$(sudo powermetrics -n 1 --samplers smc 2>/dev/null | grep "CPU die temperature" | awk '{print $4}')
echo "CPU Temp: ${MAX_TEMP}°C"
```

```powershell
# Windows (requires admin, WMI thermal zone)
$temp = Get-WmiObject -Namespace "root\wmi" -Class MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | 
    Select-Object -First 1 -ExpandProperty CurrentTemperature
if ($temp) {
    $tempC = [math]::Round(($temp / 10) - 273.15, 1)
    Write-Host "CPU Temp: ${tempC}°C"
} else {
    Write-Host "CPU Temp: [UNKNOWN] WMI thermal data not available (may need third-party tool)"
}
```

**Thresholds**:
```yaml
OK: < 80°C
WARNING: 80-95°C
CRITICAL: > 95°C (thermal throttling)
```

---

### 2. Memory ECC Errors

```bash
# Linux
if command -v edac-util &>/dev/null; then
  edac-util -s
else
  echo "edac-util not installed (apt-get install edac-utils)"
fi
```

```bash
# macOS
# ECC not typically available on consumer Macs
echo "ECC Memory: [N/A] Consumer Macs don't have ECC RAM"
# For Mac Pro with ECC, check system logs
system_profiler SPMemoryDataType | grep -i ecc
```

```powershell
# Windows
# Check memory errors from system event log
$memErrors = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Memory'; Level=2} -MaxEvents 10 -ErrorAction SilentlyContinue
if ($memErrors) {
    Write-Host "Memory Errors: [WARNING] $($memErrors.Count) memory errors found in event log"
    $memErrors | Select-Object -First 3 TimeCreated,Message | Format-List
} else {
    Write-Host "Memory Errors: [OK] No recent memory errors"
}
```

**Thresholds**:
```yaml
OK: CE = 0, UE = 0
WARNING: CE > 0 (correctable errors)
CRITICAL: UE > 0 (uncorrectable errors, data corruption risk)
```

---

### 3. RAID Status

```bash
# Linux: Hardware RAID (MegaRAID)
if command -v megacli &>/dev/null; then
  megacli -LDInfo -Lall -aALL | grep "State"
fi

# Software RAID (mdadm)
if [ -f /proc/mdstat ]; then
  cat /proc/mdstat
fi
```

```bash
# macOS: Check Apple RAID (Software RAID)
diskutil appleRAID list 2>/dev/null || echo "RAID: [N/A] No Apple RAID configured"
```

```powershell
# Windows: Storage Spaces and Hardware RAID
# Check Storage Spaces (Software RAID)
$storageSpaces = Get-VirtualDisk -ErrorAction SilentlyContinue
if ($storageSpaces) {
    $storageSpaces | Select-Object FriendlyName,OperationalStatus,HealthStatus | Format-Table -AutoSize
} else {
    Write-Host "Storage Spaces: [N/A] No virtual disks configured"
}

# Check hardware RAID via WMI (if available)
Get-WmiObject -Namespace root\wmi -Class MSStorageDriver_FailurePredictStatus -ErrorAction SilentlyContinue | 
    Select-Object InstanceName,PredictFailure | Format-Table -AutoSize
```

**Thresholds**:
```yaml
OK: Optimal / clean
WARNING: Degraded / rebuilding
CRITICAL: Failed
```

---

### 4. Battery Health (Laptops/UPS)

```bash
# macOS
pmset -g batt

# Linux (laptops)
cat /sys/class/power_supply/BAT0/capacity 2>/dev/null
```

```powershell
# Windows
# Battery status (laptops)
$battery = Get-WmiObject Win32_Battery -ErrorAction SilentlyContinue
if ($battery) {
    $capacity = $battery.EstimatedChargeRemaining
    $status = $battery.BatteryStatus
    Write-Host "Battery: ${capacity}% - Status: $status"
    if ($capacity -lt 50) {
        Write-Host "[CRITICAL] Battery below 50%"
    } elseif ($capacity -lt 80) {
        Write-Host "[WARNING] Battery below 80%"
    } else {
        Write-Host "[OK]"
    }
} else {
    Write-Host "Battery: [N/A] Desktop or AC power"
}

# Detailed battery health report (optional)
# powercfg /batteryreport /output "C:\battery-report.html"
```

**Thresholds**:
```yaml
OK: > 80%
WARNING: 50-80%
CRITICAL: < 50%
```

---

## 📋 Quick Mode Complete Script

```bash
#!/bin/bash
echo "=== Quick Mode: Hardware Health ==="

# 1. CPU Temperature
if command -v sensors &>/dev/null; then
  MAX_TEMP=$(sensors 2>/dev/null | grep -E "Core |Package" | awk '{print $3}' | sed 's/[^0-9.]//g' | sort -rn | head -1)
  [ $(echo "$MAX_TEMP > 95" | bc) -eq 1 ] && CPU_STATUS="CRITICAL" || [ $(echo "$MAX_TEMP > 80" | bc) -eq 1 ] && CPU_STATUS="WARNING" || CPU_STATUS="OK"
  echo "CPU: ${MAX_TEMP}°C [$CPU_STATUS]"
else
  echo "CPU: [UNKNOWN] lm-sensors not installed"
fi

# 2. Memory ECC
if command -v edac-util &>/dev/null; then
  ECC_OUTPUT=$(edac-util -s 2>/dev/null)
  echo "Memory ECC: $ECC_OUTPUT"
else
  echo "Memory ECC: [UNKNOWN] edac-utils not installed"
fi

# 3. RAID
if [ -f /proc/mdstat ]; then
  RAID_STATE=$(grep -E "active|degraded|failed" /proc/mdstat | head -1)
  echo "RAID: $RAID_STATE"
else
  echo "RAID: [N/A] No software RAID detected"
fi

# 4. Battery (if applicable)
if [ -f /sys/class/power_supply/BAT0/capacity ]; then
  BAT_CAP=$(cat /sys/class/power_supply/BAT0/capacity)
  echo "Battery: ${BAT_CAP}%"
else
  echo "Battery: [N/A] Desktop or AC power"
fi
```

---

## 🔗 Next Steps

- If **CPU CRITICAL** → Read `hardware-health-deep.md` (§ Deep Mode: CPU Temperature)
- If **Memory UE > 0** → Read `hardware-health-deep.md` (§ Deep Mode: Memory ECC Errors)
- If **RAID degraded** → Read `hardware-health-deep.md` (§ Deep Mode: RAID Status)
- If **all OK** → No further action needed

---

**Last Updated**: 2026-03-25
**Compatibility**: Linux, macOS, Windows (full support)
**Dependencies**: lm-sensors, edac-utils (optional for Linux), powermetrics (macOS), WMI (Windows)
**Token Estimate**: ~400 tokens
