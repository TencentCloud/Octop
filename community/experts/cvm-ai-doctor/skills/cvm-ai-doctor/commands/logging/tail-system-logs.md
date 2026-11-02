# Tail System Logs

You are helping the user monitor system logs in real-time for debugging and system monitoring.

## Platform Detection

Before running commands, detect the OS:
```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux → Linux, macOS → Darwin, Windows → MINGW*/MSYS*/CYGWIN*
```

## Task

### 1. Follow all system logs:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Follow all logs | `journalctl -f` | `log stream` | `powershell "Get-WinEvent -LogName System -MaxEvents 0 -Wait"` |
| With timestamp | `journalctl -f -o short-precise` | `log stream --style compact` | N/A (timestamps included) |
| Errors only | `journalctl -f -p err` | `log stream --predicate 'messageType == "error"'` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=2} -MaxEvents 0 -Wait"` |

### 2. Follow specific services:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Specific service | `journalctl -u SERVICE_NAME -f` | `log stream --predicate 'process == "process_name"'` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='ServiceName'} -MaxEvents 0 -Wait"` |
| Multiple services | `journalctl -u NetworkManager -u systemd-resolved -f` | `log stream --predicate 'process == "NetworkManager" OR process == "resolved"'` | `powershell "Get-WinEvent -FilterHashtable @{ProviderName='Service1','Service2'} -MaxEvents 0 -Wait"` |

**Common services to monitor:**

| Service | Linux | macOS | Windows |
|---------|-------|-------|---------|
| Network | `journalctl -u NetworkManager -f` | `log stream --predicate 'subsystem == "com.apple.network"'` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='*Network*'} -MaxEvents 0 -Wait"` |
| Display | `journalctl -u gdm -u gnome-shell -f` | `log stream --predicate 'process == "WindowServer"'` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='*dxgkrnl*','*Display*'} -MaxEvents 0 -Wait"` |
| Audio | `journalctl --user -u pipewire -f` | `log stream --predicate 'subsystem == "com.apple.audio"'` | Windows Audio events |

### 3. Follow kernel messages:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Kernel ring buffer | `dmesg -w` | `log stream --predicate 'subsystem == "com.apple.kernel"'` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-Power'} -MaxEvents 0 -Wait"` |
| Kernel from journal | `journalctl -k -f` | `log stream --predicate 'sender == "kernel"'` | N/A |
| Specific subsystem | `dmesg -w \| grep -i usb` | `log stream --predicate 'subsystem == "com.apple.iokit.IOUSBHostFamily"'` | USB-specific event logs |

### 4. Follow authentication logs:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Auth attempts | `journalctl -u ssh -u sudo -f` | `log stream --predicate 'subsystem == "com.apple.security"'` | `powershell "Get-WinEvent -FilterHashtable @{LogName='Security'; ID=4624,4625} -MaxEvents 0 -Wait"` |
| Login events | `journalctl _SYSTEMD_UNIT=systemd-logind.service -f` | `log stream --predicate 'process == "securityd"'` | PowerShell security log |
| Auth log file | `tail -f /var/log/auth.log` | N/A | N/A |

### 5. Follow application logs:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| X11 session | `tail -f ~/.xsession-errors` | N/A | N/A |
| User session | `journalctl --user -f` | `log stream --predicate 'processImagePath contains "'$HOME'"'` | Application-specific event logs |
| Specific app | `journalctl -f \| grep -i "app-name"` | `log stream --predicate 'process == "app_name"'` | `powershell "Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='AppName'} -MaxEvents 0 -Wait"` |

### 6. Follow with filtering:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Errors + warnings | `journalctl -f -p warning` | `log stream --predicate 'messageType == "error" OR messageType == "warning"'` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2,3} -MaxEvents 0 -Wait"` |
| By identifier | `journalctl -f -t identifier-name` | `log stream --predicate 'sender == "com.example.name"'` | By ProviderName |
| Grep terms | `journalctl -f \| grep -i "error\|fail\|critical"` | `log stream \| grep -i "error\|fail\|critical"` | `powershell "... \| Where Message -match 'error\|fail'"` |

### 7. Follow with context:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Last N + new | `journalctl -n 100 -f` | `log show --last 5m && log stream` | Last N via `-MaxEvents`, follow via `-Wait` |
| Since time | `journalctl --since "10 minutes ago" -f` | `log stream --start "$(date -v-10M '+%Y-%m-%d %H:%M:%S')"` | `StartTime` parameter |
| Current boot | `journalctl -b -f` | `log stream` (macOS doesn't separate boot logs) | `powershell "... StartTime=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"` |

## Common Monitoring Scenarios

| Scenario | Linux | macOS | Windows |
|----------|-------|-------|---------|
| Boot issues | `journalctl -b -f` | `log stream --predicate 'boot=true'` | PowerShell with boot time filter |
| Network trouble | `journalctl -u NetworkManager -u systemd-resolved -u wpa_supplicant -f` | `log stream --predicate 'subsystem == "com.apple.network"'` | Network Profile events |
| Display/GPU | `journalctl -f \| grep -iE "drm\|amdgpu\|nvidia\|wayland\|xorg"` | `log stream --predicate 'subsystem == "com.apple.iokit.IOGraphicsFamily"'` | Display driver events |
| USB debugging | `dmesg -w \| grep -i usb` | `log stream --predicate 'subsystem contains "USB"'` | USB events |
| Bluetooth | `journalctl -u bluetooth -f` | `log stream --predicate 'subsystem == "com.apple.bluetooth"'` | Bluetooth events |
| Audio | `journalctl --user -u pipewire -u wireplumber -f` | `log stream --predicate 'subsystem == "com.apple.audio"'` | Windows Audio events |

## Log Rotation & Management

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Check log size | `journalctl --disk-usage` | N/A (macOS manages automatically) | Event Viewer → Properties |
| Vacuum old logs | `sudo journalctl --vacuum-time=7d` | N/A | `wevtutil cl System` (clear) |
| View available boots | `journalctl --list-boots` | N/A | N/A |
| Previous boot | `journalctl -b -1 -f` | N/A | Previous boot time filter |

## Alternative Log Files

Some systems still use traditional log files:

| Log Type | Linux | macOS | Windows |
|----------|-------|-------|---------|
| System | `/var/log/syslog` | N/A (Unified Logging) | Event Viewer → System |
| Kernel | `/var/log/kern.log` | `log show --predicate 'sender == "kernel"'` | Event Viewer → System (Kernel-Power) |
| Auth | `/var/log/auth.log` | `log show --predicate 'subsystem == "com.apple.security"'` | Event Viewer → Security |
| Package mgmt | `/var/log/dpkg.log` | `brew log` / `var/log/install.log` | N/A |
| X11 | `/var/log/Xorg.0.log` | N/A | N/A |

## Notes

- Linux: Use `-o verbose` for max detail, `-o json` for machine-readable
- macOS: `log stream` for real-time, `log show --last Xm` for historical
- Windows: `-Wait` for real-time follow, `-MaxEvents` to limit
- Ctrl+C to stop following logs on all platforms
