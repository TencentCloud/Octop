# Diagnose Program Crash

You are helping the user diagnose a recent program crash. Ask for additional context from the user, but start by checking obvious places in the logs.

## Platform Detection

Before running commands, detect the OS:
```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux → Linux, macOS → Darwin, Windows → MINGW*/MSYS*/CYGWIN*
```

## Your tasks:

### 1. Gather information from the user:
   Ask the user:
   - What program crashed?
   - When did it crash (approximate time)?
   - What were they doing when it crashed?
   - Does it crash consistently or intermittently?
   - Any error messages displayed?

### 2. Check system journal for crash information:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Recent errors | `sudo journalctl -p err -b` | `log show --predicate 'messageType == "error"' --last 1h` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=2} -MaxEvents 20"` |
| Last N entries | `sudo journalctl -n 100 --no-pager` | `log show --last 10m --style compact \| tail -100` | `powershell "Get-WinEvent -LogName System -MaxEvents 100"` |
| Since time | `sudo journalctl --since "10 minutes ago" -p warning` | `log show --start "$(date -v-10M '+%Y-%m-%d %H:%M:%S')"` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddMinutes(-10)}"` |
| Search program | `sudo journalctl -b \| grep -i "<program>"` | `log show --last 1h \| grep -i "<program>"` | `powershell "Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='<program>'}"` |

### 3. Check kernel logs:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Recent kernel msgs | `dmesg \| tail -100` | `log show --predicate 'subsystem == "com.apple.kernel"' --last 10m` | `powershell "Get-WinEvent @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'}"` |
| Search program | `dmesg \| grep -i "<program>"` | `log show --predicate 'subsystem == "com.apple.kernel"' --last 10m \| grep -i "<program>"` | PowerShell event log search |
| OOM kills | `dmesg \| grep -i "killed process"` | `log show --predicate 'messageType == "error"' --last 1h \| grep -i oom` | PowerShell Event ID 2020 (Resource-Exhaustion-Detected) |

