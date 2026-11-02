---
description: Comprehensive system health checkup including disk health, SMART status, filesystem checks, and overall system status. Supports Linux, macOS, and Windows.
tags: [sysadmin, diagnostics, health, disk, smart, filesystem, comprehensive, cross-platform]
---

Perform a comprehensive system health checkup.

## Platform Detection

Before running commands, detect the OS:
```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux → Linux, macOS → Darwin, Windows → MINGW*/MSYS*/CYGWIN*
```

## Checks by Category

### 1. Disk Health (SMART)

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| List drives | `sudo smartctl --scan` | `diskutil list` | `wmic diskdrive get Model,Size,Status` |
| SMART health | `sudo smartctl -H /dev/sdX` | `sudo smartctl -H /dev/disk0` | N/A (use `wmic diskdrive get Status`) |
| SMART attributes | `sudo smartctl -A /dev/sdX` | `sudo smartctl -A /dev/disk0` | N/A |
| NVMe health | `sudo nvme smart-log /dev/nvmeXn1` | N/A | `powershell "Get-PhysicalDisk \| Select HealthStatus,OperationalStatus"` |

- Check for: Reallocated sectors, Current pending sectors, Offline uncorrectable sectors
- **Install smartmontools**:
  - Linux: `sudo apt install smartmontools`
  - macOS: `brew install smartmontools`
  - Windows: Download from https://www.smartmontools.org/wiki/Download

### 2. Filesystem Health

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Disk space | `df -h` | `df -h` | `wmic logicaldisk get caption,size,freespace` |
| Inode usage | `df -i` | `df -i` | N/A |
| Mounted filesystems | `mount \| grep -E '^/dev'` | `mount \| grep -E '^/dev'` | `wmic logicaldisk get caption,filesystem` |
| Filesystem check | `sudo tune2fs -l /dev/sdXY \| grep -i 'state\|error'` (ext4) | `diskutil info /` | `chkdsk /scan` (read-only) |
| BTRFS stats | `sudo btrfs device stats /` (if BTRFS) | N/A | N/A |

### 3. System Resources

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Memory | `free -h` | `vm_stat` + `sysctl hw.memsize` | `wmic OS get TotalVisibleMemorySize,FreePhysicalMemory` |
| Load averages | `uptime` | `uptime` | `wmic cpu get loadpercentage` |
| Process overview | `top -b -n 1 \| head -n 20` | `top -l 1 -n 20 -stats pid,command,cpu,mem` | `powershell "Get-Process \| Sort CPU -Desc \| Select -First 20"` |
| Swap | `swapon --show` | `sysctl vm.swapusage` | `wmic pagefileset get AllocatedBaseSize,CurrentUsage` |

### 4. Critical Services

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Logging service | `systemctl status systemd-journald` | `sudo launchctl list \| grep syslog` | `powershell "Get-Service -Name 'EventLog'"` |
| Task scheduler | `systemctl status cron` or `crond` | `sudo launchctl list \| grep com.apple.periodic` | `powershell "Get-Service -Name 'TaskScheduler'"` |
| Failed services | `systemctl --failed` | `launchctl list \| grep '^\-'` | `powershell "Get-Service \| Where {$_.Status -ne 'Running'}"` |

### 5. Security Updates

| Action | Linux (apt) | macOS | Windows |
|--------|------------|-------|---------|
| Refresh lists | `sudo apt-get update` | `brew update` | `winget update` (checks only) |
| Available updates | `apt list --upgradable` | `brew outdated` | `winget upgrade` or `choco outdated` |
| Recent updates | `grep -i security /var/log/apt/history.log \| tail -20` | N/A (check `softwareupdate -l`) | `powershell "Get-HotFix \| Sort InstalledOn -Desc \| Select -First 20"` |

### 6. System Logs

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Error logs | `journalctl -p 3 -b` | `log show --predicate 'messageType == "error"' --last 1h` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=2,3} -MaxEvents 30"` |
| Critical logs | `journalctl -p 2 -b` | `log show --predicate 'messageType == "critical"' --last 24h` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=1} -MaxEvents 10"` |
| Kernel errors | `dmesg \| grep -i 'error\|fail\|critical' \| tail -20` | `log show --predicate 'subsystem == "com.apple.kernel"' --last 1h` | PowerShell kernel-power events |

### 7. Hardware Status

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Temperature | `sensors` (needs lm-sensors) | `osx-cpu-temp` (needs brew) | PowerShell WMI thermal query |
| Hardware errors | `dmesg \| grep -i 'hardware error'` | `log show --predicate 'subsystem contains "hardware"' --last 24h` | `powershell "Get-WinEvent @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'}"` |
| PCIe errors | `lspci -v \| grep -i 'error'` | N/A | N/A |

### 8. Additional Checks

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Failed logins | `sudo grep -i 'failed password' /var/log/auth.log \| tail -10` | `log show --predicate 'subsystem == "com.apple.security"' --last 24h` | `powershell "Get-WinEvent @{LogName='Security'; ID=4625} -MaxEvents 10"` |
| Disk I/O errors | `dmesg \| grep -i 'I/O error'` | `diskutil list` (check for offline disks) | `powershell "Get-WinEvent @{LogName='System'; ProviderName='disk'}"` |

## Output Report

Analyze all results and provide:

**Summary Report:**
- Detected OS: [Linux/macOS/Windows] [version]
- Overall system health status (Healthy, Warning, Critical)
- Disk health status for each drive
- Filesystem health and space status
- Memory and swap status
- Any failed services or critical errors
- Pending updates (especially security)
- Temperature warnings if applicable
- Specific issues found with severity levels

**Recommendations:**
- Immediate actions needed (if any)
- Preventive maintenance suggestions
- Monitoring recommendations
- Whether a reboot is recommended
- Backup reminders if issues detected
- OS-specific tool install suggestions

**Priority Issues:**
List any issues in order of urgency:
1. Critical (requires immediate attention)
2. Warning (should be addressed soon)
3. Informational (for awareness)
