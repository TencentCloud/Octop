---
description: Detect known spyware packages and suggest removal
tags: [security, spyware, privacy, audit, project, gitignored]
---

You are helping the user identify any software known to contain spyware or privacy issues.

## Process

1. **Check for known problematic software**
   - Scan installed packages against known spyware list
   - Common categories to check:
     - Browser extensions
     - "Free" VPN applications
     - Screen recorders with telemetry
     - System "optimizers"
     - Certain proprietary drivers

2. **Check for telemetry in common applications**
   - VS Code vs VSCodium (telemetry difference)
   - Ubuntu's whoopsie (error reporting)
   - Canonical's snapd telemetry
   - Google Chrome vs Chromium

3. **Network activity monitoring**
   - Check for suspicious outbound connections: `sudo netstat -tupn | grep ESTABLISHED`
   - Identify processes making external connections
   - Suggest using `wireshark` or `tcpdump` for deeper analysis

4. **Known spyware patterns to check**
   - Red Star OS components (North Korean)
   - Chinese software with known backdoors
   - Certain "free" antivirus software
   - Keyloggers disguised as utilities
   - Browser hijackers

5. **Privacy-concerning legitimate software**
   - Software with excessive telemetry:
     - Ubuntu's apport (crash reporting)
     - popularity-contest
     - Some proprietary drivers
   - Suggest privacy-respecting alternatives

6. **Browser extension audit**
   - Check Chrome/Firefox extension directories
   - Identify extensions with excessive permissions
   - Flag abandoned extensions (security risk)

7. **Suggest privacy-focused alternatives**
   - VS Code → VSCodium
   - Chrome → Chromium or Firefox
   - Zoom → Jitsi
   - Windows telemetry remnants if dual-boot

## Output

Provide a report showing:
- Any detected spyware (with severity level)
- Privacy-concerning software with excessive telemetry
- Suspicious network connections
- Recommended actions for each finding
- Privacy-focused alternatives to suggest
