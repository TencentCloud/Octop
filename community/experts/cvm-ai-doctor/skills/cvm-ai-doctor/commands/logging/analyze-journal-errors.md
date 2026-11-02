# Analyze System Log Errors

You are helping the user parse system logs to identify recent errors and issues.

## Platform Detection

Before running commands, detect the OS:
```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux → Linux, macOS → Darwin, Windows → MINGW*/MSYS*/CYGWIN*
```

## Task

### 1. Check recent errors from current boot/session:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Errors (current boot) | `journalctl -b -p err` | `log show --predicate 'messageType == "error"' --last 1h` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=2} -MaxEvents 30"` |
| Errors + warnings | `journalctl -b -p warning` | `log show --predicate 'messageType == "error" OR messageType == "warning"' --last 1h` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2,3} -MaxEvents 50"` |
| Critical messages | `journalctl -b -p crit` | `log show --predicate 'messageType == "critical"' --last 24h` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=1} -MaxEvents 10"` |

### 2. Show errors from specific time periods:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Last hour | `journalctl --since "1 hour ago" -p err` | `log show --predicate 'messageType == "error"' --last 1h` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=2; StartTime=(Get-Date).AddHours(-1)}"` |
| Last 24 hours | `journalctl --since "24 hours ago" -p err` | `log show --predicate 'messageType == "error"' --last 24h` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=2; StartTime=(Get-Date).AddDays(-1)}"` |
| Date range | `journalctl --since "2025-10-25" --until "2025-10-26" -p err` | `log show --start "2025-10-25" --end "2025-10-26"` | PowerShell StartTime/EndTime parameters |
| Last N entries | `journalctl -p err -n 100` | `log show --predicate 'messageType == "error"' --last 24h \| tail -100` | `-MaxEvents 100` |

### 3. Group errors by service/source:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Failed services | `systemctl --failed` | `launchctl list \| grep '^\-'` | `powershell "Get-Service \| Where {$_.Status -eq 'Stopped' -and $_.StartType -ne 'Manual'}"` |
| Specific service | `journalctl -u SERVICE_NAME -p err` | `log show --predicate 'sender == "com.example.service"' --last 1h` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='ServiceName'; Level=2}"` |
| Network errors | `journalctl -u NetworkManager -p err` | `log show --predicate 'subsystem == "com.apple.network"' --last 1h` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='*Network*'}"` |
| DNS errors | `journalctl -u systemd-resolved -p err` | `log show --predicate 'subsystem == "com.apple.resolv"' --last 1h` | PowerShell DNS Client events |

### 4. Analyze error frequency:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Count by message | `journalctl -b -p err --no-pager \| grep -oP '(?<=: ).*' \| sort \| uniq -c \| sort -rn \| head -20` | `log show --predicate 'messageType == "error"' --last 24h \| awk '{print $NF}' \| sort \| uniq -c \| sort -rn \| head -20` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=2} -MaxEvents 200 \| Group-Object Message -NoElement \| Sort-Object Count -Desc \| Select -First 20"` |
| Errors per source | `journalctl -b -p err --no-pager \| grep -oP '\w+\.service' \| sort \| uniq -c \| sort -rn` | `log show --predicate 'messageType == "error"' --last 24h \| awk '{print $3}' \| sort \| uniq -c \| sort -rn` | `powershell "Get-WinEvent ... \| Group-Object ProviderName -NoElement \| Sort-Object Count -Desc"` |

### 5. Check for kernel errors:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Kernel errors | `journalctl -k -p err` | `log show --predicate 'subsystem == "com.apple.kernel"' --last 1h` | `powershell "Get-WinEvent @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'}"` |
| Segfaults | `journalctl \| grep -i "segfault"` | `log show --predicate 'eventMessage contains "Segmentation fault"' --last 24h` | `powershell "Get-WinEvent @{LogName='Application'; ProviderName='Application Error'}"` |
| OOM kills | `journalctl \| grep -i "killed process"` | `log show --predicate 'eventMessage contains "out of memory"' --last 24h` | PowerShell Event ID 2020 |

### 6. Find patterns and recurring issues:

| Pattern | Linux | macOS | Windows |
|---------|-------|-------|---------|
| I/O errors | `journalctl -b \| grep -i "i/o error"` | `log show --predicate 'subsystem == "com.apple.iokit.IOStorageFamily"' --last 7d` | `powershell "Get-WinEvent @{ProviderName='disk'}"` |
| Disk errors | `journalctl -b \| grep -i "ata.*error"` | `log show --predicate 'eventMessage contains "disk"' --last 7d` | `powershell "Get-WinEvent @{ProviderName='*disk*'}"` |
| Network errors | `journalctl -b \| grep -i "network.*error\|dhcp.*fail"` | `log show --predicate 'subsystem == "com.apple.network"' --last 7d` | PowerShell NetworkProfile/NetworkStore events |
| GPU errors | `journalctl -b \| grep -i "amdgpu\|drm.*error"` | `log show --predicate 'subsystem == "com.apple.iokit.IOGraphicsFamily"' --last 7d` | `powershell "Get-WinEvent @{ProviderName='*dxgkrnl*','*nvlddmkm*'}"` |

### 7. Export error summary:

```bash
# Linux
journalctl -b -p err --no-pager > /tmp/system-errors-$(date +%Y%m%d).log

# macOS
log show --predicate 'messageType == "error"' --last 24h > /tmp/system-errors-$(date +%Y%m%d).log

# Windows
powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=2} -MaxEvents 200 | Out-File $env:TEMP\system-errors.txt"
```

## Present Summary to User

Provide:
- Detected OS and log system used
- Number of errors found in timeframe
- Most frequent error messages
- Services/units with errors
- Critical vs warning vs error breakdown
- Any patterns (disk, network, GPU issues)
- Recommended actions for common errors

## Common Error Patterns & Solutions

**NetworkManager / network errors:**
- DHCP timeout: Check network cable/WiFi
- DNS resolution: Check DNS configuration

**Disk errors:**
- I/O errors: Run SMART checks
- Filesystem errors: Linux `fsck`, macOS `diskutil verifyVolume`, Windows `chkdsk`

**GPU errors:**
- AMDGPU (Linux): Check ROCm installation and kernel modules
- NVIDIA (Linux): Check driver version
- macOS: Check for system updates
- Windows: Update GPU drivers

## Additional Analysis

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Compare boots | `journalctl --list-boots` | N/A | N/A |
| Error timeline | `journalctl -b -p err --output=short-monotonic` | `log show --style compact` | `powershell "Get-WinEvent ... \| Sort TimeCreated"` |
| JSON export | `journalctl -b -p err -o json` | `log show --predicate 'messageType == "error"' --style json` | `powershell "Get-WinEvent ... \| ConvertTo-Json"` |

## Notes

- Linux: Priority levels 0=emerg, 1=alert, 2=crit, 3=err, 4=warning, 5=notice, 6=info, 7=debug
- macOS: Uses Unified Logging (`log show`) with predicates for filtering
- Windows: Event Log levels 1=Critical, 2=Error, 3=Warning, 4=Information
- Always detect OS first — the logging system differs fundamentally
