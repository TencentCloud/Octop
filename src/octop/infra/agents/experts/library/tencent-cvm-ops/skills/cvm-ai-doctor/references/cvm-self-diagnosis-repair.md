# CVM Self-Diagnosis & Repair Reference

> **Context**: Instance has OpenClaw deployed, can execute commands internally even if SSH fails  
> **Use**: Quick command reference for common self-healing scenarios

---

## 1. SSH Service Issues

### Diagnosis
```bash
# Check service status
systemctl status sshd    # Ubuntu/CentOS
service ssh status       # Debian

# Check port listening
netstat -tlnp | grep :22
ss -tlnp | grep :22

# Validate config
sshd -t
```

### Repair
```bash
# Start service
sudo systemctl start sshd && sudo systemctl enable sshd

# Fix common config issues
sudo sed -i 's/^PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sudo sed -i 's/^PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Fix permissions
sudo chmod 600 /etc/ssh/ssh_host_*_key
sudo chmod 644 /etc/ssh/ssh_host_*_key.pub
```

**Risk**: 🟡 Medium (requires restart)

---

## 2. Disk Full

### Diagnosis
```bash
df -h
du -sh /* 2>/dev/null | sort -h | tail -5
du -sh /var/log/* 2>/dev/null | sort -h | tail -5
```

### Repair
```bash
# Clean system logs (⚠️ High risk - confirm first)
sudo journalctl --vacuum-size=100M
sudo truncate -s 0 /var/log/syslog
sudo find /var/log -name "*.log" -type f -mtime +7 -exec truncate -s 0 {} \;

# Clean package cache
sudo apt-get clean            # Ubuntu/Debian
sudo yum clean all            # CentOS

# Clean temp files
sudo rm -rf /tmp/*
sudo rm -rf /var/tmp/*
```

**Risk**: 🔴 High (deletes logs/data - backup first)

---

## 3. Firewall Lockout

### Diagnosis
```bash
# iptables
sudo iptables -L -n -v | grep -E 'REJECT|DROP'

# firewalld
sudo firewall-cmd --list-all
sudo firewall-cmd --zone=public --list-ports

# ufw
sudo ufw status verbose
```

### Repair
```bash
# iptables - allow SSH
sudo iptables -I INPUT -p tcp --dport 22 -j ACCEPT
sudo iptables-save > /etc/iptables/rules.v4    # Debian/Ubuntu
sudo service iptables save                      # CentOS 6
sudo iptables-save > /etc/sysconfig/iptables   # CentOS 7+

# firewalld
sudo firewall-cmd --zone=public --add-port=22/tcp --permanent
sudo firewall-cmd --reload

# ufw
sudo ufw allow 22/tcp
```

**Risk**: 🟡 Medium (security config change)

---

## 4. Memory Exhaustion

### Diagnosis
```bash
free -h
ps aux --sort=-%mem | head -10
dmesg | grep -i "out of memory"
```

### Repair
```bash
# Add swap (⚠️ confirm size first)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Kill high-memory process (⚠️ confirm PID first)
sudo kill -9 <PID>
```

**Risk**: 🔴 High (kills processes - may affect services)

---

## 5. Account Lockout

### Diagnosis
```bash
# Check failed login attempts
faillock --user root
sudo pam_tally2 --user=root    # Older systems

# Check fail2ban
sudo fail2ban-client status sshd
```

### Repair
```bash
# Unlock account
sudo faillock --user root --reset
sudo pam_tally2 --user=root --reset

# Unban from fail2ban
sudo fail2ban-client set sshd unbanip <IP>
```

**Risk**: 🟢 Low (safe operation)

---

## 6. Service Crash

### Diagnosis
```bash
systemctl status <service>
journalctl -u <service> -n 50 --no-pager
dmesg | tail -50
```

### Repair
```bash
sudo systemctl restart <service>
sudo systemctl enable <service>
```

**Risk**: 🟡 Medium (service interruption)

---

## Quick Triage Flow

```
1. Check disk space → df -h
   If > 95% → Clean logs/cache first

2. Check memory → free -h
   If > 90% → Identify top process

3. Check SSH service → systemctl status sshd
   If inactive → Start service

4. Check firewall → iptables -L -n | grep 22
   If blocked → Allow port 22

5. Check account lock → faillock --user root
   If locked → Reset faillock
```

---

## User Confirmation Protocol

### 🟢 Low Risk (auto-execute)
- Service status checks
- Port listening checks
- Log file reading
- Account lock status

### 🟡 Medium Risk (confirm first)
- Service restart
- Firewall rule changes
- SSH config modifications
- Adding swap

### 🔴 High Risk (explicit confirmation + show impact)
- Deleting logs/files
- Killing processes
- Truncating system logs
- Mass file cleanup

**Always**: Backup configs before modification, show exact commands before execution
