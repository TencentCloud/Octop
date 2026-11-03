---
name: system-logs-check
description: Detect system errors through log analysis - kernel errors, hardware failures, OOM events, auth failures
category: standalone-checks
---

# System Logs & Errors Check

**Purpose**: System logs are the **only source** for detecting hardware failures, kernel panics, OOM events, and service failures.

**Based on**: Brendan Gregg's USE Method (Errors dimension) + Google SRE error rate monitoring

---

## 🎯 AI Usage Guide

### Quick/Deep Workflow

```mermaid
User Question → Quick Mode (10s) → Analyze Results → Deep Mode (20-40s, if needed)
```

**When to use each mode**:

| Mode | Duration | Purpose | When to Use |
|------|----------|---------|-------------|
| **Quick** | 10s | Count errors across all categories | Health check, triage, "检查日志" |
| **Deep** | 20-40s | Detailed error analysis + root cause | Quick finds errors, troubleshooting |

**Decision Logic**:
```yaml
Quick Mode Results:
  - All OK → Stop, report healthy
  - Any CRITICAL → Deep Mode on that category
  - Multiple WARNINGS → Deep Mode on top 2 categories
  
Deep Mode Focus:
  - kernel: Kernel error details + hardware correlation
  - oom: OOM event timeline + memory leak analysis
  - fs: File system errors + disk health
  - auth: Attack pattern analysis + IP reputation
  - service: Service logs + dependency check
```

**Output Format**:

```yaml
# Quick Mode
status: OK | WARNING | CRITICAL
summary: "One-line result"
categories:
  - kernel: {count: N, status: OK/WARNING/CRITICAL}
  - oom: {count: N, status: OK/WARNING/CRITICAL}
  - fs: {count: N, status: OK/WARNING/CRITICAL}
  - auth: {count: N, status: OK/WARNING/CRITICAL}
  - service: {count: N, status: OK/WARNING/CRITICAL}
next_action: "stop" | "deep_kernel" | "deep_oom" | ...

# Deep Mode
category: kernel | oom | fs | auth | service
root_cause: "Identified cause"
evidence: ["detail 1", "detail 2"]
recommendation: ["action 1", "action 2"]
```

---

## ⚡ Quick Mode (10s)

**Purpose**: Rapid error count across 5 categories - triage in 10 seconds

### 1. Kernel Errors Count

```bash
# Linux
dmesg -l err,crit,alert,emerg 2>/dev/null | wc -l

# macOS
log show --predicate 'messageType == error' --last 1h 2>/dev/null | wc -l

# Windows (PowerShell)
(Get-EventLog -LogName System -EntryType Error -Newest 50 -ErrorAction SilentlyContinue).Count
```

**Thresholds**:
```yaml
CRITICAL: > 10
WARNING: 1-10
OK: 0
```

---

### 2. OOM Killer Events Count

```bash
# Linux
dmesg 2>/dev/null | grep -c "Out of memory"

# macOS
log show --predicate 'eventMessage contains "killed"' --last 1d 2>/dev/null | wc -l

# Windows (Application crashes)
(Get-EventLog -LogName Application -Source "Application Error" -Newest 20 -ErrorAction SilentlyContinue).Count
```

**Thresholds**:
```yaml
CRITICAL: > 5
WARNING: 1-5
OK: 0
```

---

### 3. File System Errors Count

```bash
# Linux
dmesg 2>/dev/null | grep -i "ext4\|xfs\|btrfs" | grep -ci error

# macOS
log show --predicate 'subsystem == "com.apple.filesystems"' --last 1d 2>/dev/null | grep -ci error

# Windows
(Get-EventLog -LogName System -Source "Ntfs" -EntryType Error -Newest 20 -ErrorAction SilentlyContinue).Count
```

**Thresholds**:
```yaml
WARNING: > 0
OK: 0
```

---

### 4. Authentication Failures Count (Last Hour)

```bash
# Linux
AUTH_LOG="/var/log/auth.log"
[ ! -f "$AUTH_LOG" ] && AUTH_LOG="/var/log/secure"
grep "Failed password" "$AUTH_LOG" 2>/dev/null | grep "$(date '+%b %e %H')" | wc -l

# macOS
log show --predicate 'eventMessage contains "authentication failed"' --last 1h 2>/dev/null | wc -l

# Windows
(Get-EventLog -LogName Security -InstanceId 4625 -Newest 50 -ErrorAction SilentlyContinue).Count
```