### 4. Check for core dumps:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Core dump enabled | `ulimit -c` | `ulimit -c` | N/A (always enabled via WER) |
| Core dump location | `cat /proc/sys/kernel/core_pattern` | `/cores/` (default) | `%LOCALAPPDATA%\CrashDumps\` or WER reports |
| Find core dumps | `find /var/lib/systemd/coredump -name "*<program>*" -mtime -1` | `ls -lt ~/Library/Logs/DiagnosticReports/` | `dir %LOCALAPPDATA%\CrashDumps\` |
| List coredumps | `coredumpctl list` | `ls -lt /cores/` | `powershell "Get-WinEvent @{LogName='Application'; ProviderName='Application Error'}"` |
| Coredump info | `coredumpctl info <pid>` | `crashreporter` shows on next launch | Windows Error Reporting dialog |

### 5. Check application-specific logs:

| Type | Linux | macOS | Windows |
|------|-------|-------|---------|
| User app logs | `~/.local/share/<program>/` | `~/Library/Logs/<Program>/` | `%APPDATA%\<Program>\` or `%LOCALAPPDATA%\<Program>\` |
| App cache | `~/.cache/<program>/` | `~/Library/Caches/<Program>/` | `%LOCALAPPDATA%\<Program>\Cache\` |
| App config | `~/.config/<program>/` | `~/Library/Preferences/com.vendor.<program>.plist` | `%APPDATA%\<Program>\` |
| Xsession errors | `~/.xsession-errors` | N/A | N/A |
| Browser logs | `~/.mozilla/`, `~/.config/google-chrome/` | `~/Library/Application Support/Chrome/`, `~/Library/Safari/` | `%LOCALAPPDATA%\Google\Chrome\`, `%APPDATA%\Mozilla\` |

### 6. Check crash reporter systems:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Crash reports | `/var/crash/` (Ubuntu Apport) | `~/Library/Logs/DiagnosticReports/` | Windows Error Reporting (WER) |
| List crashes | `ls -lt /var/crash/` | `ls -lt ~/Library/Logs/DiagnosticReports/` | `powershell "Get-WinEvent @{LogName='Application'; ProviderName='Application Error'} -MaxEvents 10"` |
| File bug | `ubuntu-bug <program>` | Apple Feedback / Developer portal | Microsoft Feedback Hub |
| GNOME/KDE | `~/.local/share/gnome-shell/` / `~/.local/share/drkonqi/` | N/A | N/A |

### 7. Check resource issues at crash time:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Memory | `free -h` | `vm_stat` | `wmic OS get TotalVisibleMemorySize,FreePhysicalMemory` |
| Disk space | `df -h` | `df -h` | `wmic logicaldisk get caption,size,freespace` |
| Swap activity | Check `vmstat 1 5` (si/so columns) | Check `vm_stat` (pageins/pageouts) | Check pagefile usage |

### 8. Check for dependency issues:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Missing libs | `ldd $(which <program>)` | `otool -L $(which <program>)` | Dependency Walker or `dumpbin /dependents` |
| Binary exists | `which <program>` | `which <program>` | `where <program>` or `Get-Command <program>` |
| Version | `<program> --version` | `<program> --version` | `<program> --version` |

### 9. Check for recent system changes:

| Action | Linux (apt) | macOS | Windows |
|--------|------------|-------|---------|
| Package updates | `grep "install\|upgrade" /var/log/dpkg.log \| tail -50` | `brew info <program>` (check for recent updates) | `powershell "Get-HotFix \| Sort InstalledOn -Desc \| Select -First 20"` |
| System updates | `grep "upgrade" /var/log/apt/history.log \| tail -20` | `softwareupdate --history` | `powershell "Get-HotFix \| Sort InstalledOn -Desc"` |
| Kernel changes | `ls -lt /boot/vmlinuz-*` | System Preferences → Software Update | Windows Update history |

### 10. Graphics/display-related crashes:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| GPU info | `nvidia-smi` / `dmesg \| grep -i gpu` | `system_profiler SPDisplaysDataType` | `powershell "Get-WmiObject Win32_VideoController"` |
| X errors | `grep -i "error\|segfault" /var/log/Xorg.0.log` | WindowServer crash logs in DiagnosticReports | `powershell "Get-WinEvent @{LogName='System'; ProviderName='dxgkrnl'}"` |
| GPU driver log | `dmesg \| grep -i "nvidia\|amdgpu\|radeon"` | `log show --predicate 'subsystem == "com.apple.iokit.IOGraphicsFamily"'` | GPU driver-specific event logs |

### 11. Check for known issues:
    - Search the program's GitHub issues, bug tracker
    - Check if the crash is reproducible
    - Check if a newer version is available

### 12. Analyze crash signatures:
    Look for common crash indicators:
    - **Segmentation fault (SIGSEGV)**: Memory access violation
    - **SIGABRT**: Program called abort()
    - **SIGILL**: Illegal instruction
    - **SIGBUS**: Bus error
    - **SIGFPE**: Floating point exception
    - **OOM Killer**: Process killed due to out of memory
    - **Stack trace**: If available in logs

### 13. Try to reproduce the crash:
    Guide user to:
    - Run program from terminal to see error output:
      ```bash
      <program> 2>&1 | tee /tmp/program-output.log
      ```
    - Run with debug logging (if supported):
      ```bash
      <program> --debug
      <program> --verbose
      ```
    - Check environment variables that might affect behavior

### 14. Report findings:
    Summarize:
    - Probable cause of crash (if identified)
    - Relevant log entries
    - Any error messages or stack traces found
    - Resource issues if any
    - Recent system changes that might be related

### 15. Provide recommendations:
    Based on findings, suggest:
    - **If OOM kill**: Reduce memory usage, close other programs, add more RAM/swap
    - **If segfault**: Check for updates, try reinstalling program, report bug
    - **If dependency issue**: Reinstall program and dependencies
    - **If config issue**: Reset configuration, move config to backup
    - **If disk full**: Free up disk space
    - **If recent update**: Consider downgrading or wait for fix
    - **If reproducible**: Enable debug mode, create bug report with steps
    - **If GPU-related**: Update drivers, check GPU health

## Important notes:
- Always detect OS first — log locations and tools differ significantly
- Use sudo for system logs and journal access (Linux/macOS)
- Times in logs may be in UTC — account for timezone
- macOS logs are in `~/Library/Logs/DiagnosticReports/`
- Windows crash dumps are in `%LOCALAPPDATA%\CrashDumps\`
- Some log files can be very large — use grep and tail to filter
- Core dumps can be very large — ask before extracting
- Privacy: don't ask to see sensitive information from logs
- If no obvious cause is found, explain what additional info would help
