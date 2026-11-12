---
name: time-synchronization-check
description: Verify NTP/chrony synchronization status - critical for distributed systems and log correlation
category: standalone-checks
---

# Time Synchronization Check

**Purpose**: Ensure system clocks are accurately synchronized - critical for distributed systems, log correlation, and security protocols.

**Why critical**: Time drift breaks authentication (Kerberos), distributed transactions, log analysis, and scheduled tasks.

**SRE best practice**: Time drift is a "silent killer" - rarely monitored but causes cascading failures.

---

## 🎯 AI Usage Guide

### Quick/Deep Workflow

```mermaid
User Question → Quick Mode (5s) → Analyze → Deep Mode (10-15s, if issues)
```

**When to use each mode**:

| Mode | Duration | Purpose | When to Use |
|------|----------|---------|-------------|
| **Quick** | 5s | Check if NTP is enabled and synced | Health check, "检查时间", daily routine |
| **Deep** | 10-15s | Detailed offset analysis + troubleshooting | Quick shows not synced, time drift issues |

**Decision Logic**:
```yaml
Quick Mode Results:
  - NTP active AND synced → Stop, report healthy
  - NTP inactive → Deep Mode: diagnose why
  - NTP active but not synced → Deep Mode: check offset/connectivity
  
Deep Mode Focus:
  - Measure clock offset (current drift)
  - Check NTP server reachability
  - Verify firewall/network connectivity
  - Diagnose configuration issues
```

**Output Format**:

```yaml
# Quick Mode
ntp_service: active | inactive
clock_synced: yes | no
status: OK | WARNING | CRITICAL
summary: "One-line result"

# Deep Mode
ntp_service: active | inactive
clock_synced: yes | no
clock_offset: N seconds (if available)
ntp_servers: ["server1", "server2"]
reachable_servers: N
root_cause: "Identified issue"
impact: ["impact 1", "impact 2"]
recommendation: ["action 1", "action 2"]
```

---

## ⚡ Quick Mode (5s)

**Purpose**: Verify NTP service status and sync state

---

### Check NTP Service and Sync Status

```bash
# Linux (systemd-timesyncd)
if command -v timedatectl &>/dev/null; then
  NTP_SERVICE=$(timedatectl status 2>/dev/null | grep "NTP service" | awk '{print $3}')
  CLOCK_SYNCED=$(timedatectl status 2>/dev/null | grep "System clock synchronized" | awk '{print $4}')
  
  echo "NTP Service: $NTP_SERVICE"
  echo "Clock Synced: $CLOCK_SYNCED"
  
  if [ "$CLOCK_SYNCED" = "yes" ] && [ "$NTP_SERVICE" = "active" ]; then
    echo "Status: OK"
  elif [ "$NTP_SERVICE" = "inactive" ]; then
    echo "Status: CRITICAL - NTP disabled"
  else
    echo "Status: WARNING - NTP enabled but not synced"
  fi
fi

# Alternative: chronyd
if command -v chronyc &>/dev/null; then
  CHRONY_TRACKING=$(chronyc tracking 2>/dev/null)
  if echo "$CHRONY_TRACKING" | grep -q "Leap status.*Normal"; then
    echo "Chrony: Synchronized [OK]"
  else
    echo "Chrony: Not synchronized [WARNING]"
  fi
fi
```

```bash
# macOS
NTP_STATUS=$(systemsetup -getusingnetworktime 2>/dev/null | awk -F': ' '{print $2}')

if [ "$NTP_STATUS" = "On" ]; then
  echo "Network Time: On [OK]"
else
  echo "Network Time: Off [CRITICAL]"
fi
```

```powershell
# Windows
$w32tmStatus = w32tm /query /status 2>&1

if ($w32tmStatus -match "Source:.*\.") {
  Write-Host "Time Service: Synchronized [OK]"
} else {
  Write-Host "Time Service: Not synchronized [CRITICAL]"
}
```

**Thresholds**:
```yaml
CRITICAL: NTP disabled or no sync for >24h
WARNING: NTP enabled but not currently synced
OK: Active synchronization
```

**AI Instructions for Quick Mode**:
1. Execute commands
2. Parse NTP service status and sync state
3. Decision logic:
   - Both OK → Report healthy, stop
   - NTP inactive → Deep Mode (why disabled?)
   - Not synced → Deep Mode (check offset/connectivity)

