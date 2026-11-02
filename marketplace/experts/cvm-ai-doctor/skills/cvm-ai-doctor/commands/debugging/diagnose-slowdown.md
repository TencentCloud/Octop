# Diagnose System Slowdown

You are helping the user diagnose system laginess and performance issues.

## Platform Detection

Before running any commands, detect the OS and use platform-appropriate commands.

```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux: Linux
# macOS: Darwin  
# Windows (Git Bash): MINGW* | MSYS* | CYGWIN*
```

## Your tasks:

1. **Gather initial information:**
   Ask the user:
   - When did the slowdown start?
   - Is it constant or intermittent?
   - What activities trigger it? (startup, specific applications, general use)
   - Any recent changes? (updates, new software, configuration changes)

2. **Check current system load:**

   | Check | Linux | macOS | Windows (Git Bash) |
   |-------|-------|-------|-------------------|
   | Load averages | `uptime` | `uptime` | `wmic cpu get loadpercentage` |
   | Process count | `ps aux \| wc -l` | `ps aux \| wc -l` | N/A |
   | Process snapshot | `top -b -n 1 \| head -20` | `top -l 1 -n 20 -stats pid,command,cpu,mem` | `powershell "Get-Process \| Sort CPU -Desc \| Select -First 20"` |

3. **CPU analysis:**

   | Check | Linux | macOS | Windows |
   |-------|-------|-------|---------|
   | CPU info | `lscpu` or `cat /proc/cpuinfo` | `sysctl -n machdep.cpu.brand_string` | `wmic cpu get Name,NumberOfCores,MaxClockSpeed` |
   | Top consumers | `ps aux --sort=-%cpu \| head -20` | `ps aux -r \| head -20` | `powershell "Get-Process \| Sort CPU -Desc \| Select -First 20"` |
   | Per-core usage | `mpstat -P ALL 1 1` (needs sysstat) | `top -l 1 -n 0 -stats cpu` | `typeperf "\Processor(_Total)\% Processor Time" -sc 1` |
   | Frequency | `cat /proc/cpuinfo \| grep MHz` | `sysctl -n hw.cpufrequency` | `wmic cpu get CurrentClockSpeed` |
   | Temperature | `sensors` (needs lm-sensors) | `osx-cpu-temp` (needs brew) | PowerShell WMI thermal query |

4. **Memory analysis:**

   | Check | Linux | macOS | Windows |
   |-------|-------|-------|---------|
   | Memory usage | `free -h` | `vm_stat` + `sysctl hw.memsize` | `wmic OS get TotalVisibleMemorySize,FreePhysicalMemory` |
   | Top consumers | `ps aux --sort=-%mem \| head -20` | `ps aux -m \| head -20` | `powershell "Get-Process \| Sort WorkingSet64 -Desc \| Select -First 20"` |
   | Swap usage | `swapon --show` | `sysctl vm.swapusage` | `wmic pagefileset get AllocatedBaseSize,CurrentUsage` |
   | OOM events | `sudo journalctl -k \| grep -i "out of memory"` | `log show --predicate 'messageType == "error"' --last 1h \| grep -i oom` | PowerShell Event Log Level 1 |

5. **Disk I/O analysis:**

   | Check | Linux | macOS | Windows |
   |-------|-------|-------|---------|
   | Disk usage | `df -h` | `df -h` | `wmic logicaldisk get caption,size,freespace` |
   | Inode usage | `df -i` | `df -i` | N/A |
   | I/O stats | `iostat -x 1 5` (needs sysstat) | `iostat -d -w 1 -c 2` | `typeperf "\PhysicalDisk(_Total)\% Disk Time" -sc 5` |
   | Top I/O procs | `sudo iotop -b -n 1` | `sudo fs_usage -f filesys` (2s) | `powershell "Get-Process \| Sort HandleCount -Desc"` |
   | Disk wait | Look at `wa` in `top`/`vmstat` | `iostat` | Disk Queue Length counter |

6. **Process analysis:**

   | Check | Linux | macOS | Windows |
   |-------|-------|-------|---------|
   | All processes | `ps aux` | `ps aux` | `powershell "Get-Process"` |
   | Process tree | `pstree -p` | `pstree -p` (needs brew) | N/A |
   | Zombie procs | `ps aux \| grep Z` | `ps aux \| grep Z` | N/A |
   | D-state procs | `ps aux \| grep " D "` | `ps aux \| grep " U "` | N/A |
   | Long-running | `ps -eo pid,user,start,time,cmd --sort=-time` | `ps -eo pid,lstart,time,command -sort time` | `powershell "Get-Process \| Sort StartTime"` |

