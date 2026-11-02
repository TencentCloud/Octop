---
name: disk-smart-deep
description: Detailed SMART attribute analysis with failure prediction (20-30 seconds)
category: standalone-checks
mode: deep
---

# Disk SMART Deep Analysis

**Purpose**: Detailed SMART attributes + predictive failure analysis.

**Duration**: ~20-30 seconds

**Trigger**: Quick Mode shows FAILED or UNKNOWN

---

## 🔬 Deep Analysis Commands

### Step 1: Full SMART Attributes

**Command**:
```bash
# Linux
sudo smartctl -a /dev/<disk>
```

```bash
# macOS
sudo smartctl -a /dev/<disk>
# For NVMe drives on macOS
sudo smartctl -a disk0
```

```powershell
# Windows
# Using smartctl (recommended)
smartctl -a /dev/pd<diskNumber>

# Or using WMIC for basic info
Get-WmiObject -Namespace root\wmi -Class MSStorageDriver_FailurePredictData -ErrorAction SilentlyContinue | 
    Select-Object InstanceName,@{Name="VendorSpecific";Expression={$_.VendorSpecific}} | Format-List

# Detailed disk info
Get-PhysicalDisk | Select-Object FriendlyName,SerialNumber,MediaType,HealthStatus,OperationalStatus,@{Label="Size(GB)";Expression={[math]::Round($_.Size/1GB,2)}} | Format-List
```

**AI Analysis**: Extract key attributes (see patterns below)

---

### Step 2: Critical Attributes (Most Important)

**Command**:
```bash
# Linux / macOS
sudo smartctl -A /dev/<disk> | grep -E "ID#|Reallocated_Sector_Ct|Current_Pending_Sector|Offline_Uncorrectable|Temperature_Celsius|Power_On_Hours"
```

```powershell
# Windows
# Using smartctl
smartctl -A /dev/pd<diskNumber> | Select-String "ID#|Reallocated_Sector_Ct|Current_Pending_Sector|Offline_Uncorrectable|Temperature_Celsius|Power_On_Hours"

# Alternative: Check Windows disk health indicators
Get-StorageReliabilityCounter -PhysicalDisk (Get-PhysicalDisk | Select-Object -First 1) -ErrorAction SilentlyContinue | 
    Select-Object Temperature,Wear,ReadErrorsTotal,WriteErrorsTotal,PowerOnHours | Format-List

# Temperature monitoring
Get-WmiObject -Namespace root\wmi -Class MSStorageDriver_ATAPISmartData -ErrorAction SilentlyContinue | 
    Select-Object InstanceName | Format-List
```

**AI Focus**:
- ID 5: Reallocated_Sector_Ct
- ID 197: Current_Pending_Sector
- ID 198: Offline_Uncorrectable
- ID 194: Temperature_Celsius
- ID 9: Power_On_Hours

---

## 🎯 Root Cause Inference

### Critical Attributes Guide

```yaml
ID 5 - Reallocated_Sector_Ct:
  CRITICAL: > 0 (bad sectors detected)
  WARNING: Raw value increasing
  Meaning: Disk has remapped bad sectors
  Action: Backup immediately, plan replacement

ID 197 - Current_Pending_Sector:
  CRITICAL: > 10 (imminent failure)
  WARNING: > 0 (disk trying to reallocate)
  Meaning: Sectors waiting to be remapped
  Action: Backup now, replace disk soon

ID 198 - Offline_Uncorrectable:
  CRITICAL: > 0 (data corruption risk)
  Meaning: Sectors that cannot be read/written
  Action: Backup IMMEDIATELY, replace disk

ID 194 - Temperature_Celsius:
  CRITICAL: > 60°C (overheating)
  WARNING: > 50°C
  Meaning: Disk running too hot
  Action: Improve cooling, check airflow

ID 9 - Power_On_Hours:
  INFO: Disk age indicator
  > 40,000 hours (~ 5 years): Consider replacement
  > 70,000 hours (~ 8 years): High failure risk
```

---

### Failure Probability Assessment

**AI should calculate**:

```yaml
Imminent Failure (Replace NOW):
  - ID 198 > 0 (uncorrectable errors)
  - ID 197 > 10 (pending sectors)
  - SMART health = FAILED

High Risk (Replace within 7 days):
  - ID 5 > 10 (many reallocated sectors)
  - ID 197 > 0 AND increasing
  - Temperature > 60°C sustained

Medium Risk (Replace within 30 days):
  - ID 5 > 0 (some reallocated sectors)
  - Power-on hours > 70,000
  - Temperature > 50°C

Low Risk (Monitor):
  - All attributes OK
  - Power-on hours < 40,000
  - Temperature < 50°C
```

---

## 📋 Output Template

```json
{
  "mode": "deep",
  "disk": "/dev/sda",
  "health_status": "FAILED",
  "critical_attributes": {
    "reallocated_sectors": {"value": 25, "status": "CRITICAL"},
    "pending_sectors": {"value": 5, "status": "WARNING"},
    "uncorrectable_errors": {"value": 0, "status": "OK"},
    "temperature": {"value": "45°C", "status": "OK"},
    "power_on_hours": 52000
  },
  "failure_probability": "high",
  "recommendation": "Replace disk within 7 days. Backup immediately.",
  "timeline": "7 days"
}
```

**Human-friendly format**:

```
🔬 Deep SMART Analysis: /dev/sda (25s)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚨 Health Status: FAILED

📊 Critical Attributes:
   • Reallocated Sectors: 25 [CRITICAL]
   • Pending Sectors: 5 [WARNING]
   • Uncorrectable Errors: 0 [OK]
   • Temperature: 45°C [OK]
   • Power-On Hours: 52,000 (6 years)

⚠️  Failure Probability: HIGH

🛠️  Recommendation:
   1. BACKUP DATA IMMEDIATELY
   2. Replace disk within 7 days
   3. Monitor daily until replacement
```

---

## 🔗 Related Checks

- If temperature high → Run `hardware-other.md` for cooling analysis
- If multiple disks failing → Check power supply
- If filesystem errors → Run `system-logs-deep-fs.md`

---

**Last Updated**: 2026-03-25
**Compatibility**: Linux, macOS, Windows (full support)
**Dependencies**: smartmontools (smartctl) - recommended for all platforms; Windows Get-StorageReliabilityCounter as supplement
**Token Estimate**: ~700 tokens

---

---

> 📊 分析完成后静默执行: `bash scripts/log_stats.sh deep disk_smart <os> 0 skipped skipped skipped skipped user`
