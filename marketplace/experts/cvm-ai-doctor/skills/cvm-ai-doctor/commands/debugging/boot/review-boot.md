# Review Boot Process

Review system boot process and identify issues.

## Platform Detection

Before running commands, detect the OS:
```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux → Linux, macOS → Darwin, Windows → MINGW*/MSYS*/CYGWIN*
```

## Your tasks:

### 1. Scan boot messages and logs:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Current boot logs | `journalctl -b` | `log show --last 10m --predicate 'process == "kernel"'` | `powershell "Get-WinEvent @{LogName='System'; StartTime=[System.Management.ManagementDateTimeConverter]::ToDmtfDateTime((Get-CimInstance Win32_OperatingSystem).LastBootUpTime)}"` |
| Previous boot | `journalctl -b -1` | N/A (macOS doesn't separate boot logs) | `powershell "Get-WinEvent @{LogName='System'; StartTime=(Get-Date).AddDays(-1)} \| Select -First 100"` |
| Boot errors | `journalctl -b -p err` | `log show --predicate 'messageType == "error" AND boot=true' --last 24h` | `powershell "Get-WinEvent @{LogName='System'; Level=1,2; StartTime=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime}"` |

### 2. Analyze boot performance:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Overall boot time | `systemd-analyze` | Check Console.app → User Reports → boot time in log | `powershell "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"` |
| Time per service | `systemd-analyze blame` | N/A | `powershell "Get-CimInstance Win32_Service \| Where {$_.StartMode -eq 'Auto'} \| Select Name,State"` |
| Critical path | `systemd-analyze critical-chain` | N/A | Windows Boot Performance diagnostics |

### 3. Identify issues:
   - Failed services
   - Error messages
   - Warnings
   - Slow-starting services
   - Dependency problems

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Failed services | `systemctl --failed` | `launchctl list \| grep '^\-'` | `powershell "Get-Service \| Where {$_.Status -ne 'Running' -and $_.StartType -eq 'Automatic'}"` |
| Auto-start services | `systemctl list-unit-files --type=service --state=enabled` | `launchctl list` | `powershell "Get-CimInstance Win32_Service \| Where StartMode='Auto'"` |
| Boot dependencies | `systemd-analyze --no-pager critical-chain` | N/A | `msconfig` (GUI) or `autoruns.exe` (Sysinternals) |

### 4. Common boot-time issues by platform:

**Linux:**
- Failed systemd services: `systemctl --failed`
- Dependency loops: `systemctl --state=not-found`
- Long-fsck: Check `systemd-analyze blame` for mount units
- Network wait: `systemd-analyze blame | grep network`

**macOS:**
- Slow boot: Check `log show --predicate 'process == "kernel"' --last 10m`
- Login items: `osascript -e 'tell application "System Events" to get the name of every login item'`
- Launch agents: `ls ~/Library/LaunchAgents/ /Library/LaunchAgents/`
- Launch daemons: `ls /Library/LaunchDaemons/`

**Windows:**
- Slow boot: Event Viewer → Windows Logs → System → Filter by Event ID 100 (boot) and 101 (slow boot)
- Startup programs: `powershell "Get-CimInstance Win32_StartupCommand"`
- Auto services: `powershell "Get-Service \| Where {$_.StartType -eq 'Automatic' -and $_.Status -ne 'Running'}"`

### 5. Suggest remediation:
   - Fix failed services
   - Disable unnecessary services
   - Resolve dependency issues
   - Optimize slow services

### 6. Provide actionable recommendations:
   - Commands to investigate specific issues
   - Configuration changes needed
   - Services to disable or reconfigure
   - Further diagnostic steps

Proactively identify and suggest fixes for boot-time issues.
