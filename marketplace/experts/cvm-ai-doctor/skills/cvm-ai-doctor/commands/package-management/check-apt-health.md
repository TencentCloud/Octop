# APT Package Manager Health Check

You are helping the user ensure that the APT package manager on Ubuntu is in good working health and remove any broken third-party repositories or packages.

## Your tasks:

1. **Check basic APT functionality:**
   - Update package lists: `sudo apt update`
   - Check for errors in output
   - Verify cache state: `apt-cache policy`

2. **Check for broken packages:**
   - List broken packages: `dpkg -l | grep "^..r"`
   - Check for unconfigured packages: `dpkg -l | grep "^..c"`
   - Check dpkg status: `sudo dpkg --configure -a`
   - Check for broken dependencies: `sudo apt-get check`

3. **Identify problematic repositories:**
   - List all repositories:
     ```bash
     grep -r --include '*.list' '^deb ' /etc/apt/sources.list /etc/apt/sources.list.d/
     ```
   - Check for failing repositories during update:
     ```bash
     sudo apt update 2>&1 | grep -i "fail\|error\|warning"
     ```
   - List third-party PPAs:
     ```bash
     ls /etc/apt/sources.list.d/
     ```

4. **Check APT cache integrity:**
   - Check cache size: `du -sh /var/cache/apt/archives/`
   - List problematic cache entries:
     ```bash
     sudo apt-get clean
     sudo apt-get autoclean
     ```

5. **Fix broken dependencies:**
   - Attempt to fix broken packages:
     ```bash
     sudo apt --fix-broken install
     ```
   - Force reconfiguration of all packages:
     ```bash
     sudo dpkg --configure -a
     ```
   - Try to complete interrupted installations:
     ```bash
     sudo apt-get -f install
     ```

6. **Identify and handle broken third-party repositories:**
   For each failing repository found:
   - Ask user if they still need it
   - If not needed, disable or remove:
     ```bash
     sudo add-apt-repository --remove ppa:<ppa-name>
     ```
   - Or manually remove: `sudo rm /etc/apt/sources.list.d/<repo>.list`
   - Or disable by commenting out: `sudo sed -i 's/^deb/#deb/' /etc/apt/sources.list.d/<repo>.list`

7. **Check for GPG key issues:**
   - Check for missing GPG keys:
     ```bash
     sudo apt update 2>&1 | grep "NO_PUBKEY"
     ```
   - If missing keys found, attempt to import:
     ```bash
     sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys <KEY>
     ```
   - List all trusted keys: `apt-key list`

8. **Check for duplicate repositories:**
   - Find duplicates:
     ```bash
     grep -h "^deb " /etc/apt/sources.list /etc/apt/sources.list.d/* | sort | uniq -d
     ```
   - Remove duplicates manually or ask user which to keep

9. **Check disk space:**
   - Disk space in /var: `df -h /var`
   - If low on space:
     ```bash
     sudo apt-get clean
     sudo apt-get autoclean
     sudo apt-get autoremove
     ```

10. **Check for held packages:**
    - List held packages: `apt-mark showhold`
    - These packages won't be upgraded - ask user if intentional
    - To unhold: `sudo apt-mark unhold <package-name>`

11. **Verify repository configurations:**
    - Check main sources.list: `cat /etc/apt/sources.list`
    - Ensure official Ubuntu repositories are present:
      - main
      - restricted
      - universe
      - multiverse
      - security updates
      - updates
      - backports (optional)

12. **Check for obsolete packages:**
    - List locally installed packages not in any repository:
      ```bash
      aptitude search '~o'
      ```
    - Or using apt: `apt list '~o'`

13. **Verify package authentication:**
    - Check if packages are being verified:
      ```bash
      grep -r "APT::Get::AllowUnauthenticated" /etc/apt/
      ```
    - Should be "false" or not present for security

14. **Run full system check:**
    - Check for consistency: `sudo apt-get check`
    - Simulate upgrade to check for issues: `sudo apt-get -s upgrade`
    - Simulate dist-upgrade: `sudo apt-get -s dist-upgrade`

15. **Clean up:**
    - Remove old packages: `sudo apt-get autoremove`
    - Clean package cache: `sudo apt-get clean`
    - Clean old cached packages: `sudo apt-get autoclean`

16. **Reset APT if severely broken:**
    If APT is severely corrupted, may need to:
    ```bash
    # Backup current sources
    sudo cp -r /etc/apt /etc/apt.backup

    # Reset dpkg
    sudo dpkg --clear-avail
    sudo apt-get update

    # Reinstall base packages if needed
    sudo apt-get install --reinstall apt dpkg
    ```

17. **Check APT configuration files:**
    - List all APT config: `apt-config dump`
    - Check for problematic configurations in:
      - `/etc/apt/apt.conf`
      - `/etc/apt/apt.conf.d/`
    - Look for unusual proxy settings, deprecated options

18. **Report findings:**
    Summarize:
    - Number of broken packages (if any)
    - Problematic repositories (outdated PPAs, failing repos)
    - Missing GPG keys
    - Dependency issues
    - Disk space issues
    - Held packages
    - Overall APT health status (HEALTHY / NEEDS ATTENTION / BROKEN)

19. **Provide recommendations:**
    - List of repositories to remove
    - Packages to fix or remove
    - Whether full system upgrade is recommended
    - Cleanup commands to run
    - Any configuration changes needed
    - If APT is healthy, suggest regular maintenance:
      ```bash
      sudo apt update && sudo apt upgrade
      sudo apt autoremove
      sudo apt clean
      ```

## Important notes:
- Always backup before removing repositories or packages
- Don't remove dependencies of packages user needs
- Some third-party repos may be intentionally added - confirm before removing
- Be cautious with --fix-broken - it may remove packages
- Check if user is running unsupported Ubuntu version (EOL)
- PPAs may lag behind Ubuntu releases
- sudo is required for most operations
- After major fixes, suggest reboot to ensure clean state
