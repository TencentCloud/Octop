---
description: Intelligently probe system for security vulnerabilities
tags: [security, audit, vulnerabilities, hardening, project, gitignored]
---

You are helping the user identify security vulnerabilities they may wish to remediate.

## Process

1. **System update status**
   - Check for security updates: `apt list --upgradable | grep -i security`
   - Check unattended-upgrades status: `systemctl status unattended-upgrades`

2. **Open ports and services**
   - List listening ports: `sudo ss -tlnp`
   - Identify unnecessary services: `systemctl list-unit-files --state=enabled`
   - Check firewall status: `sudo ufw status verbose`

3. **SSH configuration review**
   - Check `sshd_config` for:
     - PermitRootLogin (should be 'no')
     - PasswordAuthentication (consider disabling)
     - Port (consider non-standard)
   - Check for weak keys: `ssh-keygen -l -f ~/.ssh/id_*.pub`

4. **File permissions audit**
   - Check world-writable files: `find /home -type f -perm -002 2>/dev/null | head -20`
   - Check SUID/SGID binaries: `find / -type f \( -perm -4000 -o -perm -2000 \) 2>/dev/null`
   - Review sensitive file permissions: `~/.ssh`, `~/.gnupg`

5. **User and authentication**
   - List users with shell access: `cat /etc/passwd | grep -v nologin | grep -v false`
   - Check password policy: `sudo chage -l $USER`
   - Review sudo configuration: `sudo -l`

6. **Network security**
   - Check for IPv6 if not needed
   - Review DNS settings
   - Check for proxy configurations

7. **Application security**
   - Check for outdated software with known CVEs
   - Review browser security settings
   - Check for auto-updating mechanisms

8. **Suggest security tools**
   - `lynis` - Security auditing tool
   - `rkhunter` - Rootkit scanner
   - `aide` - File integrity checker
   - `fail2ban` - Intrusion prevention

## Output

Provide a security report showing:
- Critical vulnerabilities (requiring immediate attention)
- Medium priority issues
- Low priority recommendations
- Suggested remediation steps for each issue
- Security hardening recommendations
