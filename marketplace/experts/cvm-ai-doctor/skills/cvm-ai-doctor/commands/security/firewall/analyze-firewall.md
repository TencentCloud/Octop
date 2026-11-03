# Analyze Firewall and Suggest Hardening

You are helping the user check if a firewall is running, analyze open ports, and suggest potential hardening.

## Your tasks:

1. **Check if a firewall is active:**

   **UFW (Uncomplicated Firewall):**
   ```bash
   sudo ufw status verbose
   ```

   **iptables (lower level):**
   ```bash
   sudo iptables -L -n -v
   sudo ip6tables -L -n -v
   ```

   **firewalld (if used):**
   ```bash
   sudo firewall-cmd --state
   sudo firewall-cmd --list-all
   ```

   **nftables (modern replacement for iptables):**
   ```bash
   sudo nft list ruleset
   ```

2. **If no firewall is active, recommend enabling UFW:**
   ```bash
   sudo apt install ufw
   sudo ufw enable
   sudo ufw status
   ```

3. **Check currently listening services:**
   ```bash
   sudo ss -tulpn
   # Or
   sudo netstat -tulpn
   ```

   This shows what services are listening on which ports.

4. **Check for open ports from external perspective:**
   ```bash
   sudo nmap -sT -O localhost
   ```

   Or install nmap if not available:
   ```bash
   sudo apt install nmap
   ```

5. **Analyze each open port:**
   For each listening port, identify:
   - Which service is using it
   - Whether it should be accessible from network
   - Current firewall rules for it

   Common ports to check:
   - 22 (SSH)
   - 80 (HTTP)
   - 443 (HTTPS)
   - 3306 (MySQL)
   - 5432 (PostgreSQL)
   - 6379 (Redis)
   - 27017 (MongoDB)
   - 3389 (RDP)
   - 445 (SMB)
   - 2049 (NFS)

6. **Check UFW rules in detail:**
   ```bash
   sudo ufw status numbered
   sudo ufw show added
   ```

7. **Check iptables rules in detail:**
   ```bash
   sudo iptables -S
   sudo iptables -L INPUT -v -n
   sudo iptables -L OUTPUT -v -n
   sudo iptables -L FORWARD -v -n
   ```

8. **Identify potential security issues:**

   **Services listening on 0.0.0.0 (all interfaces):**
   These are accessible from network. Should they be?
   ```bash
   sudo ss -tulpn | grep "0.0.0.0"
   ```

   **Services that should only be local:**
   Databases, Redis, etc. should typically only listen on 127.0.0.1:
   ```bash
   sudo ss -tulpn | grep -v "127.0.0.1"
   ```

   **Unnecessary services:**
   Check for services that shouldn't be running:
   ```bash
   sudo systemctl list-units --type=service --state=running | grep -E "telnet|ftp|rsh"
   ```

9. **Analyze by service type:**

   **SSH (port 22):**
   - Should SSH be accessible from internet?
   - Consider changing default port
   - Check SSH configuration: `cat /etc/ssh/sshd_config | grep -v "^#" | grep -v "^$"`
   - Verify key-only authentication is enforced
   - Check fail2ban status: `sudo systemctl status fail2ban`

   **Web services (80, 443):**
   - Are these intentional?
   - Is there a web server running?
   - Check for default/test pages

   **Databases (3306, 5432, 27017, etc.):**
   - Should NEVER be exposed to internet
   - Should listen only on 127.0.0.1
   - Check configuration files

10. **Check for common attack vectors:**
    ```bash
    # Check for services with known vulnerabilities
    sudo ss -tulpn | grep -E "telnet|ftp|rlogin|rsh|rexec"

    # Check for uncommon high ports
    sudo ss -tulpn | awk '{print $5}' | cut -d: -f2 | sort -n | uniq
    ```

11. **Suggest hardening measures:**

    **Enable UFW if not active:**
    ```bash
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    sudo ufw enable
    ```

    **For SSH access:**
    ```bash
    sudo ufw allow 22/tcp comment 'SSH'
    # Or from specific IP:
    sudo ufw allow from <IP-address> to any port 22 comment 'SSH from specific IP'
    ```

    **For web server:**
    ```bash
    sudo ufw allow 80/tcp comment 'HTTP'
    sudo ufw allow 443/tcp comment 'HTTPS'
    ```

    **For local network only:**
    ```bash
    sudo ufw allow from 192.168.1.0/24 comment 'Local network'
    ```