---

## 🔬 Deep Mode (10-15s)

**Purpose**: Diagnose time sync issues + measure drift

---

### Deep Mode: NTP Synchronization Analysis

```bash
#!/bin/bash
echo "========================================="
echo " Time Synchronization Deep Analysis"
echo "========================================="

# 1. Service Status
echo -e "\n[1/5] NTP Service Status"
if command -v timedatectl &>/dev/null; then
  timedatectl status | grep -E "NTP|synchronized|Time zone"
elif command -v chronyc &>/dev/null; then
  if systemctl is-active chronyd &>/dev/null; then
    echo "Chronyd: Active"
  else
    echo "Chronyd: Inactive"
  fi
else
  echo "⚠️  No NTP service detected (ntpd, chronyd, or systemd-timesyncd)"
fi

# 2. Clock Offset
echo -e "\n[2/5] Clock Offset Measurement"
if command -v chronyc &>/dev/null; then
  OFFSET=$(chronyc tracking 2>/dev/null | awk '/Last offset/ {print $4}')
  if [ -n "$OFFSET" ]; then
    echo "Current offset: ${OFFSET}s"
    
    # Convert to absolute value for threshold check
    ABS_OFFSET=$(echo "$OFFSET" | awk '{print ($1<0)?-$1:$1}')
    
    if command -v bc &>/dev/null; then
      if (( $(echo "$ABS_OFFSET > 5.0" | bc -l) )); then
        echo "🔴 CRITICAL - Offset > 5 seconds (Kerberos/TLS will fail)"
      elif (( $(echo "$ABS_OFFSET > 1.0" | bc -l) )); then
        echo "⚠️  WARNING - Offset > 1 second"
      else
        echo "✅ Offset within tolerance (<1s)"
      fi
    fi
  else
    echo "Unable to determine offset"
  fi
elif command -v ntpq &>/dev/null; then
  OFFSET_MS=$(ntpq -c rv 2>/dev/null | grep -oP 'offset=\K[0-9.-]+')
  if [ -n "$OFFSET_MS" ]; then
    OFFSET_S=$(echo "scale=3; $OFFSET_MS / 1000" | bc 2>/dev/null)
    echo "NTP offset: ${OFFSET_S}s (${OFFSET_MS}ms)"
  fi
else
  # Manual check via HTTP
  echo "Attempting manual offset check..."
  EXTERNAL_TIME=$(curl -sI https://www.google.com 2>/dev/null | grep "^Date:" | sed 's/Date: //')
  if [ -n "$EXTERNAL_TIME" ]; then
    EXTERNAL_EPOCH=$(date -d "$EXTERNAL_TIME" +%s 2>/dev/null || date -j -f "%a, %d %b %Y %T %Z" "$EXTERNAL_TIME" +%s 2>/dev/null)
    LOCAL_EPOCH=$(date +%s)
    
    if [ -n "$EXTERNAL_EPOCH" ]; then
      OFFSET=$((LOCAL_EPOCH - EXTERNAL_EPOCH))
      echo "Offset vs Google: ${OFFSET}s"
      
      if [ "${OFFSET#-}" -gt 5 ]; then
        echo "🔴 CRITICAL - Significant drift detected"
      elif [ "${OFFSET#-}" -gt 1 ]; then
        echo "⚠️  WARNING - Minor drift detected"
      else
        echo "✅ Time appears accurate"
      fi
    fi
  else
    echo "ℹ️  Unable to check offset (no internet or NTP daemon)"
  fi
fi

# 3. NTP Server Configuration
echo -e "\n[3/5] NTP Server Configuration"
if [ -f /etc/chrony/chrony.conf ]; then
  echo "Configured servers (chrony):"
  grep "^server\|^pool" /etc/chrony/chrony.conf | head -5
elif [ -f /etc/ntp.conf ]; then
  echo "Configured servers (ntp):"
  grep "^server" /etc/ntp.conf | head -5
elif command -v timedatectl &>/dev/null; then
  echo "Using systemd-timesyncd"
  grep "^NTP=" /etc/systemd/timesyncd.conf 2>/dev/null || echo "Using default servers"
else
  echo "ℹ️  Unable to determine configured servers"
fi

# 4. NTP Server Reachability
echo -e "\n[4/5] NTP Server Reachability"
if command -v chronyc &>/dev/null; then
  echo "Chrony sources:"
  chronyc sources 2>/dev/null
  
  REACHABLE=$(chronyc sources 2>/dev/null | grep -c "^\^\*\|^\^+")
  echo ""
  if [ "$REACHABLE" -eq 0 ]; then
    echo "🔴 CRITICAL - No reachable NTP sources"
  else
    echo "✅ $REACHABLE NTP source(s) reachable"
  fi
elif command -v ntpq &>/dev/null; then
  echo "NTP peers:"
  ntpq -p 2>/dev/null
  
  SYNCED=$(ntpq -p 2>/dev/null | grep -c "^\*")
  echo ""
  if [ "$SYNCED" -eq 0 ]; then
    echo "⚠️  WARNING - No synced peer"
  else
    echo "✅ Synced with NTP peer"
  fi
else
  echo "Testing connectivity to public NTP servers..."
  NTP_SERVERS=("time.google.com" "pool.ntp.org" "time.cloudflare.com")
  
  for server in "${NTP_SERVERS[@]}"; do
    if timeout 3 bash -c "echo > /dev/udp/$server/123" 2>/dev/null; then
      echo "✅ $server - Reachable"
    else
      echo "❌ $server - Unreachable"
    fi
  done
fi

# 5. Timezone & RTC
echo -e "\n[5/5] Timezone and Hardware Clock"
if command -v timedatectl &>/dev/null; then
  TIMEZONE=$(timedatectl status 2>/dev/null | awk '/Time zone:/ {print $3}')
  RTC_LOCAL=$(timedatectl status 2>/dev/null | grep "RTC in local TZ" | awk '{print $5}')
  
  echo "Timezone: $TIMEZONE"
  
  if [ "$RTC_LOCAL" = "yes" ]; then
    echo "⚠️  WARNING - RTC in local time (should be UTC)"
  else
    echo "✅ RTC in UTC (correct)"
  fi
else
  TIMEZONE=$(cat /etc/timezone 2>/dev/null || echo "Unknown")
  echo "Timezone: $TIMEZONE"
fi

echo ""
echo "========================================="
echo " Diagnosis & Recommendations"
echo "========================================="
```

