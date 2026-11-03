# RAID Configuration Check

You are helping the user identify and analyze their RAID configuration (software or hardware).

## Your tasks:

1. **Detect RAID type:**

   **Software RAID (mdadm):**
   - Check if mdadm is installed: `which mdadm`
   - List all MD devices: `cat /proc/mdstat`
   - Get detailed info for each array: `sudo mdadm --detail /dev/md*`
   - Check mdadm configuration: `cat /etc/mdadm/mdadm.conf` (if exists)

   **LVM RAID:**
   - Check for LVM: `sudo pvs`, `sudo vgs`, `sudo lvs`
   - Check for RAID logical volumes: `sudo lvs -a -o +devices,segtype`

   **Hardware RAID:**
   - Check for common hardware RAID controllers:
     - MegaRAID: `sudo lspci | grep -i raid` and `which megacli` or `which storcli`
     - HP Smart Array: `which hpacucli` or `which ssacli`
     - Adaptec: `which arcconf`
   - List block devices: `lsblk` and `sudo lshw -class disk -class storage`

   **ZFS (if applicable):**
   - Check if ZFS is installed: `which zfs`
   - List ZFS pools: `sudo zpool status`
   - List ZFS datasets: `sudo zfs list`

2. **Analyze RAID health:**
   - For software RAID: check array status, degraded arrays, sync status
   - For hardware RAID: if tools are available, check controller and disk status
   - Check for any failed or missing drives
   - Review disk errors: `sudo smartctl -a /dev/sd*` for member disks

3. **Report configuration details:**
   - RAID level (RAID 0, 1, 5, 6, 10, etc.)
   - Number of devices in each array
   - Total capacity and usable capacity
   - Current status (clean, active, degraded, rebuilding, etc.)
   - Performance configuration (chunk size, stripe size)

4. **Provide recommendations:**
   - If arrays are degraded, suggest immediate action
   - If no monitoring is configured, suggest setting up monitoring
   - If hardware RAID tools are missing, suggest installation
   - Best practices for the detected configuration

## Important notes:
- Use sudo for all RAID-related commands
- If no RAID is detected, clearly state "No RAID configuration found"
- Be specific about what type of RAID is in use
- Highlight any critical issues requiring immediate attention
