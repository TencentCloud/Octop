# SMART Status Check

You are helping the user check SMART health status for all storage drives.

> **Note**: For full SMART attribute analysis and failure prediction, use `disk-smart-deep.md`.
> This file provides a quick status check (PASSED/FAILED) for immediate triage.

## Platform Detection

```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux → Linux, macOS → Darwin, Windows → MINGW*/MSYS*/CYGWIN*
```

## Quick SMART Status

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| List all disks | `lsblk -nd -o NAME,TYPE \| awk '$2=="disk" {print "/dev/"$1}'` | `diskutil list \| grep "^/dev/disk"` | `Get-PhysicalDisk \| Select-Object DeviceId,FriendlyName` |
| Check SMART health | `sudo smartctl -H /dev/<disk>` | `sudo smartctl -H /dev/<disk>` | `smartctl -H /dev/pd<id>` |
| All disks at once (Linux) | `for d in $(lsblk -nd -o NAME \| grep -E "^[sv]d\|^nvme"); do echo "$d: $(sudo smartctl -H /dev/$d 2>/dev/null \| grep -E 'PASSED\|FAILED\|result')"; done` | — | — |

## Interpret Results

| Result | Meaning | Action |
|--------|---------|--------|
| `PASSED` | Disk is healthy | No action needed |
| `FAILED` | Disk is failing | **Backup immediately**, read `disk-smart-deep.md` |
| `UNKNOWN` / no output | SMART not supported or tool missing | Install `smartmontools`, read `disk-smart-deep.md` |

## Install smartmontools (if missing)

| Linux (apt) | Linux (yum) | macOS | Windows |
|-------------|-------------|-------|---------|
| `sudo apt-get install smartmontools` | `sudo yum install smartmontools` | `brew install smartmontools` | `choco install smartmontools` |

## Next Steps

- Any disk `FAILED` → Read `references/disk-smart-deep.md` for detailed attribute analysis
- All disks `PASSED` → Disk hardware is healthy; I/O issues are software/workload related

**Last Updated**: 2026-04-02
**Compatibility**: Linux (full), macOS (full), Windows (partial — requires smartmontools)
