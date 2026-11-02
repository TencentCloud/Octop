You are conducting a comprehensive security posture evaluation for this Linux desktop system.

## Your Task

Perform a thorough security assessment of the system and provide a detailed report with actionable recommendations.

## Assessment Areas

### 1. Firewall Status
- Check if UFW (Uncomplicated Firewall) or iptables is active
- Review firewall rules and policies
- Identify any concerning open ports

### 2. System Updates
- Check for available security updates
- Verify automatic update configuration
- Review update history for critical patches

### 3. User Account Security
- List user accounts and their privileges
- Check for accounts with sudo access
- Identify any accounts without passwords or weak configurations
- Review SSH key configurations

### 4. SSH Security
- Check if SSH is running
- Review SSH configuration (`/etc/ssh/sshd_config`)
- Verify key-based authentication settings
- Check for root login permission
- Review allowed authentication methods

### 5. Running Services
- List all active services
- Identify unnecessary services that could be disabled
- Check for services listening on external interfaces

### 6. File Permissions
- Check critical system files (`/etc/passwd`, `/etc/shadow`, `/etc/sudoers`)
- Review permissions on home directories
- Identify world-writable files in system directories

### 7. Antivirus/Malware Protection
- Check if ClamAV or other antivirus is installed
- Verify if definitions are up to date
- Check recent scan history

### 8. Security Packages
- Verify installation of: fail2ban, apparmor, aide, rkhunter, lynis
- Check their configuration and status

### 9. Network Security
- Review listening ports and services
- Check for unusual network connections
- Verify network configuration security

### 10. Audit Logs
- Check if auditd is running
- Review recent authentication logs
- Look for failed login attempts
- Check for suspicious sudo usage

## Output Format

Provide your findings in the following structured format:

```
SECURITY POSTURE ASSESSMENT
Generated: [timestamp]

=== SUMMARY ===
Overall Security Level: [Critical/Poor/Fair/Good/Excellent]
Critical Issues Found: [number]
Warnings: [number]
Recommendations: [number]

=== CRITICAL ISSUES ===
[List any critical security problems that need immediate attention]

=== WARNINGS ===
[List security concerns that should be addressed]

=== CURRENT PROTECTIONS ===
[List active security measures in place]

=== RECOMMENDATIONS ===
[Prioritized list of security improvements]

=== DETAILED FINDINGS ===
[Detailed breakdown by assessment area]
```

## Important Notes

- Use sudo when necessary to access system files and configurations
- Be thorough but focus on actionable findings
- Prioritize issues by severity
- Provide specific commands for remediation where applicable
- Consider the desktop/workstation context (not a server)