**AI Instructions for Deep Mode**:
1. Run the script
2. Extract key values:
   - NTP service status
   - Clock offset
   - Number of reachable servers
   - RTC configuration
3. Apply Root Cause Inference patterns
4. Generate actionable report

---

### Root Cause Inference Patterns

**Pattern 1: NTP Service Disabled**
```yaml
Evidence:
  - NTP service: inactive
  - Clock synced: no
Root Cause: "NTP service not enabled or not running"
Impact:
  - "Clock will drift over time"
  - "Log timestamps become unreliable"
  - "Distributed system consensus will break"
  - "Kerberos authentication will fail (>5min drift)"
Recommendation:
  - "Enable NTP immediately"
  - "Linux: timedatectl set-ntp true"
  - "Or install chronyd: apt-get install chrony && systemctl enable chronyd"
  - "Verify sync: timedatectl status"
```

**Pattern 2: Large Clock Offset (>5 seconds)**
```yaml
Evidence:
  - NTP service: active
  - Clock synced: yes/no
  - Offset: > 5 seconds
Root Cause: "Significant time drift, NTP unable to sync gradually"
Impact:
  - "🔴 CRITICAL - Authentication failures (Kerberos)"
  - "SSL certificate validation errors"
  - "Distributed transaction failures"
  - "Log correlation impossible"
Recommendation:
  - "Force immediate time step (breaks gradual sync rules)"
  - "Chronyd: chronyc makestep"
  - "Ntpd: ntpd -gq (force step)"
  - "Systemd-timesyncd: timedatectl set-ntp false && timedatectl set-ntp true"
  - "Check NTP server connectivity"
  - "Investigate why drift occurred (RTC battery?)"
```

**Pattern 3: No Reachable NTP Servers**
```yaml
Evidence:
  - NTP service: active
  - Clock synced: no
  - Reachable servers: 0
Root Cause: "Network/firewall blocking NTP traffic"
Impact:
  - "Clock will drift"
  - "NTP running but ineffective"
Recommendation:
  - "Check firewall: iptables -L -n | grep 123"
  - "Allow NTP outbound: ufw allow out 123/udp"
  - "Test connectivity: nc -vzu time.google.com 123"
  - "Try alternative servers: pool.ntp.org, time.cloudflare.com"
  - "If corporate network: use internal NTP servers"
  - "Check if HTTP proxy required (rare for NTP)"
```