7. **Check for system resource contention:**
   - Linux: `vmstat 1 5` (context switches, interrupts, swap in/out)
   - macOS: `vm_stat` for page stats, `iostat` for CPU/disk
   - Windows: `typeperf "\System\Processor Queue Length" "\System\Context Switches/sec" -sc 5`

8. **Network issues (can cause perceived slowness):**

   | Check | Linux | macOS | Windows |
   |-------|-------|-------|---------|
   | Connections | `ss -s` | `netstat -s` | `netstat -e` |
   | DNS test | `time nslookup google.com` | `time nslookup google.com` | `time nslookup google.com` |
   | Network errors | `ip -s link` | `netstat -i` | `netstat -e` |

9. **Graphics/Desktop environment (for GUI slowness):**
   - Linux: Check GPU usage with `nvidia-smi` / `radeontop`; compositor settings
   - macOS: `sudo powermetrics --samplers gpu_power -i 3000 -n 1`
   - Windows: `powershell "Get-Counter '\GPU Engine(*)\Utilization Percentage'"`

10. **Check system logs for errors:**

    | Check | Linux | macOS | Windows |
    |-------|-------|-------|---------|
    | Recent errors | `sudo journalctl -p err -b` | `log show --predicate 'messageType == "error"' --last 1h` | `powershell "Get-WinEvent -FilterHashtable @{LogName='System'; Level=2} -MaxEvents 20"` |
    | Kernel messages | `dmesg \| tail -50` | `log show --predicate 'subsystem == "com.apple.kernel"' --last 10m` | PowerShell kernel-power events |
    | System log | `sudo journalctl -xe --no-pager \| tail -100` | `log show --last 10m --style compact \| tail -100` | PowerShell System event log |

11. **Check for background services/processes:**

    | Check | Linux | macOS | Windows |
    |-------|-------|-------|---------|
    | Running services | `systemctl list-units --type=service --state=running` | `launchctl list` | `powershell "Get-Service \| Where Status -eq Running"` |
    | Failed services | `systemctl --failed` | `launchctl list \| grep '^\-'` | `powershell "Get-Service \| Where Status -eq Stopped"` |
    | Background indexers | Check: updatedb, baloo, tracker | Check: mdworker, Spotlight | Check: Windows Search, Antivirus scans |

12. **Application-specific checks:**
    If slowness is application-specific:
    - Browser: check extensions, tabs, cache size
    - Database: check for long-running queries
    - IDE: check for indexing, plugins
    - Check application logs (paths vary by OS):
      - Linux: `~/.local/share/`, `/var/log/`
      - macOS: `~/Library/Logs/`, `~/Library/Application Support/`
      - Windows: `%APPDATA%`, `%LOCALAPPDATA%`

13. **Historical data (if available):**
    - Linux: `sar -u` (if sysstat configured), `sudo journalctl --since "1 day ago" -p err`
    - macOS: `log show --start "1 day ago" --predicate 'messageType == "error"'`
    - Windows: PowerShell Event Log with time range filter

14. **Analyze and report findings:**
    Categorize issues found:
    - **CPU bottleneck**: High CPU usage, identify culprit processes
    - **Memory bottleneck**: High memory usage, swapping, suggest adding RAM or killing processes
    - **Disk I/O bottleneck**: High wait times, slow disk, suggest SSD upgrade or I/O optimization
    - **Thermal throttling**: High temperatures causing CPU slowdown
    - **Runaway processes**: Specific process consuming excessive resources
    - **Resource leaks**: Memory or handle leaks in specific applications
    - **Background tasks**: Indexing, updates, backups running
    - **Network issues**: DNS problems, slow network affecting system

15. **Provide recommendations:**
    Based on findings, suggest:
    - Kill or restart specific problematic processes
    - Disable unnecessary services
    - Linux: Adjust swappiness: `sudo sysctl vm.swappiness=10`
    - Clean up disk space if low
    - Update or reinstall problematic drivers
    - Install missing performance tools:
      - Linux: `sudo apt install sysstat iotop htop lm-sensors`
      - macOS: `brew install htop smartmontools osx-cpu-temp`
      - Windows: winget / choco for additional tools
    - Schedule resource-intensive tasks for off-hours
    - Hardware upgrades (RAM, SSD) if appropriate
    - Investigate and fix application-specific issues
    - Reboot if system has been up for extended period with memory leaks

## Important notes:
- Always detect OS first and use platform-appropriate commands
- Use sudo for system-level diagnostics (Linux/macOS)
- Be systematic - check CPU, memory, disk, and network in order
- Correlate findings with user's description of when slowness occurs
- Don't immediately kill processes - confirm with user first
- Consider both hardware and software causes
- If a tool is not available, suggest the install command for the detected platform
