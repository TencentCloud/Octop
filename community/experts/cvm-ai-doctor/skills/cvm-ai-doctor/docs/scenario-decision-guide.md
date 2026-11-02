# Scenario Decision Guide

**Purpose**: Extended scenario library with 60+ diagnostic scenarios.  
**Usage**: Fallback reference when SKILL.md's built-in scenarios don't match.

---

## How to Use This Guide

1. **Try SKILL.md first** - It covers 80% of common cases
2. **If no match**, search this file for relevant keywords
3. **Follow the workflow** specified for that scenario

---

## Performance Issues

### 服务器慢/卡 (System Slow)
```yaml
Keywords: [慢, 卡, slow, lag, sluggish, 响应慢, latency]
Workflow:
  step1: Read resource-saturation-quick.md
  step2: Execute Quick checks (10s)
  step3: Based on results, conditionally read Deep modules:
    - If CPU = WARNING/CRITICAL → resource-saturation-deep-cpu.md
    - If Memory = WARNING/CRITICAL → resource-saturation-deep-memory.md
    - If Disk = WARNING/CRITICAL → resource-saturation-deep-disk.md
    - If Network = WARNING/CRITICAL → resource-saturation-deep-network.md
Reason: Quick triage identifies bottleneck, then Deep analysis on specific component
```

### CPU 高 (High CPU)
```yaml
Keywords: [CPU, cpu高, CPU 100%, 进程卡死, high cpu]
Workflow:
  step1: Skip Quick, go directly to:
    - resource-saturation-deep-cpu.md
Reason: User already identified CPU as bottleneck
```

### 内存不足 (Memory Issues)
```yaml
Keywords: [内存, memory, OOM, swap, 内存满, out of memory]
Workflow:
  step1: Skip Quick if issue is clear
  step2: Read resource-saturation-deep-memory.md
Reason: Focus on memory component only
```

### 磁盘问题 (Disk Issues)
```yaml
Keywords: [磁盘, disk, 磁盘满, disk full, 磁盘慢, I/O slow]
Workflow:
  step1: Determine if "full" or "slow"
  step2a: If "full" → Direct commands (du, df)
  step2b: If "slow" → resource-saturation-quick.md, then resource-saturation-deep-disk.md
Reason: Disk full needs space check, disk slow needs I/O analysis
```

### 网络慢 (Network Issues)
```yaml
Keywords: [网络, network, 网络慢, network slow, 丢包, packet loss]
Workflow:
  step1: Read resource-saturation-quick.md
  step2: If network issue confirmed → resource-saturation-deep-network.md
Reason: Network diagnostics need baseline first
```

---

## System Errors

### 健康检查 (Health Check)
```yaml
Keywords: [检查, 健康, health, check, 体检]
Workflow:
  step1: Read resource-saturation-quick.md
  step2: Read system-logs-quick.md
  step3: If all OK → Stop (no Deep needed)
Reason: Health check only needs Quick scan
```

### 崩溃/错误 (Crash/Errors)
```yaml
Keywords: [崩溃, crash, 错误, error, 异常, exception, killed, panic]
Workflow:
  step1: Read system-logs-quick.md
  step2: Based on results, conditionally read:
    - If kernel errors → system-logs-deep-kernel.md
    - If OOM events → system-logs-deep-oom.md
    - If FS errors → system-logs-deep-fs.md
    - If auth failures → system-logs-deep-auth.md
    - If service failures → system-logs-deep-service.md
Reason: Quick error count identifies problem categories, then Deep analysis
```

### OOM 问题 (OOM Killer)
```yaml
Keywords: [OOM, Out of Memory, killed process, 内存杀手, oom killer]
Workflow:
  step1: Skip system-logs-quick.md
  step2: Read system-logs-deep-oom.md directly
Reason: OOM explicitly mentioned, direct to Deep analysis
```

### Kernel Panic/Crash
```yaml
Keywords: [kernel panic, kernel crash, 内核崩溃, kernel oops]
Workflow:
  step1: Skip Quick
  step2: Read system-logs-deep-kernel.md
Reason: Critical issue, immediate Deep analysis needed
```

### 认证失败 (Auth Failures)
```yaml
Keywords: [认证, authentication, SSH, 登录失败, login failed, brute force]
Workflow:
  step1: Skip system-logs-quick.md
  step2: Read system-logs-deep-auth.md directly
Reason: Auth issues need immediate analysis
```

### 文件系统错误 (Filesystem Errors)
```yaml
Keywords: [文件系统, filesystem, fs error, read-only, 只读, I/O error]
Workflow:
  step1: Skip Quick
  step2: Read system-logs-deep-fs.md
Reason: FS errors are critical, direct Deep analysis
```

### 服务失败 (Service Failures)
```yaml
Keywords: [服务, service, systemd, 服务启动失败, service failed]
Workflow:
  step1: system-logs-quick.md (check if systemic)
  step2: If service-specific → system-logs-deep-service.md
Reason: Differentiate between systemic vs. single service issue
```

---

## Hardware Issues

