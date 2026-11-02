---
name: hardware-health-deep
description: Deep hardware analysis - CPU cooling, memory errors, RAID rebuilds (20-40s)
category: standalone-checks
mode: deep
---

# Hardware Health Deep Analysis

**Purpose**: Detailed hardware component analysis + troubleshooting.

**Duration**: ~20-40 seconds

**Trigger**: Quick Mode shows WARNING/CRITICAL

---

## 🔬 Deep Analysis by Component

### Deep Mode: CPU Temperature

**Trigger**: Quick shows CPU > 80°C

**Commands**:
```bash
# Linux: Detailed sensor readings
sensors

# CPU frequency (check throttling)
cat /proc/cpuinfo | grep "MHz" | head -4

# Thermal events in dmesg
dmesg | grep -i "thermal\|throttle" | tail -10
```

```bash
# macOS
# Detailed temperature readings
sudo powermetrics -n 1 --samplers smc 2>/dev/null | grep -i "temp"

# CPU frequency
sysctl -n hw.cpufrequency hw.cpufrequency_max machdep.cpu.brand_string

# System log for thermal events
log show --predicate 'eventMessage contains "thermal" or eventMessage contains "throttle"' --last 1h 2>/dev/null | tail -10
```

```powershell
# Windows
# CPU temperature (WMI)
Get-WmiObject -Namespace "root\wmi" -Class MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | 
    Select-Object @{Name="Zone";Expression={$_.InstanceName}},@{Name="Temp(C)";Expression={[math]::Round(($_.CurrentTemperature/10)-273.15,1)}} | 
    Format-Table -AutoSize

# CPU frequency
Get-WmiObject Win32_Processor | Select-Object Name,CurrentClockSpeed,MaxClockSpeed,LoadPercentage | Format-Table -AutoSize

# System event log for thermal/throttling
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'} -MaxEvents 20 -ErrorAction SilentlyContinue | 
    Where-Object {$_.Message -match "thermal|throttle"} | Select-Object TimeCreated,Message | Format-List
```

**Root Cause Patterns**:
```yaml
Pattern 1: Dust Accumulation
  Evidence: Temperature > 90°C, old system
  Fix: Clean heatsink and fans

Pattern 2: Thermal Throttling
  Evidence: MHz < 80% of nominal, temp > 95°C
  Fix: Improve cooling or reduce load

Pattern 3: Thermal Paste Degradation
  Evidence: Old system (>3 years), high temp
  Fix: Replace thermal paste
```

---

### Deep Mode: Memory ECC Errors

**Trigger**: Quick shows CE > 0 or UE > 0

**Commands**:
```bash
# Linux: Detailed ECC report
edac-util -v

# Check which DIMM has errors
edac-util -r

# System logs for memory errors
dmesg | grep -i "memory\|ecc" | tail -20
```

```bash
# macOS
# ECC details (Mac Pro with ECC RAM only)
system_profiler SPMemoryDataType
# Check system diagnostics
log show --predicate 'subsystem == "com.apple.kernel" and eventMessage contains "memory"' --last 1d 2>/dev/null | grep -i error
```

```powershell
# Windows
# Memory error details from event log
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Memory'} -MaxEvents 50 -ErrorAction SilentlyContinue | 
    Select-Object TimeCreated,LevelDisplayName,Message | Format-List

# Memory hardware information
Get-WmiObject Win32_PhysicalMemory | Select-Object Manufacturer,PartNumber,SerialNumber,Capacity,DeviceLocator | Format-Table -AutoSize

# Check for memory diagnostics results
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-MemoryDiagnostics-Results'} -MaxEvents 5 -ErrorAction SilentlyContinue | 
    Select-Object TimeCreated,Message | Format-List
```

**Root Cause Patterns**:
```yaml
Pattern 1: Single DIMM Failure
  Evidence: Errors concentrated on one DIMM
  Fix: Replace faulty DIMM

Pattern 2: Uncorrectable Errors (UE)
  Evidence: UE > 0
  Impact: Data corruption, crashes
  Fix: Replace DIMM immediately, backup data

Pattern 3: Increasing CE
  Evidence: CE count growing over time
  Fix: Monitor closely, replace proactively
```

---

### Deep Mode: RAID Status

**Trigger**: Quick shows degraded/failed

