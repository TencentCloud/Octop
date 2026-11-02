# Monitor System Resources

You are helping the user monitor live system resource usage (CPU, RAM, disk I/O, network).

## Platform Detection

Before running commands, detect the OS:
```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux → Linux, macOS → Darwin, Windows → MINGW*/MSYS*/CYGWIN*
```

## Task

### 1. Quick resource overview:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| System overview | `top -b -n 1 \| head -20` | `top -l 1 -n 20 -stats pid,command,cpu,mem` | `powershell "Get-Process \| Sort CPU -Desc \| Select -First 20 \| Format-Table"` |
| htop (if installed) | `htop` | `htop` (via `brew install htop`) | Not available |
| Modern alternative | `btop` | `btop` (via `brew install btop`) | Not available |

### 2. CPU monitoring:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| CPU usage summary | `mpstat 1 5` (needs sysstat) | `top -l 1 -n 0 -stats cpu` | `typeperf "\Processor(_Total)\% Processor Time" -sc 5` |
| Per-core usage | `mpstat -P ALL 1 5` | `top -l 1 -n 0 -stats cpu` | `typeperf "\Processor(*)\% Processor Time" -sc 1` |
| Top consumers | `ps aux --sort=-%cpu \| head -10` | `ps aux -r \| head -10` | `powershell "Get-Process \| Sort CPU -Desc \| Select -First 10"` |
| CPU frequency/temp | `grep MHz /proc/cpuinfo && sensors` | `sysctl -n hw.cpufrequency` | `wmic cpu get CurrentClockSpeed,LoadPercentage` |
| Watch CPU | `watch -n 1 "grep MHz /proc/cpuinfo \| head -5 && sensors"` | `sudo powermetrics --samplers cpu_power -i 3000 -n 1` | `typeperf "\Processor(_Total)\% Processor Time" -sc 0` (continuous) |

### 3. Memory monitoring:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Memory usage | `free -h` | `vm_stat` + `sysctl hw.memsize` | `wmic OS get TotalVisibleMemorySize,FreePhysicalMemory` |
| Detailed info | `cat /proc/meminfo` | `vm_stat` | `wmic OS get *` |
| Top consumers | `ps aux --sort=-%mem \| head -10` | `ps aux -m \| head -10` | `powershell "Get-Process \| Sort WorkingSet64 -Desc \| Select -First 10"` |
| Watch memory | `watch -n 1 free -h` | `watch -n 1 vm_stat` | `typeperf "\Memory\Available MBytes" -sc 0` |

### 4. Disk I/O monitoring:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| I/O statistics | `iostat -x 1 5` (needs sysstat) | `iostat -d -w 1 -c 5` | `typeperf "\PhysicalDisk(*)\% Disk Time" -sc 5` |
| Per-process I/O | `iotop -o` (needs root) | `sudo fs_usage -f filesys` (2s) | `powershell "Get-Process \| Sort HandleCount -Desc"` |
| Watch disk I/O | `watch -n 1 "iostat -x \| grep -E 'Device\|sd\|nvme'"` | `watch -n 1 iostat -d -w 1 -c 1` | `typeperf "\PhysicalDisk(_Total)\Avg. Disk Queue Length" -sc 0` |

### 5. Network monitoring:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Interface stats | `ifstat 1 5` or `ss -s` | `netstat -ib -w 1` | `typeperf "\Network Interface(*)\Bytes Total/sec" -sc 5` |
| Bandwidth per if | `bmon` or `iftop` | `nettop -P -n` | `typeperf "\Network Interface(*)\*"` |
| Active connections | `ss -tunap` | `netstat -an` | `netstat -ano` |
| Per-process network | `nethogs` (needs root) | `nettop -P -m tcp` | `powershell "Get-NetTCPConnection \| Select LocalPort,OwningProcess"` |

