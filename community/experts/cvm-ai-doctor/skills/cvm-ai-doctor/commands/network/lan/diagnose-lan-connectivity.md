---
description: Diagnose LAN connectivity issues by pinging gateway and testing network. Supports Linux, macOS, and Windows.
tags: [network, diagnostics, connectivity, gateway, troubleshooting, cross-platform]
---

You are helping the user diagnose LAN connectivity issues.

## Platform Detection

Before running commands, detect the OS:
```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux → Linux, macOS → Darwin, Windows → MINGW*/MSYS*/CYGWIN*
```

## Process

### 1. Identify network configuration

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Show interfaces | `ip addr show` or `ifconfig` | `ifconfig` | `ipconfig /all` |
| Default gateway | `ip route show` | `netstat -rn \| grep default` | `ipconfig` (look for Default Gateway) |
| DNS servers | `cat /etc/resolv.conf` | `scutil --dns` | `ipconfig /all` (DNS Servers) |

### 2. Test gateway connectivity

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Ping gateway | `ping -c 4 <gateway-ip>` | `ping -c 4 <gateway-ip>` | `ping -n 4 <gateway-ip>` |
| If unreachable | Check interface: `ip link show` | Check interface: `ifconfig` | Check interface: `ipconfig` |
| NetworkManager | `nmcli device status` | `networksetup -listallhardwareports` | `netsh interface show interface` |

### 3. Test DNS resolution

| Action | All Platforms |
|--------|---------------|
| DNS lookup | `nslookup google.com` |
| Alternative DNS | `nslookup google.com 8.8.8.8` |
| macOS-specific | `dscacheutil -q host -a name google.com` |
| Windows-specific | `nslookup google.com 8.8.8.8` |

### 4. Test external connectivity

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Ping external IP | `ping -c 4 8.8.8.8` | `ping -c 4 8.8.8.8` | `ping -n 4 8.8.8.8` |
| Ping domain | `ping -c 4 google.com` | `ping -c 4 google.com` | `ping -n 4 google.com` |
| Traceroute | `traceroute google.com` | `traceroute google.com` or `traceroute6` | `tracert google.com` |

### 5. Check for common issues

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Firewall | `sudo ufw status` | `sudo pfctl -s info` | `netsh advfirewall show allprofiles` |
| IP conflicts | `arp -a` (look for duplicate IPs) | `arp -a` | `arp -a` |
| DHCP self-assigned | Check for 169.254.x.x in `ip addr` | Check for 169.254.x.x in `ifconfig` | Check for 169.254.x.x in `ipconfig` |
| Link state | `ip link show` (check state UP/DOWN) | `ifconfig` (check status active/inactive) | `netsh interface show interface` |

### 6. Advanced diagnostics

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Routing table | `ip route show` | `netstat -rn` | `route print` |
| Packet capture | `sudo tcpdump -i <interface> -c 20` | `sudo tcpdump -i <interface> -c 20` | `powershell "Start-NetEventSession"` or Wireshark |
| Packet loss/MTR | `mtr <gateway-ip>` | `mtr <gateway-ip>` (needs `brew install mtr`) | `pathping <gateway-ip>` |
| Connection stats | `ss -s` | `netstat -s` | `netstat -e` |
| DNS cache | `sudo systemd-resolve --flush-caches` | `sudo dscacheutil -flushcache` | `ipconfig /flushdns` |
| DNS test | `dig google.com` (needs `bind9-dnsutils`) | `dig google.com` (needs `brew install bind`) | `nslookup google.com` |

## Output

Provide a diagnostic report showing:
- Detected OS
- Network configuration summary
- Gateway reachability status
- DNS resolution status
- External connectivity status
- Identified issues (if any)
- Recommended fixes (platform-specific commands)