12. **Install and configure fail2ban (recommended):**
    ```bash
    sudo apt install fail2ban
    sudo systemctl enable fail2ban
    sudo systemctl start fail2ban
    sudo fail2ban-client status
    sudo fail2ban-client status sshd
    ```

13. **Check for IPv6 exposure:**
    ```bash
    sudo ss -tulpn6
    sudo ufw status
    ```

    Ensure IPv6 is also protected:
    ```bash
    sudo ufw default deny incoming
    # UFW handles both IPv4 and IPv6
    ```

14. **Advanced iptables hardening (if using iptables):**

    **Drop invalid packets:**
    ```bash
    sudo iptables -A INPUT -m conntrack --ctstate INVALID -j DROP
    ```

    **Rate limit SSH:**
    ```bash
    sudo iptables -A INPUT -p tcp --dport 22 -m conntrack --ctstate NEW -m recent --set
    sudo iptables -A INPUT -p tcp --dport 22 -m conntrack --ctstate NEW -m recent --update --seconds 60 --hitcount 4 -j DROP
    ```

    **Log dropped packets:**
    ```bash
    sudo iptables -A INPUT -j LOG --log-prefix "iptables-dropped: "
    ```

15. **Check for Docker interference:**
    Docker manipulates iptables directly, which can bypass UFW:
    ```bash
    sudo iptables -L DOCKER -n
    ```

    To prevent Docker from bypassing UFW, edit `/etc/docker/daemon.json`:
    ```json
    {
      "iptables": false
    }
    ```

    Or use firewalld instead for better Docker integration.

16. **Check connection tracking:**
    ```bash
    sudo conntrack -L
    cat /proc/sys/net/netfilter/nf_conntrack_count
    cat /proc/sys/net/netfilter/nf_conntrack_max
    ```

17. **Review logging:**
    ```bash
    sudo grep UFW /var/log/syslog | tail -20
    sudo tail -20 /var/log/ufw.log
    ```

18. **Generate hardening recommendations:**
    Based on findings, suggest:
    - Enable firewall if not active
    - Block unnecessary ports
    - Restrict services to local interface only
    - Install fail2ban for brute-force protection
    - Change SSH port (optional, security through obscurity)
    - Disable root SSH login
    - Use key-based SSH authentication only
    - Close database ports from external access
    - Remove unnecessary services
    - Enable connection rate limiting
    - Set up intrusion detection (OSSEC, Snort)
    - Regular security updates
    - Monitor logs regularly

19. **Provide firewall management commands:**

    **UFW:**
    - `sudo ufw status` - Check status
    - `sudo ufw enable` - Enable firewall
    - `sudo ufw disable` - Disable firewall
    - `sudo ufw allow <port>` - Allow port
    - `sudo ufw deny <port>` - Deny port
    - `sudo ufw delete <rule>` - Delete rule
    - `sudo ufw reset` - Reset to default
    - `sudo ufw logging on` - Enable logging

    **iptables:**
    - `sudo iptables -L` - List rules
    - `sudo iptables -A INPUT -p tcp --dport <port> -j ACCEPT` - Allow port
    - `sudo iptables -D INPUT <rule-number>` - Delete rule
    - `sudo iptables-save > /etc/iptables/rules.v4` - Save rules
    - `sudo iptables-restore < /etc/iptables/rules.v4` - Restore rules

20. **Report findings:**
    Summarize:
    - Firewall status (active/inactive)
    - List of open ports
    - Services listening on each port
    - Current firewall rules
    - Security issues found
    - Recommended hardening measures
    - Priority actions (critical vs. nice-to-have)

## Important notes:
- Test firewall rules carefully to avoid locking yourself out
- Always have a backup access method (console/KVM) before changing SSH rules
- UFW and iptables can conflict - use one or the other
- Docker can bypass UFW - special configuration needed
- Deny incoming by default, allow specific services
- Keep logs for intrusion detection
- Regularly review and update firewall rules
- Consider using VPN for remote access instead of exposing services
- fail2ban is essential for SSH protection
- Don't expose databases to the internet
