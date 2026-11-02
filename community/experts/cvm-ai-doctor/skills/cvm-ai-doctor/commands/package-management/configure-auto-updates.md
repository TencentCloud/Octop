# Configure Ubuntu Auto-Updates

You are helping the user configure automatic updates for Ubuntu.

## Your tasks:

1. **Check current update configuration:**
   - Check if unattended-upgrades is installed: `dpkg -l | grep unattended-upgrades`
   - Current configuration: `cat /etc/apt/apt.conf.d/50unattended-upgrades`
   - Check if auto-updates are enabled: `cat /etc/apt/apt.conf.d/20auto-upgrades`
   - Update check frequency: `cat /etc/apt/apt.conf.d/10periodic`

2. **Install unattended-upgrades if not present:**
   ```bash
   sudo apt update
   sudo apt install unattended-upgrades apt-listchanges
   ```

3. **Ask user about their update preferences:**
   Discuss with the user:
   - **Security updates only** (recommended, safest)
   - **Security + recommended updates**
   - **All updates** (risky for production systems)
   - **Update frequency**: daily, weekly
   - **Auto-reboot preference**: never, only for security, scheduled time
   - **Email notifications** (if configured)

4. **Configure update types:**
   Edit `/etc/apt/apt.conf.d/50unattended-upgrades`:

   For security updates only (recommended):
   ```
   Unattended-Upgrade::Allowed-Origins {
       "${distro_id}:${distro_codename}-security";
   };
   ```

   For security + updates:
   ```
   Unattended-Upgrade::Allowed-Origins {
       "${distro_id}:${distro_codename}-security";
       "${distro_id}:${distro_codename}-updates";
   };
   ```

5. **Configure automatic reboot settings:**
   In `/etc/apt/apt.conf.d/50unattended-upgrades`, configure:

   **Never auto-reboot (safest):**
   ```
   Unattended-Upgrade::Automatic-Reboot "false";
   ```

   **Auto-reboot when required:**
   ```
   Unattended-Upgrade::Automatic-Reboot "true";
   Unattended-Upgrade::Automatic-Reboot-Time "02:00";
   ```

   **Only reboot if no users logged in:**
   ```
   Unattended-Upgrade::Automatic-Reboot-WithUsers "false";
   ```

6. **Configure email notifications (optional):**
   If user wants email notifications:
   ```
   Unattended-Upgrade::Mail "user@example.com";
   Unattended-Upgrade::MailReport "on-change";  // or "always" or "only-on-error"
   ```

   Note: Requires mail system configured (postfix, sendmail, etc.)

7. **Enable automatic updates:**
   Create/edit `/etc/apt/apt.conf.d/20auto-upgrades`:
   ```
   APT::Periodic::Update-Package-Lists "1";
   APT::Periodic::Download-Upgradeable-Packages "1";
   APT::Periodic::AutocleanInterval "7";
   APT::Periodic::Unattended-Upgrade "1";
   ```

   Explanation:
   - `Update-Package-Lists`: Update package list (1=daily)
   - `Download-Upgradeable-Packages`: Pre-download updates (1=daily)
   - `AutocleanInterval`: Clean up old packages (7=weekly)
   - `Unattended-Upgrade`: Actually install updates (1=daily)

8. **Configure blacklist (packages to exclude):**
   In `/etc/apt/apt.conf.d/50unattended-upgrades`:
   ```
   Unattended-Upgrade::Package-Blacklist {
       "linux-image-*";  // Example: don't auto-update kernel
       "nvidia-*";        // Example: don't auto-update GPU drivers
   };
   ```

   Ask user if there are specific packages they want to exclude.

9. **Test configuration:**
   - Check configuration syntax:
     ```bash
     sudo unattended-upgrades --dry-run --debug
     ```
   - View what would be updated:
     ```bash
     sudo unattended-upgrade --dry-run
     ```

10. **Set up monitoring:**
    - Check logs: `cat /var/log/unattended-upgrades/unattended-upgrades.log`
    - Check dpkg log: `cat /var/log/dpkg.log`
    - Monitor update service status: `systemctl status unattended-upgrades.service`

11. **Configure additional safety options:**
    In `/etc/apt/apt.conf.d/50unattended-upgrades`:
    ```
    // Remove unused dependencies
    Unattended-Upgrade::Remove-Unused-Dependencies "true";

    // Remove unused kernel packages
    Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";

    // Automatically remove new unused dependencies
    Unattended-Upgrade::Remove-New-Unused-Dependencies "true";

    // Split the upgrade into smallest possible chunks
    Unattended-Upgrade::MinimalSteps "true";

    // Install updates when on AC power only
    Unattended-Upgrade::OnlyOnACPower "true";  // laptops only
    ```

12. **Set up pre/post-update hooks (optional):**
    If user wants custom actions before/after updates:
    ```
    Unattended-Upgrade::PreUpdate "echo 'Starting updates' | logger";
    Unattended-Upgrade::PostUpdate "echo 'Updates complete' | logger";
    ```

13. **Enable and start the service:**
    ```bash
    sudo systemctl enable unattended-upgrades
    sudo systemctl start unattended-upgrades
    sudo systemctl status unattended-upgrades
    ```

14. **Manual trigger for testing:**
    ```bash
    sudo unattended-upgrade -d
    ```

15. **Provide best practices and recommendations:**
    - **Desktops/Workstations**: Security updates only, no auto-reboot
    - **Servers**: Security updates only, scheduled reboot window if needed
    - **Laptops**: Same as desktop, plus OnlyOnACPower option
    - **Production systems**: Manual updates preferred, or extensive testing
    - Always check logs periodically: `/var/log/unattended-upgrades/`
    - Test in non-production environment first
    - Keep kernel packages in blacklist if you want manual control
    - Consider using livepatch for kernel updates without rebooting
    - Set up email notifications for important systems
    - Monitor disk space - updates require free space

16. **Show how to check what's configured:**
    ```bash
    # View current configuration
    apt-config dump APT::Periodic

    # Check when updates last ran
    ls -la /var/lib/apt/periodic/

    # View update history
    cat /var/log/unattended-upgrades/unattended-upgrades.log
    ```

## Important notes:
- Backup configuration files before editing
- Test with --dry-run before enabling
- Auto-reboot can be disruptive - configure carefully
- Email requires MTA (mail system) configured
- Updates consume bandwidth and disk space
- Some updates may break custom configurations
- Keep an eye on logs after enabling
- Security updates are generally safe to auto-install
- Feature updates may require testing