**Thresholds**:
```yaml
CRITICAL: > 50 (likely attack)
WARNING: 11-50
OK: 0-10
```

---

### 5. Failed Services Count

```bash
# Linux
systemctl --failed --no-legend 2>/dev/null | wc -l

# macOS
launchctl list 2>/dev/null | grep -v "^-\|0$" | wc -l

# Windows
(Get-Service | Where-Object {$_.Status -ne "Running" -and $_.StartType -eq "Automatic"}).Count
```

**Thresholds**:
```yaml
WARNING: > 0
OK: 0
```

---

### Quick Mode Complete Script

```bash
#!/bin/bash
# Quick Mode: Error count only (10 seconds)

echo "=== Quick Mode: System Log Check ==="

# 1. Kernel Errors
KERNEL_ERRORS=$(dmesg -l err,crit,alert,emerg 2>/dev/null | wc -l)
[ "$KERNEL_ERRORS" -gt 10 ] && K_STATUS="CRITICAL" || [ "$KERNEL_ERRORS" -gt 0 ] && K_STATUS="WARNING" || K_STATUS="OK"
echo "Kernel: $KERNEL_ERRORS errors [$K_STATUS]"

# 2. OOM Events
OOM_COUNT=$(dmesg 2>/dev/null | grep -c "Out of memory")
[ "$OOM_COUNT" -gt 5 ] && O_STATUS="CRITICAL" || [ "$OOM_COUNT" -gt 0 ] && O_STATUS="WARNING" || O_STATUS="OK"
echo "OOM: $OOM_COUNT events [$O_STATUS]"

# 3. FS Errors
FS_ERRORS=$(dmesg 2>/dev/null | grep -i "ext4\|xfs" | grep -ci error)
[ "$FS_ERRORS" -gt 0 ] && F_STATUS="WARNING" || F_STATUS="OK"
echo "File System: $FS_ERRORS errors [$F_STATUS]"

# 4. Auth Failures
AUTH_LOG="/var/log/auth.log"
[ ! -f "$AUTH_LOG" ] && AUTH_LOG="/var/log/secure"
FAILED_LOGINS=$(grep "Failed password" "$AUTH_LOG" 2>/dev/null | grep "$(date '+%b %e %H')" | wc -l)
[ "$FAILED_LOGINS" -gt 50 ] && A_STATUS="CRITICAL" || [ "$FAILED_LOGINS" -gt 10 ] && A_STATUS="WARNING" || A_STATUS="OK"
echo "Auth Failures: $FAILED_LOGINS/hour [$A_STATUS]"

# 5. Failed Services
FAILED_SERVICES=$(systemctl --failed --no-legend 2>/dev/null | wc -l)
[ "$FAILED_SERVICES" -gt 0 ] && S_STATUS="WARNING" || S_STATUS="OK"
echo "Services: $FAILED_SERVICES failed [$S_STATUS]"

# Overall Status
if [[ "$K_STATUS" == "CRITICAL" || "$O_STATUS" == "CRITICAL" || "$A_STATUS" == "CRITICAL" ]]; then
  echo "OVERALL: CRITICAL - Deep mode recommended"
elif [[ "$K_STATUS" == "WARNING" || "$O_STATUS" == "WARNING" || "$F_STATUS" == "WARNING" || "$A_STATUS" == "WARNING" || "$S_STATUS" == "WARNING" ]]; then
  echo "OVERALL: WARNING - Consider deep mode"
else
  echo "OVERALL: OK - No issues detected"
fi
```

**AI Instructions for Quick Mode**:
1. Execute the script above
2. Parse output to extract counts and statuses
3. Apply decision logic to determine next action:
   - All OK → Report healthy, stop
   - Any CRITICAL → Trigger Deep Mode on that category
   - 2+ WARNINGS → Trigger Deep Mode on top 2

---

## 🔬 Deep Mode (20-40s)

**Purpose**: Detailed error analysis + root cause identification

---

### Deep Mode: Kernel Errors

**When**: Quick shows kernel errors > 0

**Commands**:
```bash
# 1. Recent kernel errors with timestamp
dmesg -T -l err,crit,alert,emerg 2>/dev/null | tail -30

# 2. Hardware error correlation
grep -i "error\|fail\|bad\|hardware" /var/log/kern.log 2>/dev/null | tail -20

# 3. Disk I/O errors
dmesg 2>/dev/null | grep -i "I/O error\|bad sector" | tail -10
```

