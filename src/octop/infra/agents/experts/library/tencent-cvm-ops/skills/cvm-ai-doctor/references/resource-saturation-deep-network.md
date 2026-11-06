---
name: resource-saturation-deep-network
description: Deep network analysis with bandwidth and error diagnosis (20 seconds)
category: standalone-checks
mode: deep
component: network
---

# Resource Saturation Deep Analysis - Network

**Purpose**: Root cause analysis and actionable recommendations for network issues.

**Duration**: ~20 seconds

**Trigger**: Quick Mode Network = WARNING/CRITICAL OR user requests network analysis

---

## ⚡ 脚本优先路径（Script-First Path）

若 `scripts/deep_scan.sh` 存在，**优先执行脚本采集**，跳过以下手动步骤：

```bash
bash scripts/deep_scan.sh network --output json
```

脚本会自动采集网卡统计（错误/丢包）、连接饱和度（ss/netstat）、1秒带宽采样，输出结构化 JSON。
收到 JSON 后，直接跳至 **"根因推断"** 部分，用输出数据填入模板。

若脚本不存在，按以下手动步骤采集。

---

## 🔬 Deep Analysis Steps

### Step 1: Interface Statistics

**Command**:
```bash
# Linux
ip -s link show | awk '/^[0-9]+:/ {iface=$2} /RX:|TX:/ {getline; if (iface) print iface, $0; iface=""}'
```

```bash
# macOS
netstat -i -b | awk 'NR>1 {print $1 "\tRX errors:" $6 " TX errors:" $9 " Drops:" $8+$11}'
```

```powershell
# Windows
Get-NetAdapterStatistics | Select-Object Name,ReceivedBytes,SentBytes,ReceivedUnicastPackets,SentUnicastPackets,ReceivedDiscardedPackets,OutboundDiscardedPackets,ReceivedErrors,OutboundErrors | Format-Table -AutoSize
```

**AI Analysis**:
- Errors > 100 → physical layer issues
- Drops > 1000 → buffer overflow
- Overruns → NIC cannot keep up with traffic

---

### Step 2: Connection Saturation

**Command**:
```bash
# Linux
ss -s
netstat -s | grep -E "overflow|drop|failed" | head -10
```

```bash
# macOS
netstat -s | grep -E "overflow|drop|fail|retransmit" | head -15
```

```powershell
# Windows
# Connection statistics
netstat -s | Select-String -Pattern "fail|drop|error|retrans" -Context 0,1

# TCP connection state summary
Get-NetTCPConnection | Group-Object -Property State | Select-Object Count,Name | Sort-Object Count -Descending
```

**AI Analysis**:
- Listen queue overflow → accept() too slow
- Connection refused → port not listening
- Retransmits → packet loss on network

---

### Step 3: Bandwidth Utilization

**Command**:
```bash
# Linux
if command -v iftop &> /dev/null; then
  echo "Top bandwidth consumers (requires root):"
  sudo iftop -t -s 5 -n
else
  echo "iftop not installed"
  echo "Current RX/TX rates:"
  for iface in $(ip -o link show | awk -F': ' '{print $2}' | grep -v lo); do
    RX1=$(cat /sys/class/net/$iface/statistics/rx_bytes 2>/dev/null)
    TX1=$(cat /sys/class/net/$iface/statistics/tx_bytes 2>/dev/null)
    sleep 1
    RX2=$(cat /sys/class/net/$iface/statistics/rx_bytes 2>/dev/null)
    TX2=$(cat /sys/class/net/$iface/statistics/tx_bytes 2>/dev/null)
    RX_RATE=$(( (RX2 - RX1) / 1024 ))
    TX_RATE=$(( (TX2 - TX1) / 1024 ))
    echo "$iface: RX ${RX_RATE}KB/s, TX ${TX_RATE}KB/s"
  done
fi
```

```bash
# macOS
# Monitor network bandwidth for 5 seconds
nettop -t wifi -l 1 -J bytes_in,bytes_out -P 2>/dev/null | head -20
# Or use netstat
netstat -i -b -w 1 | head -10
```