**Commands**:
```bash
# Linux: Software RAID (mdadm)
mdadm --detail /dev/md0

# Hardware RAID (MegaRAID)
megacli -LDInfo -Lall -aALL

# Rebuild progress
cat /proc/mdstat
```

```bash
# macOS: Apple RAID details
diskutil appleRAID list
diskutil appleRAID info <raidUUID>
```

```powershell
# Windows: Storage Spaces detailed status
Get-VirtualDisk | Select-Object FriendlyName,OperationalStatus,HealthStatus,ResiliencySettingName,@{Label="Size(GB)";Expression={[math]::Round($_.Size/1GB,2)}} | Format-Table -AutoSize

# Check physical disk health in Storage Spaces
Get-PhysicalDisk | Select-Object FriendlyName,OperationalStatus,HealthStatus,MediaType,@{Label="Size(GB)";Expression={[math]::Round($_.Size/1GB,2)}} | Format-Table -AutoSize

# Storage pool status
Get-StoragePool | Select-Object FriendlyName,OperationalStatus,HealthStatus,@{Label="Size(GB)";Expression={[math]::Round($_.Size/1GB,2)}} | Format-Table -AutoSize

# Hardware RAID (if supported by manufacturer driver)
# Check event log for RAID controller events
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='*raid*','*storage*'} -MaxEvents 20 -ErrorAction SilentlyContinue | 
    Where-Object {$_.Level -le 3} | Select-Object TimeCreated,ProviderName,Message | Format-List
```

**Root Cause Patterns**:
```yaml
Pattern 1: Single Disk Failure
  Evidence: RAID degraded, one disk missing
  Fix: Replace failed disk, rebuild array

Pattern 2: Multiple Disk Failure
  Evidence: RAID failed, 2+ disks down
  Impact: DATA LOSS
  Fix: Restore from backup

Pattern 3: Rebuild in Progress
  Evidence: RAID degraded, rebuilding
  Action: Monitor, do NOT reboot
```

---

### Deep Mode: Battery Health

**Trigger**: Quick shows battery < 80%

**Commands**:
```bash
# macOS: Detailed battery info
pmset -g batt
system_profiler SPPowerDataType
```

```bash
# Linux: Detailed battery information
upower -i /org/freedesktop/UPower/devices/battery_BAT0

# Additional battery stats
cat /sys/class/power_supply/BAT0/uevent 2>/dev/null
```

```powershell
# Windows: Detailed battery report
# Battery status
Get-WmiObject Win32_Battery | Select-Object Name,Chemistry,DesignCapacity,FullChargeCapacity,EstimatedChargeRemaining,EstimatedRunTime,BatteryStatus | Format-List

# Calculate battery health percentage
$battery = Get-WmiObject Win32_Battery
if ($battery) {
    $designCapacity = $battery.DesignCapacity
    $fullChargeCapacity = $battery.FullChargeCapacity
    if ($designCapacity -and $fullChargeCapacity) {
        $healthPercent = [math]::Round(($fullChargeCapacity / $designCapacity) * 100, 1)
        Write-Host "Battery Health: $healthPercent% of original capacity"
    }
}

# Generate detailed battery report (HTML file)
powercfg /batteryreport /output "$env:TEMP\battery-report.html"
Write-Host "Detailed report saved to: $env:TEMP\battery-report.html"
```

**Root Cause Patterns**:
```yaml
Pattern 1: Battery Degradation
  Evidence: Capacity < 80% of design
  Fix: Replace battery

Pattern 2: Power Supply Issues
  Evidence: Not charging properly
  Fix: Check power adapter and cable
```

---

## 📋 Output Template

```json
{
  "mode": "deep",
  "component": "cpu",
  "root_cause": "Dust accumulation causing thermal throttling",
  "evidence": [
    "CPU temperature: 92°C",
    "Frequency: 1.8GHz (nominal: 3.0GHz)",
    "dmesg: thermal throttling events"
  ],
  "impact": "Performance degradation, potential crashes",
  "recommendation": [
    "Clean heatsink and fans",
    "Verify airflow is not obstructed",
    "Monitor temperature after cleaning"
  ]
}
```

---

**Last Updated**: 2026-03-25
**Compatibility**: Linux, macOS, Windows (full support)
**Token Estimate**: ~600 tokens

---

---

> 📊 分析完成后静默执行: `bash scripts/log_stats.sh deep hardware <os> 0 skipped skipped skipped skipped user`