**Pattern 4: RTC in Local Time (Windows Dual Boot Issue)**
```yaml
Evidence:
  - NTP synced
  - RTC in local TZ: yes
  - Timezone configured correctly
Root Cause: "Hardware clock set to local time instead of UTC"
Impact:
  - "Daylight Saving Time changes cause time jumps"
  - "Dual-boot systems have time conflicts"
  - "Time zone changes cause incorrect time"
Recommendation:
  - "Set RTC to UTC: timedatectl set-local-rtc 0"
  - "If dual-boot with Windows: configure Windows to use UTC"
  - "  Windows Registry: HKLM\\SYSTEM\\CurrentControlSet\\Control\\TimeZoneInformation"
  - "  Set RealTimeIsUniversal = 1 (DWORD)"
```

**Pattern 5: Moderate Drift (<5s) But Not Syncing**
```yaml
Evidence:
  - NTP service: active
  - Clock synced: no
  - Offset: 1-5 seconds
  - Some servers reachable
Root Cause: "NTP struggling to sync (network latency, packet loss)"
Impact:
  - "Gradual drift"
  - "May cause issues if reaches >5s"
Recommendation:
  - "Check network latency: ping <ntp_server>"
  - "Use geographically closer NTP servers"
  - "Verify no packet loss: mtr <ntp_server>"
  - "Increase polling interval if needed"
  - "If persistent: force step (see Pattern 2)"
```

**Pattern 6: Everything Healthy**
```yaml
Evidence:
  - NTP service: active
  - Clock synced: yes
  - Offset: < 1 second
  - Servers reachable: > 0
  - RTC in UTC
Root Cause: "Time synchronization healthy"
Impact: "None - system operating correctly"
Recommendation:
  - "✅ No action required"
  - "Continue quarterly checks"
  - "Monitor for offset trends"
```

---

## 💡 Complete Usage Examples

### Example 1: User Reports "Kerberos 认证失败"

**Step 1: Quick Mode**
```
NTP Service: active
Clock Synced: yes
Status: WARNING - NTP enabled but not synced
```

**AI Decision**: Not synced → Deep Mode

**Step 2: Deep Mode**
```
[1/5] NTP Service: Active
[2/5] Offset: 8.3 seconds
[3/5] Servers: time.google.com, pool.ntp.org
[4/5] Reachable: 2 servers
[5/5] RTC: UTC (correct)
```

**AI Inference**: Pattern 2 (Large Offset >5s)

**Final Report**:
```
🔴 时间严重偏移 - Kerberos 失败原因找到

检测结果：
- NTP 服务：运行中
- 时间偏移：8.3 秒（超过 Kerberos 5 秒阈值）
- NTP 服务器：可达（2 个）

根因：时间漂移超过 5 秒，Kerberos 拒绝认证

影响：
- 🔴 Kerberos 认证失败（>5 秒阈值）
- SSL 证书验证可能失败
- 分布式事务错误
- 日志时间戳不可靠

立即修复：
1. 强制时间同步：
   sudo chronyc makestep
   
2. 验证修复：
   timedatectl status
   # 应显示 "System clock synchronized: yes"
   
3. 测试 Kerberos：
   kinit <username>
   
4. 后续排查：
   - 为什么时间漂移如此严重？
   - 检查硬件时钟（RTC）电池
   - 检查 NTP 日志：journalctl -u chronyd
```

---

### Example 2: User Asks "检查时间同步"

**Step 1: Quick Mode**
```
NTP Service: inactive
Clock Synced: no
Status: CRITICAL - NTP disabled
```

**AI Decision**: NTP disabled → Deep Mode

**Step 2: Deep Mode**
```
[1/5] No NTP service detected
[2/5] Offset check via HTTP: +127 seconds
[4/5] Manual connectivity test:
  time.google.com: Reachable
  pool.ntp.org: Reachable
```

**AI Inference**: Pattern 1 (NTP Disabled)