**Root Cause Inference** (AI should match these patterns):

```yaml
Pattern 1: Memory Hardware Failure
  Evidence:
    - "memory parity error" OR "ECC error"
    - "Machine check exception"
  Root Cause: "Memory module failure"
  Recommendation:
    - "Check memory: edac-util -s"
    - "Replace faulty memory module"
    - "See memory ECC check in hardware-other.md"

Pattern 2: Disk Failure
  Evidence:
    - "I/O error" OR "bad sector" OR "SATA error"
    - Specific disk name (sda, nvme0n1)
  Root Cause: "Disk hardware failure"
  Recommendation:
    - "Check SMART: smartctl -a /dev/<disk>"
    - "Backup data immediately"
    - "Replace disk if SMART shows failures"

Pattern 3: Driver/Kernel Bug
  Evidence:
    - "BUG:" OR "kernel panic" OR "oops"
    - Module name mentioned
  Root Cause: "Kernel driver bug or incompatibility"
  Recommendation:
    - "Check kernel version: uname -r"
    - "Update driver: modprobe -r <module> && modprobe <module>"
    - "Consider kernel update or rollback"

Pattern 4: USB/PCI Device Error
  Evidence:
    - "usb" OR "pci" in error messages
  Root Cause: "Device connection issue"
  Recommendation:
    - "Check physical connections"
    - "Try different USB port or cable"
    - "Check dmesg for device disconnect events"
```

---

### Deep Mode: OOM Killer Events

**When**: Quick shows OOM count > 0

**Commands**:
```bash
# 1. OOM event timeline
dmesg -T 2>/dev/null | grep -i "out of memory\|killed process" | tail -20

# 2. Which processes were killed
dmesg 2>/dev/null | grep "killed process" | awk '{print $(NF-7), $(NF-1)}' | tail -10

# 3. Current memory state
free -h

# 4. Top memory consumers
ps aux --sort=-%mem | head -10
```

**Root Cause Inference**:

```yaml
Pattern 1: Memory Leak
  Evidence:
    - Same process killed repeatedly (e.g., "java" 3 times)
    - OOM events increasing over time
  Root Cause: "Memory leak in <process_name>"
  Recommendation:
    - "Restart <process_name>"
    - "Check application logs for memory growth"
    - "Use 'ps aux' to monitor memory usage over time"
    - "Consider profiling with valgrind or heaptrack"

Pattern 2: Insufficient Memory
  Evidence:
    - Different processes killed
    - Total memory usage consistently near 100%
  Root Cause: "System memory insufficient for workload"
  Recommendation:
    - "Add more RAM"
    - "Enable swap if not present"
    - "Reduce concurrent processes"
    - "Current memory: <X>GB, Recommended: <Y>GB"

Pattern 3: Burst Traffic
  Evidence:
    - Multiple processes killed at same timestamp
    - Timestamps align with traffic spike
  Root Cause: "Sudden memory spike from traffic burst"
  Recommendation:
    - "Implement rate limiting"
    - "Add auto-scaling if cloud-based"
    - "Optimize application memory usage"

Pattern 4: No Swap
  Evidence:
    - Swap = 0 in 'free -h' output
    - Physical memory hit 100%
  Root Cause: "No swap space configured"
  Recommendation:
    - "Add swap file: fallocate -l 2G /swapfile && mkswap /swapfile && swapon /swapfile"
    - "Make persistent: echo '/swapfile none swap sw 0 0' >> /etc/fstab"
```

---

### Deep Mode: File System Errors

**When**: Quick shows FS errors > 0

**Commands**:
```bash
# 1. File system error details
dmesg 2>/dev/null | grep -i "ext4\|xfs\|btrfs" | grep -i error | tail -20

# 2. Mount status
mount | grep -v "tmpfs\|devtmpfs"

# 3. Disk usage
df -h

# 4. Inode usage
df -i
```

**Root Cause Inference**:

