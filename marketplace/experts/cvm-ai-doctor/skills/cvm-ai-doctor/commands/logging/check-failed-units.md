# Check Failed Systemd Units

You are helping the user identify and diagnose failed systemd units (services, mounts, timers, etc.).

## Task

1. **List all failed units:**
   ```bash
   # Show failed units
   systemctl --failed

   # More detailed output
   systemctl --failed --all

   # Include user units
   systemctl --user --failed
   ```

2. **Get detailed status of failed units:**
   ```bash
   # For each failed unit, get details
   for unit in $(systemctl --failed --no-legend | awk '{print $1}'); do
     echo "=== $unit ==="
     systemctl status "$unit" --no-pager -l
     echo ""
   done
   ```

3. **Check recent failures:**
   ```bash
   # Units that failed in last boot
   systemctl list-units --failed --state=failed

   # Check boot log for failures
   journalctl -b -p err | grep -i "failed"
   ```

4. **Analyze specific failed unit:**
   ```bash
   # Status with full output
   systemctl status UNIT_NAME -l --no-pager

   # Recent logs for the unit
   journalctl -u UNIT_NAME -n 50 --no-pager

   # Logs from current boot
   journalctl -b -u UNIT_NAME --no-pager

   # All logs for the unit
   journalctl -u UNIT_NAME --since "24 hours ago" --no-pager
   ```

5. **Check unit dependencies:**
   ```bash
   # What this unit depends on
   systemctl list-dependencies UNIT_NAME

   # What depends on this unit
   systemctl list-dependencies --reverse UNIT_NAME

   # Check if dependencies failed
   systemctl list-dependencies UNIT_NAME --all | while read dep; do
     systemctl is-failed "$dep" 2>/dev/null | grep -q "^failed" && echo "FAILED: $dep"
   done
   ```

6. **Common failure patterns:**
   ```bash
   # Mount failures
   systemctl --failed | grep ".mount"

   # Service failures
   systemctl --failed | grep ".service"

   # Timer failures
   systemctl --failed | grep ".timer"

   # Network-related failures
   systemctl --failed | grep -E "network|dhcp|dns"
   ```

7. **Attempt to diagnose failure reason:**
   ```bash
   # Exit code and signal
   systemctl show UNIT_NAME | grep -E "ExecMainStatus|ExecMainCode|Result"

   # Unit file location and settings
   systemctl cat UNIT_NAME

   # Check if unit file exists and is valid
   systemctl show UNIT_NAME -p LoadState,ActiveState,SubState,Result
   ```

8. **Try to restart failed units:**
   ```bash
   # Ask user if they want to attempt restart
   # List failed units
   failed_units=$(systemctl --failed --no-legend | awk '{print $1}')

   # For each unit, ask to restart
   for unit in $failed_units; do
     echo "Attempting to restart: $unit"
     sudo systemctl restart "$unit"
     systemctl is-active --quiet "$unit" && echo "✓ $unit restarted successfully" || echo "✗ $unit restart failed"
   done
   ```

9. **Check for masked units:**
   ```bash
   # List masked units
   systemctl list-unit-files | grep masked

   # Check if failed unit is masked
   systemctl is-enabled UNIT_NAME
   ```

10. **Generate failure report:**
    ```bash
    cat > /tmp/failed-units-report.txt << EOF
    Failed Units Report - $(date)
    ======================================

    Failed Units Summary:
    $(systemctl --failed --no-pager)

    Detailed Status:
    EOF

    for unit in $(systemctl --failed --no-legend | awk '{print $1}'); do
      echo "" >> /tmp/failed-units-report.txt
      echo "=== $unit ===" >> /tmp/failed-units-report.txt
      systemctl status "$unit" --no-pager -l >> /tmp/failed-units-report.txt 2>&1
      echo "" >> /tmp/failed-units-report.txt
      echo "Recent Logs:" >> /tmp/failed-units-report.txt
      journalctl -u "$unit" -n 20 --no-pager >> /tmp/failed-units-report.txt 2>&1
      echo "" >> /tmp/failed-units-report.txt
    done

    cat /tmp/failed-units-report.txt
    ```

## Present Summary to User

Provide:
- Number of failed units
- List of failed unit names and types
- Failure reasons (exit codes, signals)
- Recent log entries for each
- Recommended actions

## Common Failed Units & Solutions

**NetworkManager-wait-online.service:**
- Usually safe to ignore or disable if not needed
- `sudo systemctl disable NetworkManager-wait-online.service`

**ModemManager.service:**
- May fail if no modem hardware present
- Can disable: `sudo systemctl disable ModemManager.service`

**bluetooth.service:**
- Check firmware: `journalctl -u bluetooth | grep -i firmware`
- Restart: `sudo systemctl restart bluetooth`

**systemd-resolved.service:**
- Check config: `/etc/systemd/resolved.conf`
- DNS issues: `resolvectl status`

**Mount units (*.mount):**
- Check fstab: `cat /etc/fstab`
- Verify device exists: `lsblk`
- Check mount point permissions

**User services:**
- Check user journal: `journalctl --user -u UNIT_NAME`
- May need `loginctl enable-linger USER`

## Cleanup Actions

```bash
# Reset failed state
sudo systemctl reset-failed

# Disable permanently failed units (ask first!)
sudo systemctl disable UNIT_NAME

# Mask unit to prevent activation
sudo systemctl mask UNIT_NAME

# Unmask unit
sudo systemctl unmask UNIT_NAME

# Reload systemd configuration
sudo systemctl daemon-reload
```

## Notes

- Not all failures are critical - some are expected
- Check if service is actually needed before disabling
- Some failures may be due to hardware not present (modems, bluetooth)
- Mount failures can prevent boot - be careful with fstab changes
- User units are separate from system units
- Use `systemctl reset-failed` to clear failed state after fixing