### 磁盘健康 (Disk Health)
```yaml
Keywords: [磁盘健康, disk health, SMART, 坏道, bad sector]
Workflow:
  step1: Read disk-smart-quick.md (10s check)
  step2: If any disk = FAILED or UNKNOWN → disk-smart-deep.md
Reason: Quick health check sufficient if all PASSED
```

### 磁盘故障 (Disk Failure)
```yaml
Keywords: [磁盘故障, disk failure, 磁盘坏了, FAILED, disk failed]
Workflow:
  step1: Skip disk-smart-quick.md
  step2: Read disk-smart-deep.md directly
Reason: Explicit failure mentioned, detailed SMART analysis needed
```

### 硬件问题 (Hardware Issues)
```yaml
Keywords: [硬件, hardware, 温度, temperature, hot, 过热, overheating]
Workflow:
  step1: Read hardware-health-quick.md
  step2: If issues found → hardware-health-deep.md
Reason: Quick hardware health scan across all components
```

### CPU 过热 (CPU Overheating)
```yaml
Keywords: [CPU温度, CPU过热, CPU hot, CPU temperature, throttling]
Workflow:
  step1: Skip Quick
  step2: Read hardware-health-deep.md (focus: CPU temperature)
Reason: Temperature issues need immediate deep analysis
```

### 内存硬件故障 (Memory Hardware)
```yaml
Keywords: [内存故障, memory error, ECC, memory hardware, 坏内存]
Workflow:
  step1: Skip Quick
  step2: Read hardware-health-deep.md (focus: ECC errors)
Reason: Hardware memory errors need detailed analysis
```

### RAID 问题 (RAID Issues)
```yaml
Keywords: [RAID, raid degraded, 阵列, array, 硬盘阵列]
Workflow:
  step1: Read hardware-health-quick.md
  step2: If RAID degraded → hardware-health-deep.md
Reason: RAID issues need component-level analysis
```

---

## Time & Clock

### 时间问题 (Time Issues)
```yaml
Keywords: [时间, time, NTP, ntp, 时钟, clock, 时间不对]
Workflow:
  step1: Read time-sync.md (Quick section)
  step2: If not synced → time-sync.md (Deep section)
Reason: Quick NTP sync check, then Deep if issues
```

### 时间偏移 (Time Drift)
```yaml
Keywords: [时间偏移, time drift, clock offset, Kerberos失败]
Workflow:
  step1: Skip Quick
  step2: Read time-sync.md (Deep section)
Reason: Time drift explicitly mentioned, immediate Deep analysis
```

### Kerberos 认证失败 (Kerberos Auth)
```yaml
Keywords: [Kerberos, kerberos失败, clock skew]
Workflow:
  step1: Read time-sync.md (check time first)
  step2: If time OK → system-logs-deep-auth.md
Reason: Kerberos failures often caused by time drift (>5s threshold)
```

---

## Low-Frequency Scenarios

### 系统启动慢 (Slow Boot)
```yaml
Keywords: [启动慢, slow boot, boot time, systemd-analyze]
Workflow:
  - Run: systemd-analyze blame
  - Identify slow services
  - Check: system-logs-deep-service.md for service issues
```

### 进程僵尸 (Zombie Processes)
```yaml
Keywords: [僵尸进程, zombie, defunct, Z state]
Workflow:
  - Run: ps aux | grep defunct
  - Identify parent process
  - Check if parent is hung (resource-saturation-deep-cpu.md)
```

### 负载高但 CPU 低 (High Load, Low CPU)
```yaml
Keywords: [load average high, cpu not high, 负载高 CPU低]
Workflow:
  - Read: resource-saturation-quick.md
  - Focus on: Disk I/O wait, Network wait
  - Deep: resource-saturation-deep-disk.md or deep-network.md
Reason: High load with low CPU indicates I/O or network bottleneck
```

### 上下文切换过多 (High Context Switches)
```yaml
Keywords: [context switch, 上下文切换, cs rate]
Workflow:
  - Read: resource-saturation-deep-cpu.md
  - Focus on: vmstat cs column, process scheduling
```

### 文件描述符耗尽 (File Descriptor Exhaustion)
```yaml
Keywords: [too many open files, 文件描述符, ulimit, fd limit]
Workflow:
  - Check: lsof -p <pid> | wc -l
  - Check: ulimit -n
  - Deep: system-logs-deep-service.md (if service-related)
```

---

## Usage Tips

### For AI Agents

1. **Start with SKILL.md** - Don't read this file unless needed
2. **Match keywords precisely** - Use exact keyword matching
3. **Follow workflow strictly** - Don't skip steps unless specified
4. **Combine scenarios** - Some issues need multiple checks

### When to Use This File

- ✅ Built-in scenarios in SKILL.md don't match
- ✅ User mentions specific technical terms (Kerberos, RAID, ECC)
- ✅ Low-frequency issues (zombie processes, fd exhaustion)
- ❌ Common issues (慢, CPU高, 内存不足) - Use SKILL.md instead

---

**Last Updated**: 2026-03-24  
**Maintainer**: AI diagnostics team  
**Related**: See SKILL.md for core scenarios, commands/ for action commands
