---
description: Diagnose installed printers and suggest removal of unused ones
tags: [system, printers, cups, cleanup, project, gitignored]
---

You are helping the user review installed printers and identify ones that can be removed.

## Process

1. **Check CUPS status**
   - Verify CUPS is running: `systemctl status cups`
   - Access CUPS web interface info: check `http://localhost:631`

2. **List configured printers**
   - Run: `lpstat -p -d`
   - Show detailed info: `lpstat -l -p`
   - List printer queues: `lpq -a`

3. **Check printer usage**
   - View printer job history if available
   - Check `/var/log/cups/page_log` for usage patterns
   - Identify printers with no recent jobs

4. **Identify printer drivers**
   - List installed printer drivers: `lpinfo -m | grep -i <printer-brand>`
   - Check for unnecessary driver packages: `dpkg -l | grep -E "printer|cups|hplip"`

5. **Test printer connectivity**
   - For network printers, ping their IPs
   - Check if printers are still on the network
   - Test print to each printer: `lp -d <printer> /etc/hosts`

6. **Suggest removals**
   - Old/disconnected printers
   - Duplicate printer entries
   - Printers user no longer has access to
   - Unnecessary drivers

7. **Cleanup commands**
   - Remove printer: `lpadmin -x <printer-name>`
   - Remove unused drivers: `apt remove <driver-package>`
   - Clean print queue: `cancel -a <printer-name>`
   - Disable CUPS if no printers needed: `sudo systemctl disable cups`

## Output

Provide a report showing:
- List of configured printers with status
- Last usage date (if available)
- Network connectivity status
- Installed printer drivers
- Recommendations for removal
- Cleanup commands
- Potential space savings