```yaml
Pattern 1: Disk Full
  Evidence:
    - "No space left on device"
    - df shows 100% usage
  Root Cause: "File system full"
  Recommendation:
    - "Find large files: du -h / | sort -rh | head -20"
    - "Clear logs: journalctl --vacuum-time=7d"
    - "Check for deleted files still held by processes: lsof +L1"

Pattern 2: Inode Exhaustion
  Evidence:
    - "No space left on device"
    - df -h shows space available BUT df -i shows 100%
  Root Cause: "Inode table full"
  Recommendation:
    - "Find inode-heavy directories: find / -xdev -printf '%h\n' | sort | uniq -c | sort -rn | head -20"
    - "Delete small/temp files"
    - "Common culprit: /var/spool/postfix, /tmp"

Pattern 3: Read-Only Remount
  Evidence:
    - "Read-only file system"
    - mount shows "ro" instead of "rw"
  Root Cause: "File system corruption, kernel remounted as read-only"
  Recommendation:
    - "Critical: Backup data immediately"
    - "Unmount and run fsck: umount <mountpoint> && fsck -y <device>"
    - "Check disk health with SMART: smartctl -a <device>"

Pattern 4: XFS/Btrfs Specific Errors
  Evidence:
    - "metadata I/O error" OR "corruption"
  Root Cause: "File system corruption"
  Recommendation:
    - "XFS: xfs_repair -n <device> (dry-run check)"
    - "Btrfs: btrfs scrub start <mountpoint>"
    - "Consider disk replacement if SMART shows issues"
```

---

### Deep Mode: Authentication Failures

**When**: Quick shows auth failures > 10/hour

**Commands**:
```bash
# 1. Recent failed attempts with IPs
AUTH_LOG="/var/log/auth.log"
[ ! -f "$AUTH_LOG" ] && AUTH_LOG="/var/log/secure"
grep "Failed password" "$AUTH_LOG" 2>/dev/null | tail -30

# 2. Top attacking IPs
grep "Failed password" "$AUTH_LOG" 2>/dev/null | awk '{print $(NF-3)}' | sort | uniq -c | sort -rn | head -10

# 3. fail2ban status (if installed)
fail2ban-client status sshd 2>/dev/null || echo "fail2ban not installed"

# 4. Current SSH sessions
who -u
```

**Root Cause Inference**:

```yaml
Pattern 1: Brute-Force Attack
  Evidence:
    - 50+ failures/hour
    - Failures from few IPs (< 5)
  Root Cause: "SSH brute-force attack"
  Recommendation:
    - "Install fail2ban: apt-get install fail2ban"
    - "Configure SSH key-only auth: PasswordAuthentication no in /etc/ssh/sshd_config"
    - "Change SSH port if needed"
    - "Block IPs: ufw deny from <IP>"

Pattern 2: Distributed Attack
  Evidence:
    - 50+ failures/hour
    - Failures from many IPs (> 10)
  Root Cause: "Distributed brute-force (botnet)"
  Recommendation:
    - "Enable fail2ban with aggressive settings"
    - "Disable password auth entirely (key-only)"
    - "Consider VPN or IP whitelist"
    - "Use cloud firewall if available"

Pattern 3: User Misconfiguration
  Evidence:
    - < 20 failures/hour
    - Same username repeatedly
    - Legitimate IP range
  Root Cause: "User forgot password or using wrong key"
  Recommendation:
    - "Contact user to verify credentials"
    - "Check if SSH key is correct"
    - "Reset password if needed"

Pattern 4: No fail2ban
  Evidence:
    - fail2ban not running
    - Failures increasing
  Root Cause: "No intrusion prevention system"
  Recommendation:
    - "Install fail2ban immediately"
    - "Configure for SSH: systemctl enable fail2ban && systemctl start fail2ban"
```

---

### Deep Mode: Service Failures

**When**: Quick shows failed services > 0

**Commands**:
```bash
# 1. List failed services
systemctl --failed

# 2. Get detailed status for each
for service in $(systemctl --failed --no-legend | awk '{print $1}'); do
  echo "=== $service ==="
  systemctl status "$service" --no-pager -l
  echo ""
done

# 3. Recent service logs
journalctl -u <service_name> -n 50 --no-pager
```

**Root Cause Inference**:

```yaml
Pattern 1: Dependency Missing
  Evidence:
    - Status shows "Dependency failed"
    - Logs mention "cannot find", "not found"
  Root Cause: "Service depends on failed service"
  Recommendation:
    - "Identify dependency: systemctl list-dependencies <service>"
    - "Start dependency first: systemctl start <dep_service>"
    - "Fix dependency chain"

Pattern 2: Configuration Error
  Evidence:
    - Status: "exit code 1" or "configuration error"
    - Logs mention "invalid config", "parse error"
  Root Cause: "Invalid configuration file"
  Recommendation:
    - "Check config: <service_name> -t (test config)"
    - "Review recent changes: git diff <config_file>"
    - "Restore from backup if needed"

Pattern 3: Port Already in Use
  Evidence:
    - Logs: "address already in use", "bind failed"
  Root Cause: "Another process using same port"
  Recommendation:
    - "Find process: lsof -i :<port>"
    - "Kill conflicting process or change port"
    - "Check for duplicate service instances"

Pattern 4: Permission Denied
  Evidence:
    - Logs: "permission denied", "cannot access"
  Root Cause: "Insufficient file/directory permissions"
  Recommendation:
    - "Check file ownership: ls -l <file>"
    - "Fix permissions: chown <user>:<group> <file>"
    - "Verify SELinux/AppArmor settings if applicable"
```

