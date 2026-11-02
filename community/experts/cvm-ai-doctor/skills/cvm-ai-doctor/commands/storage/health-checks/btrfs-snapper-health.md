# BTRFS and Snapper Snapshot Health Check

You are helping the user check their BTRFS filesystem configuration and Snapper snapshot setup.

## Your tasks:

1. **Check if BTRFS is in use:**
   - Run `df -T` to identify BTRFS filesystems
   - Run `sudo btrfs filesystem show` to display all BTRFS filesystems
   - Run `mount | grep btrfs` to see mounted BTRFS filesystems with their options

2. **Check BTRFS filesystem health:**
   - For each BTRFS filesystem found, run `sudo btrfs filesystem usage <mountpoint>`
   - Run `sudo btrfs device stats <mountpoint>` to check for device errors
   - Run `sudo btrfs scrub status <mountpoint>` to check scrub status

3. **Check Snapper configuration:**
   - Check if Snapper is installed: `which snapper`
   - If not installed, ask the user if they want to install it
   - List Snapper configurations: `sudo snapper list-configs`
   - For each configuration, show snapshots: `sudo snapper -c <config> list`
   - Show Snapper configuration details: `sudo snapper -c <config> get-config`

4. **Analyze snapshot usage:**
   - Check disk space used by snapshots
   - Identify if there are too many snapshots that should be cleaned up
   - Check automatic snapshot policies

5. **Report findings:**
   - Summarize BTRFS health status
   - Report on snapshot configurations and disk usage
   - Provide recommendations for:
     - Snapshot retention policies if too many snapshots exist
     - Running scrub if it hasn't been run recently
     - Fixing any errors or issues detected
     - Setting up Snapper if BTRFS is in use but Snapper is not configured

## Important notes:
- Use sudo for all BTRFS and Snapper commands
- Be clear about what you find and what actions you recommend
- If BTRFS is not in use, inform the user and exit gracefully