```powershell
# Windows
# Monitor bandwidth for 5 seconds
$adapters = Get-NetAdapter | Where-Object {$_.Status -eq "Up"}
foreach ($adapter in $adapters) {
    $stat1 = Get-NetAdapterStatistics -Name $adapter.Name
    Start-Sleep -Seconds 1
    $stat2 = Get-NetAdapterStatistics -Name $adapter.Name
    
    $rxRate = [math]::Round(($stat2.ReceivedBytes - $stat1.ReceivedBytes) / 1KB, 2)
    $txRate = [math]::Round(($stat2.SentBytes - $stat1.SentBytes) / 1KB, 2)
    
    Write-Host "$($adapter.Name): RX ${rxRate}KB/s, TX ${txRate}KB/s"
}
```

**AI Analysis**:
- Compare rates to link capacity
- Sustained >80% utilization → bandwidth saturation
- Asymmetric RX/TX → identify direction of bottleneck

---

## 🎯 Root Cause Inference

**AI should apply the following templates**:

### Scenario 1: Listen Queue Overflow

**Conditions**:
- netstat shows listen queue overflows
- Connection refused errors
- Application accept() rate low

**Root Cause**: "Application cannot accept connections fast enough"

**Immediate Fix**:
- "Increase backlog: sysctl -w net.core.somaxconn=4096"
- "Increase app listen backlog parameter"

**Long-term Fix**:
- "Scale application horizontally (more instances)"
- "Optimize application accept() loop"

---

### Scenario 2: Physical Layer Errors

**Conditions**:
- Interface errors > 100
- Drops and overruns high
- SMART healthy

**Root Cause**: "Physical network issues (cable, NIC, switch)"

**Immediate Fix**:
- "Check cable connections"
- "Test with different cable"

**Long-term Fix**:
- "Replace faulty cable/NIC"
- "Check switch port health"

---

### Scenario 3: Bandwidth Saturation

**Conditions**:
- Utilization > 80% sustained
- Packet drops increasing
- No errors

**Root Cause**: "Network bandwidth exceeded"

**Immediate Fix**:
- "Identify top bandwidth consumers"
- "Rate-limit non-critical traffic"

**Long-term Fix**:
- "Upgrade link capacity (1G → 10G)"
- "Implement QoS/traffic shaping"
- "Offload traffic to separate network"

---

### Scenario 4: TCP Retransmits

**Conditions**:
- High retransmit count in netstat -s
- Normal interface statistics
- Intermittent connectivity

**Root Cause**: "Packet loss in network path"

**Immediate Fix**:
- "Test path: mtr <destination>"
- "Check for congestion at router/ISP"

**Long-term Fix**:
- "Contact ISP if external issue"
- "Tune TCP parameters (window scaling)"

---

## 📋 Output Template

**AI should generate**:

```json
{
  "mode": "deep",
  "component": "network",
  "duration": "20s",
  "root_cause": "<inferred cause>",
  "evidence": [
    "eth0: 1,234 packet drops",
    "netstat: 567 listen overflows",
    "Application: nginx"
  ],
  "immediate_fix": [
    "sysctl -w net.core.somaxconn=4096"
  ],
  "long_term_fix": [
    "Scale nginx horizontally",
    "Optimize worker_connections",
    "Add load balancer"
  ]
}
```

**Human-friendly format**:

```
🔬 Deep Network Analysis (20s)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 Root Cause: Listen Queue Overflow
   nginx cannot accept connections fast enough

📊 Evidence:
   • Interface: eth0
   • Packet Drops: 1,234
   • Listen Overflows: 567 (netstat)
   • Application: nginx

⚡ Immediate Fix:
   sudo sysctl -w net.core.somaxconn=4096

🔧 Long-term Fix:
   1. Scale nginx horizontally (add instances)
   2. Increase worker_connections in config
   3. Add load balancer
```

---

## 🔗 Related Checks

**After Network analysis, consider**:
- If firewall suspected → Check iptables/nftables rules
- If DNS issues → Run `time-sync.md` (DNS resolution sensitive to time)
- If application errors → Check application-specific logs

---

**Last Updated**: 2026-03-25
**Compatibility**: Linux, macOS, Windows (full support)
**Dependencies**: ip/ifconfig, ss/netstat (standard), iftop (optional for Linux), nettop (macOS), Get-NetAdapter (Windows)
**Token Estimate**: ~600 tokens

---

---

> 📊 分析完成后静默执行: `bash scripts/log_stats.sh deep network_issue <os> 0 skipped skipped skipped <severity> user`
