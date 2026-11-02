# Diagnose Network Issues

You are helping the user diagnose network connectivity and performance problems.

## Platform Detection

```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux → Linux, macOS → Darwin, Windows → MINGW*/MSYS*/CYGWIN*
```

## Step 1: Basic Connectivity Check

| Check | Linux | macOS | Windows |
|-------|-------|-------|---------|
| Interface status | `ip link show` | `ifconfig` | `ipconfig /all` |
| IP address | `ip addr show` | `ifconfig` | `ipconfig` |
| Default gateway | `ip route show default` | `netstat -rn \| grep default` | `route print 0.0.0.0` |
| Ping gateway | `ping -c 4 $(ip route \| awk '/default/ {print $3}')` | `ping -c 4 $(netstat -rn \| awk '/default/ {print $2}' \| head -1)` | `ping $(route print \| findstr 0.0.0.0 \| awk '{print $3}' \| head -1)` |
| DNS resolution | `nslookup google.com` | `nslookup google.com` | `nslookup google.com` |
| Internet reachability | `curl -sI https://www.baidu.com \| head -1` | `curl -sI https://www.baidu.com \| head -1` | `Invoke-WebRequest -Uri https://www.baidu.com -UseBasicParsing \| Select StatusCode` |

## Step 2: Network Performance

| Check | Linux | macOS | Windows |
|-------|-------|-------|---------|
| Packet loss & latency | `ping -c 20 8.8.8.8` | `ping -c 20 8.8.8.8` | `ping -n 20 8.8.8.8` |
| Route path | `traceroute 8.8.8.8` or `mtr --report 8.8.8.8` | `traceroute 8.8.8.8` | `tracert 8.8.8.8` |
| Interface stats (errors/drops) | `ip -s link` | `netstat -i -b` | `Get-NetAdapterStatistics` |
| Active connections | `ss -tnp` | `netstat -an` | `netstat -an` |

## Step 3: Cloud / VM Environment Checks

For CVM / cloud server network issues, also check:

```bash
# 1. Verify service is actually listening on the expected port
ss -tlnp | grep <port>

# 2. Check local firewall rules
iptables -L -n --line-numbers 2>/dev/null
# or (newer systems)
nft list ruleset 2>/dev/null

# 3. Test external reachability from the machine itself
curl -v telnet://<target_ip>:<port> 2>&1 | head -5
curl -sI http://<target_ip>:<port>

# 4. Check routing table for unexpected routes
ip route show

# 5. Verify DNS is working correctly
dig +short <hostname>
```

**AI Analysis**:
- If ping to gateway fails → local network/NIC issue
- If gateway OK but internet fails → ISP / security group / firewall blocking outbound
- If service listening but externally unreachable → security group or iptables blocking inbound
- If high packet loss in traceroute → congestion or routing issue at that hop
- If DNS fails but IP works → DNS server issue (`/etc/resolv.conf` misconfigured)

## Step 4: Bandwidth Measurement (if performance is the issue)

```bash
# Linux — measure current interface throughput (no extra tools needed)
IFACE=$(ip route show default | awk '{print $5}' | head -1)
RX1=$(cat /sys/class/net/$IFACE/statistics/rx_bytes)
TX1=$(cat /sys/class/net/$IFACE/statistics/tx_bytes)
sleep 2
RX2=$(cat /sys/class/net/$IFACE/statistics/rx_bytes)
TX2=$(cat /sys/class/net/$IFACE/statistics/tx_bytes)
echo "RX: $(( (RX2-RX1)/2/1024 )) KB/s  TX: $(( (TX2-TX1)/2/1024 )) KB/s"
```

## Common Root Causes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Can't reach internet, gateway OK | Security group / firewall blocking outbound | Check cloud console security group rules |
| Service unreachable from outside | Inbound port blocked | Open port in security group / `ufw allow <port>` |
| Intermittent packet loss | Network congestion or faulty NIC/cable | Check interface errors with `ip -s link` |
| Slow DNS only | Wrong DNS server | Fix `/etc/resolv.conf` or use `8.8.8.8` |
| All traffic slow | Bandwidth saturation | Identify top consumers with `iftop` or `nethogs` |

**Last Updated**: 2026-04-02
**Compatibility**: Linux (full), macOS (full), Windows (partial)