**Final Report**:
```
🔴 NTP 未启用 - 时间正在漂移

检测结果：
- NTP 服务：未运行
- 当前偏移：+127 秒（相对于标准时间）
- 网络：NTP 服务器可达

根因：系统未配置时间同步服务

影响：
- 时间持续漂移（已偏移 127 秒）
- 日志时间戳错误
- 定时任务可能异常
- 分布式系统将出现一致性问题

立即修复：
1. 启用 NTP：
   sudo timedatectl set-ntp true
   
2. 如果失败，安装 chrony：
   sudo apt-get install -y chrony
   sudo systemctl enable chronyd
   sudo systemctl start chronyd
   
3. 强制立即同步：
   sudo chronyc makestep
   
4. 验证：
   timedatectl status
   # 应显示：
   # NTP service: active
   # System clock synchronized: yes
   
预期结果：时间将在 1 分钟内同步到准确值
```

---

### Example 3: Health Check (All OK)

**Step 1: Quick Mode**
```
NTP Service: active
Clock Synced: yes
Status: OK
```

**AI Decision**: All OK → Optional brief Deep check

**Optional Step 2: Quick Deep Summary**
```bash
chronyc tracking | grep "Last offset"
# Output: Last offset : +0.000234 seconds
```

**Final Report**:
```
时间同步检查 - 一切正常 ✅

状态：
- NTP 服务：运行中
- 时钟已同步：是
- 当前偏移：+0.0002 秒（几乎完美）
- NTP 服务器：可达

结论：时间同步健康，无需采取行动
建议：继续定期检查（每季度）
```

---

### Example 4: User Reports "日志时间不对"

**Step 1: Quick Mode**
```
NTP Service: active
Clock Synced: yes
Status: OK
```

**AI Note**: NTP OK but user says logs wrong → Check timezone

**Step 2: Timezone-Focused Deep**
```bash
timedatectl status
# Output:
# Local time: Wed 2024-03-20 14:30:00 EST
# Universal time: Wed 2024-03-20 19:30:00 UTC
# Time zone: America/New_York (EST, -0500)
# NTP service: active
# System clock synchronized: yes
# RTC in local TZ: yes  ← PROBLEM!
```

**AI Inference**: Pattern 4 (RTC in Local Time)

**Final Report**:
```
⚠️  时区配置问题（非时间同步问题）

检测结果：
- NTP 同步：正常
- 时间偏移：< 1 秒
- 问题：硬件时钟设置为本地时间（应为 UTC）

根因：RTC (硬件时钟) 配置错误

影响：
- 夏令时切换时，时间会跳变
- 双系统（如 Windows）时间冲突
- 更改时区时，时间会错误

修复：
1. 设置 RTC 为 UTC：
   sudo timedatectl set-local-rtc 0
   
2. 验证：
   timedatectl status
   # 应显示 "RTC in local TZ: no"
   
3. 如果双系统（Windows + Linux）：
   - 在 Windows 中配置使用 UTC
   - 运行（管理员命令提示符）：
     reg add "HKLM\System\CurrentControlSet\Control\TimeZoneInformation" /v RealTimeIsUniversal /d 1 /t REG_DWORD /f

注意：此修复不会影响当前时间，但防止未来问题
```

---

## 🎯 Key Takeaways

### Why Time Sync Matters
1. **5-second threshold**: Kerberos and many security protocols fail
2. **Distributed systems**: Consensus protocols depend on time
3. **Log correlation**: Impossible without synchronized clocks
4. **Financial systems**: Require millisecond-level accuracy

### Common Issues
- **NTP disabled** → Enable immediately (most common)
- **Firewall blocks UDP 123** → Allow NTP traffic
- **Large drift** → Force time step
- **RTC in local time** → Set to UTC

### Monitoring
- **Critical systems**: Check daily
- **Standard systems**: Check monthly
- **Set alerts**: Offset > 1 second

### Real-World Failures
- **AWS outage (2020)**: Clock drift caused Kinesis failures
- **Google Spanner**: Uses atomic clocks for consistency
- **Financial trading**: Millisecond accuracy required by regulation

---

**Integration**: Time sync issues often correlate with:
- `system-logs.md` (auth failures, service errors)
- `resource-saturation.md` (if time jumps cause load spikes)

**Tools Required**:
- Linux: `timedatectl`, `chrony` or `ntpd`
- macOS: `systemsetup`, built-in NTP
- Windows: `w32tm` (built-in)
