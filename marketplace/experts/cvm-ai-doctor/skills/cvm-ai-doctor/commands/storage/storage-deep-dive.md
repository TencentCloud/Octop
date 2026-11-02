# Storage Deep Dive

You are helping the user investigate storage space consumption or I/O performance issues in depth.

## Platform Detection

```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux → Linux, macOS → Darwin, Windows → MINGW*/MSYS*/CYGWIN*
```

## Part 1: Disk Space — Find What's Consuming Space

### 1. Top-level disk usage overview

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Partition usage | `df -h` | `df -h` | `wmic logicaldisk get caption,freespace,size` |
| Top directories (depth 2) | `du -h --max-depth=2 / 2>/dev/null \| sort -rh \| head -20` | `du -h -d 2 / 2>/dev/null \| sort -rh \| head -20` | `Get-ChildItem C:\ -Depth 2 -ErrorAction SilentlyContinue \| Sort-Object Length -Desc \| Select-Object -First 20 FullName,Length` |
| Find largest files | `find / -xdev -type f -size +100M 2>/dev/null \| xargs ls -lh \| sort -k5 -rh \| head -20` | `find / -xdev -type f -size +100m 2>/dev/null \| xargs ls -lh \| sort -k5 -rh \| head -20` | `Get-ChildItem C:\ -Recurse -ErrorAction SilentlyContinue \| Sort-Object Length -Desc \| Select-Object -First 20 FullName,@{N='MB';E={[math]::Round($_.Length/1MB,1)}}` |

### 2. Common space hogs (Linux/macOS)

```bash
# System logs
journalctl --disk-usage 2>/dev/null
du -sh /var/log/ 2>/dev/null

# Package cache
du -sh /var/cache/apt/ 2>/dev/null        # Ubuntu/Debian
du -sh /var/cache/yum/ 2>/dev/null        # CentOS/RHEL
du -sh $(brew --cache) 2>/dev/null        # macOS Homebrew

# Temp files
du -sh /tmp/ /var/tmp/ 2>/dev/null

# Docker images/volumes (if applicable)
docker system df 2>/dev/null
```

### 3. Inode exhaustion check

| Check | Linux | macOS | Windows |
|-------|-------|-------|---------|
| Inode usage | `df -i` | `df -i` | N/A (NTFS uses MFT) |
| Find inode-heavy dirs | `find / -xdev -printf '%h\n' 2>/dev/null \| sort \| uniq -c \| sort -rn \| head -10` | `find / -xdev -printf '%h\n' 2>/dev/null \| sort \| uniq -c \| sort -rn \| head -10` | — |

**AI Interpretation**: If `df -h` shows space available but `df -i` shows 100% → inode exhaustion. Delete small/temp files in the high-inode directory.

---

## Part 2: Disk I/O — Identify I/O Bottlenecks

### 4. I/O-heavy process identification

| Check | Linux | macOS | Windows |
|-------|-------|-------|---------|
| Per-process I/O | `sudo iotop -b -n 1 -o 2>/dev/null \|\| pidstat -d 1 3` | `sudo fs_usage -f diskio 2>/dev/null \| head -30` | `Get-Process \| Sort-Object -Property IO -Desc \| Select-Object -First 10 Name,Id,@{N='IO_MB';E={[math]::Round(($_.ReadOperationCount+$_.WriteOperationCount)/1MB,2)}}` |
| Disk queue & latency | `iostat -x 1 3 2>/dev/null \| awk '/^[sv]d\|^nvme/ {printf "%s util=%.1f%% await=%.1fms\n",$1,$14,$10}'` | `iostat -d -w 1 -c 3 2>/dev/null` | `Get-Counter '\PhysicalDisk(_Total)\Avg. Disk Queue Length' -SampleInterval 1 -MaxSamples 3` |

### 5. Interpret results

**AI Analysis**:
- `util%` > 80% → disk is saturated, bottleneck confirmed
- `await` > 100ms → disk responding very slowly (failing disk or I/O storm)
- Single process dominating → throttle with `ionice -c 3 -p <pid>` or restart service
- Multiple processes → legitimate workload; upgrade storage or optimize I/O patterns

---

## ⚠️ Cleanup Actions (require user confirmation)

```bash
# Clean system logs older than 7 days
sudo journalctl --vacuum-time=7d

# Clean apt cache
sudo apt-get clean

# Clean temp files
sudo rm -rf /tmp/* /var/tmp/*

# Docker cleanup (removes stopped containers, dangling images)
docker system prune
```

**Last Updated**: 2026-04-02
**Compatibility**: Linux (full), macOS (partial), Windows (partial)
