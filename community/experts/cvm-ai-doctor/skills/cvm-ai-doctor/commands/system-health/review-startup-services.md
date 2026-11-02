---
description: Review system startup services, identify failed or deprecated services, and clean up boot jobs
tags: [sysadmin, systemd, services, boot, cleanup, troubleshooting]
---

Review and clean up system startup services:

1. **Failed Services**: Identify all services that failed to start
2. **Enabled Services**: List all enabled services that start at boot
3. **Deprecated Services**: Identify services that may be outdated or unnecessary
4. **Service Dependencies**: Check for broken dependencies
5. **Masked Services**: Review masked services
6. **Timing Analysis**: Identify services that slow down boot

Run the following diagnostic commands:

**Failed and Problematic Services:**
- `systemctl --failed` to list all failed services
- `systemctl list-units --state=failed --all` for detailed failed units
- `systemctl list-units --state=error` for services in error state
- `systemctl list-units --state=not-found` for services with missing unit files

**Enabled Services:**
- `systemctl list-unit-files --state=enabled` for all enabled services
- `systemctl list-units --type=service --state=running` for currently running services
- `systemctl list-units --type=service --state=active` for active services

**Boot-time Services:**
- `systemd-analyze blame | head -n 30` for slowest boot services
- `systemctl list-dependencies --before multi-user.target` for services started before multi-user
- `systemctl list-dependencies --after multi-user.target` for services started after multi-user

**Service Details for Failed Services:**
For each failed service, run:
- `systemctl status [service-name]` for current status
- `journalctl -u [service-name] -n 50` for recent logs
- `systemctl cat [service-name]` to view unit file

**Masked Services:**
- `systemctl list-unit-files --state=masked` for masked services

**Deprecated/Unnecessary Service Detection:**
- Check for common deprecated services (networking.service on systemd systems, etc.)
- Identify services for removed/uninstalled software
- Find duplicate or redundant services

Analyze the output and provide:

**Failed Services Report:**
- List each failed service with its error message
- Classify the failure:
  - Missing dependencies
  - Configuration errors
  - Service no longer needed
  - Hardware/driver related
  - Permission issues

**Recommendations for each failed service:**
- **Remove**: Service is deprecated or related to uninstalled software
  - Command: `sudo systemctl disable [service-name]`
  - Command: `sudo systemctl mask [service-name]` if it keeps trying to start

- **Fix**: Service is needed but has configuration issues
  - Provide specific fix based on error logs
  - Command to restart after fix: `sudo systemctl restart [service-name]`

- **Investigate**: Service failure needs deeper investigation
  - Provide relevant log excerpts
  - Suggest diagnostic steps

**Boot Optimization Opportunities:**
- Services that can be set to start on-demand instead of at boot
- Services that can be disabled if not needed
- Commands to disable: `sudo systemctl disable [service-name]`
- Commands to mask: `sudo systemctl mask [service-name]`

**Enabled Services Review:**
- List all enabled services
- Highlight services that may be unnecessary:
  - Services for unused hardware
  - Duplicate services
  - Development/testing services on production systems
  - Legacy services replaced by newer alternatives

**Safety Warnings:**
- Warn before suggesting removal of critical services
- List services that should NOT be disabled
- Suggest creating a snapshot/backup before making changes (especially for BTRFS/Snapper systems)

**Action Plan:**
Provide a prioritized list of actions:
1. Safe to disable/mask (services clearly not needed)
2. Should be fixed (services needed but failing)
3. Investigate further (unclear if needed or cause of failure)

For each action, provide the exact commands to execute.

**Post-cleanup:**
After making changes, recommend:
- `sudo systemctl daemon-reload` to reload systemd configuration
- `systemd-analyze` to check boot time improvement
- Review logs after next boot to ensure no new issues