---

## 💡 Complete Usage Examples

### Example 1: User Reports "系统有错误"

**Step 1: Quick Mode**
```bash
bash system-logs.md  # Quick Mode section
```

**Output**:
```
Kernel: 3 errors [WARNING]
OOM: 0 events [OK]
File System: 0 errors [OK]
Auth Failures: 5/hour [OK]
Services: 1 failed [WARNING]
OVERALL: WARNING - Consider deep mode
```

**AI Decision**: 2 warnings → Deep mode on Kernel + Services

**Step 2: Deep Mode - Kernel**
```bash
# AI extracts and runs Deep Mode: Kernel Errors commands
dmesg -T -l err,crit,alert,emerg | tail -30
# Output shows: "SATA error on /dev/sda"
```

**AI Inference**: Matches Pattern 2 (Disk Failure)
- Root Cause: "Disk hardware failure on /dev/sda"
- Recommendation: Check SMART, backup data

**Step 3: Deep Mode - Services**
```bash
systemctl status failed_service
# Output: "bind: address already in use"
```

**AI Inference**: Matches Pattern 3 (Port in Use)
- Root Cause: "Port conflict"
- Recommendation: Find conflicting process

**Final Report**:
```
检测到 2 个问题：

1. 磁盘硬件错误 (/dev/sda)
   - 根因：硬盘出现坏道
   - 建议：立即备份数据，运行 smartctl -a /dev/sda 检查健康度

2. 服务启动失败 (failed_service)
   - 根因：端口被占用
   - 建议：运行 lsof -i :<port> 查找冲突进程
```

---

### Example 2: User Reports "OOM Killer"

**Step 1: Quick Mode**
```
OOM: 12 events [CRITICAL]
OVERALL: CRITICAL - Deep mode recommended
```

**Step 2: Deep Mode - OOM**
```bash
dmesg | grep "killed process" | awk '{print $(NF-7)}' | sort | uniq -c
# Output:
# 8 java
# 3 python
# 1 mysql
```

**AI Inference**: Pattern 1 (Memory Leak) - Java killed 8 times

**Final Report**:
```
检测到严重内存问题：

根因：Java 进程存在内存泄漏
证据：
- Java 进程被 OOM Killer 杀死 8 次
- 内存使用持续增长

建议：
1. 重启 Java 应用
2. 检查应用日志，查找内存增长原因
3. 使用 jmap/jstat 分析 Java 堆内存
4. 考虑增加系统内存或优化应用
```

---

### Example 3: Health Check (All OK)

**Step 1: Quick Mode**
```
Kernel: 0 errors [OK]
OOM: 0 events [OK]
File System: 0 errors [OK]
Auth Failures: 2/hour [OK]
Services: 0 failed [OK]
OVERALL: OK - No issues detected
```

**AI Decision**: All OK → Stop, no Deep mode needed

**Final Report**:
```
系统日志检查完成 - 一切正常 ✅
- 无内核错误
- 无 OOM 事件
- 无文件系统错误
- 无异常登录
- 所有服务运行正常
```

---

## 🎯 Key Takeaways

### When to Use System Log Checks
- **Daily health checks**: Run as part of morning diagnostic routine
- **After incidents**: First place to look when investigating outages
- **Before deployments**: Verify system stability
- **Performance issues**: Rule out hardware/kernel problems

### Prioritization
1. **Kernel errors** → Hardware failures (highest priority)
2. **OOM events** → Memory exhaustion
3. **Disk errors** → Data loss risk
4. **Auth failures** → Security threats
5. **Service failures** → Application unavailability

### Integration with Monitoring
- **Errors dimension** of USE Method
- **Error Rate** of Four Golden Signals
- Complements resource utilization checks

---

**Next References**: See `disk-smart.md` (predictive disk failure), `hardware-other.md` (CPU temp, RAID), `time-sync.md` (NTP sync)
