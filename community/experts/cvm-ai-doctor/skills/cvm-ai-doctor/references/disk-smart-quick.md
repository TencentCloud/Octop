---
name: disk-smart-quick
description: Fast disk health check via SMART (10 seconds) - PASSED or FAILED
category: standalone-checks
mode: quick
---

# Disk SMART Quick Check

**Purpose**: Overall health status check - PASSED or FAILED (10 seconds).

**Why critical**: Disks fail predictably - SMART predicts 56-70% of failures 7-14 days in advance (Google/Backblaze research).

---

## ⚡ Quick Check Command

```bash
# Linux (requires smartmontools)
DISKS=$(lsblk -nd -o NAME,TYPE 2>/dev/null | awk '$2=="disk" {print "/dev/"$1}')

echo "=== Quick Mode: Disk SMART Health ==="
for disk in $DISKS; do
  if command -v smartctl &>/dev/null; then
    HEALTH=$(sudo smartctl -H "$disk" 2>/dev/null | awk '/SMART overall-health/ {print $NF}')
    if [ "$HEALTH" = "PASSED" ]; then
      echo "$disk: PASSED [OK]"
    elif [ "$HEALTH" = "FAILED" ]; then
      echo "$disk: FAILED [CRITICAL] - BACKUP DATA IMMEDIATELY"
    else
      echo "$disk: UNKNOWN [CHECK] - SMART may not be supported"
    fi
  else
    echo "smartctl not installed - run: apt-get install smartmontools"
    break
  fi
done
```

```bash
# macOS (requires smartmontools: brew install smartmontools)
DISKS=$(diskutil list | grep "^/dev/disk" | awk '{print $1}' | grep -v "disk0s")

echo "=== Quick Mode: Disk SMART Health ==="
for disk in $DISKS; do
  if command -v smartctl &>/dev/null; then
    HEALTH=$(sudo smartctl -H "$disk" 2>/dev/null | awk '/SMART overall-health|SMART Health Status/ {print $NF}')
    if [ "$HEALTH" = "PASSED" ] || [ "$HEALTH" = "OK" ]; then
      echo "$disk: PASSED [OK]"
    elif [ "$HEALTH" = "FAILED" ]; then
      echo "$disk: FAILED [CRITICAL] - BACKUP DATA IMMEDIATELY"
    else
      echo "$disk: UNKNOWN [CHECK] - SMART may not be supported"
    fi
  else
    echo "smartctl not installed - run: brew install smartmontools"
    break
  fi
done
```

```powershell
# Windows (requires smartmontools or use WMIC)
# Method 1: Using smartctl (if installed via Chocolatey: choco install smartmontools)
if (Get-Command smartctl -ErrorAction SilentlyContinue) {
    $disks = Get-PhysicalDisk | Select-Object -ExpandProperty DeviceId
    Write-Host "=== Quick Mode: Disk SMART Health ==="
    foreach ($diskId in $disks) {
        $health = & smartctl -H "/dev/pd$diskId" 2>$null | Select-String "SMART overall-health"
        if ($health -match "PASSED") {
            Write-Host "Disk $diskId : PASSED [OK]"
        } elseif ($health -match "FAILED") {
            Write-Host "Disk $diskId : FAILED [CRITICAL] - BACKUP DATA IMMEDIATELY"
        } else {
            Write-Host "Disk $diskId : UNKNOWN [CHECK]"
        }
    }
} else {
    # Method 2: Using WMIC (built-in, less detailed)
    Write-Host "=== Quick Mode: Disk Health (WMIC) ==="
    Get-WmiObject -Namespace root\wmi -Class MSStorageDriver_FailurePredictStatus -ErrorAction SilentlyContinue | 
        Select-Object @{Name="Disk";Expression={$_.InstanceName}},@{Name="Status";Expression={if($_.PredictFailure){"FAILED [CRITICAL]"}else{"OK"}}} | 
        Format-Table -AutoSize
    
    if (-not (Get-WmiObject -Namespace root\wmi -Class MSStorageDriver_FailurePredictStatus -ErrorAction SilentlyContinue)) {
        Write-Host "Note: Install smartmontools for detailed SMART data: choco install smartmontools"
    }
}
```

---

## 🎯 AI Interpretation

**Thresholds**:
```yaml
OK: All disks = PASSED
CRITICAL: Any disk = FAILED
CHECK: Any disk = UNKNOWN (SMART not supported or error)
```

**Decision Logic**:
```yaml
All PASSED:
  → Stop, report healthy
  → No Deep mode needed

Any FAILED:
  → Deep mode IMMEDIATELY (data loss risk)
  → Read: disk-smart-deep.md for specific disk

Any UNKNOWN:
  → Deep mode to verify (may be RAID, USB, or unsupported)
  → Read: disk-smart-deep.md
```

---

## 📋 Output Template

**Human-friendly format**:
```
⚡ Quick SMART Check (10s)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ /dev/sda: PASSED [OK]
✅ /dev/sdb: PASSED [OK]
🚨 /dev/sdc: FAILED [CRITICAL] - BACKUP DATA NOW

Overall: CRITICAL - Immediate Deep analysis required
```

---

## 🔗 Next Steps

- If **any FAILED** → Read `disk-smart-deep.md` immediately
- If **any UNKNOWN** → Read `disk-smart-deep.md` to investigate
- If **all PASSED** → No further action needed

---

**Last Updated**: 2026-03-25
**Compatibility**: Linux, macOS, Windows (full support)
**Dependencies**: smartmontools (smartctl) - recommended for all platforms; Windows WMIC as fallback
**Token Estimate**: ~300 tokens
