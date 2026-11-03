---
description: Perform a full system upgrade with apt-get (updates package lists and upgrades all packages)
tags: [sysadmin, maintenance, apt, upgrade, system]
---

Perform a comprehensive system upgrade:

1. Update the package lists from repositories
2. Upgrade all installed packages to their latest versions
3. Show which packages were upgraded
4. Clean up any unnecessary packages

Use sudo to execute these commands with appropriate privileges.

Run the following commands sequentially:
- `sudo apt-get update` to refresh package lists
- `sudo apt-get upgrade -y` to upgrade packages
- `sudo apt-get autoremove -y` to remove unnecessary packages
- `sudo apt-get autoclean` to clean up package cache

Provide a summary of what was updated and if a reboot is recommended.