### 6. Combined system monitoring:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| All-in-one | `glances` (needs install) | `btop` (via brew) | Task Manager (built-in) |
| Custom dashboard | `watch -n 1 '...custom commands...'` | `watch -n 1 '...custom commands...'` | `typeperf "\Processor(*)\% Processor Time" "\Memory\*" "\PhysicalDisk(*)\*"` |

### 7. GPU monitoring:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| NVIDIA | `nvidia-smi -l 1` | N/A (Apple Silicon has no NVIDIA) | `nvidia-smi -l 1` (if NVIDIA GPU) |
| AMD | `radeontop` or `rocm-smi` | N/A | AMD Adrenalin overlay |
| Apple Silicon | N/A | `sudo powermetrics --samplers gpu_power -i 3000 -n 1` | N/A |
| Generic | `intel_gpu_top` (Intel) | `system_profiler SPDisplaysDataType` | `powershell "Get-Counter '\GPU Engine(*)\Utilization Percentage'"` |

### 8. Process tree with resource usage:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Process tree | `pstree -p` | `pstree -p` (via `brew install psmisc`) | N/A |
| Resource tree | `ps auxf` | `ps auxf` | `powershell "Get-CimInstance Win32_Process \| Select Name,ParentProcessId,WorkingSetSize"` |
| Resource hogs | `ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu \| head -20` | `ps -eo pid,ppid,command,%mem,%cpu -r \| head -20` | `powershell "Get-Process \| Sort CPU -Desc \| Select -First 20 Id,ProcessName,CPU,@{N='MemMB';E={[math]::Round($_.WorkingSet64/1MB)}}"` |

### 9. System load monitoring:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Load average | `uptime` | `uptime` | `wmic cpu get loadpercentage` |
| Load over time | `watch -n 1 "uptime && cat /proc/loadavg"` | `watch -n 1 uptime` | `typeperf "\System\Processor Queue Length" -sc 0` |

## Present Summary to User

Provide snapshot of:
- **CPU:** Usage %, load average, top processes
- **Memory:** Used/Free, swap usage, top consumers
- **Disk:** Usage %, I/O wait, active reads/writes
- **Network:** Bandwidth usage, active connections
- **GPU:** Usage % (if applicable)

Flag any concerning patterns:
- High CPU usage (>80% sustained)
- Low memory (<10% free)
- High swap usage
- Disk I/O bottlenecks
- Network saturation

## Install Monitoring Tools if Needed

| Tool | Linux | macOS | Windows |
|------|-------|-------|---------|
| htop/btop | `sudo apt install htop btop` | `brew install htop btop` | N/A (use Task Manager) |
| sysstat (iostat, mpstat) | `sudo apt install sysstat` | `brew install sysstat` | N/A |
| iotop | `sudo apt install iotop` | N/A (use `fs_usage`) | N/A |
| iftop/nethogs | `sudo apt install iftop nethogs` | `brew install iftop nethogs` | N/A |
| glances | `sudo apt install glances` | `brew install glances` | N/A |
| smartmontools | `sudo apt install smartmontools` | `brew install smartmontools` | Download from smartmontools.org |
| osx-cpu-temp | N/A | `brew install osx-cpu-temp` | N/A |

## Troubleshooting High Usage

**High CPU:**
- Identify process: `top` (Linux/macOS) or Task Manager (Windows)
- Check if legitimate (updates, backups, encoding)
- Kill if necessary: `kill -15 PID` (Linux/macOS) or `Stop-Process -Id PID` (Windows)

**High Memory:**
- Check for memory leaks: `ps aux --sort=-%mem` (Linux/macOS)
- Linux: Clear caches: `sudo sync && sudo sysctl -w vm.drop_caches=3`
- Check for swap thrashing

**High Disk I/O:**
- Linux: `iotop -o`
- macOS: `sudo fs_usage -f filesys`
- Windows: Resource Monitor → Disk tab
- Check disk health

**High Network:**
- Linux: `iftop` or `ss -tunap`
- macOS: `nettop -P -m tcp`
- Windows: Resource Monitor → Network tab
