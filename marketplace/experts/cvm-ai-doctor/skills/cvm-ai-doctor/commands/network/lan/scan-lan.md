---
description: Scan local network using ARP and produce a LAN map
tags: [network, diagnostics, lan, arp, scanning, project, gitignored]
---

You are helping the user scan their local network and create a comprehensive LAN map.

## Process

1. **Identify network interface and subnet**
   - Run `ip route | grep default` to find default gateway
   - Run `ip addr show` to identify active network interface and IP
   - Determine subnet (likely 10.0.0.0/24 based on Daniel's setup)

2. **Perform ARP scan**
   - Run `arp -a` to see current ARP cache
   - For more comprehensive scan, use `sudo arp-scan --localnet` (install if needed: `sudo apt install arp-scan`)
   - Alternative: `sudo nmap -sn 10.0.0.0/24` for network sweep

3. **Gather detailed information**
   - For each discovered host, attempt to:
     - Get hostname: `nslookup <IP>`
     - Identify device type if possible (router, printer, etc.)
     - Check if SSH is accessible: `timeout 2 nc -z <IP> 22`

4. **Create LAN map**
   - Organize discovered devices by:
     - IP address
     - MAC address
     - Hostname (if available)
     - Device type (if identifiable)
     - Open ports/services (if detected)

5. **Save results**
   - Offer to save the LAN map to `~/ai-docs/network/lan-map-$(date +%Y%m%d).md`
   - Include timestamp and subnet information

## Output

Present the LAN map in a clear table format showing:
- IP Address
- MAC Address
- Hostname
- Device Type/Notes
- Status (active/inactive)

Include summary statistics (total devices, device type breakdown).
