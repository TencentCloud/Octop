# Hard Drive Health Check

You are helping the user run comprehensive health checks on all storage drives (SSD, HDD, NVMe, or mixed configurations).

## Platform Detection

Before running commands, detect the OS:
```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux → Linux, macOS → Darwin, Windows → MINGW*/MSYS*/CYGWIN*
```

## Your tasks:

### 1. Identify all storage devices:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| List block devices | `lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,MODEL,TRAN` | `diskutil list` | `wmic diskdrive get Model,Size,MediaType,InterfaceType` |
| Detailed disk info | `sudo lshw -class disk -short` | `diskutil info /dev/disk0` | `wmic diskdrive get Model,Size,Status,InterfaceType` |
| Identify types | Check lsblk TRAN column (sata, nvme, etc.) | `diskutil info /dev/disk0 \| grep Type` | `wmic diskdrive get MediaType` (Fixed disk, Removable) |

### 2. Check SMART status for each device:

**Install smartmontools if missing:**
- Linux: `sudo apt install smartmontools`
- macOS: `brew install smartmontools`
- Windows: Download from https://www.smartmontools.org/wiki/Download

**For SATA/SAS drives:**

| Action | Linux | macOS |
|--------|-------|-------|
| Device info | `sudo smartctl -i /dev/sdX` | `sudo smartctl -i /dev/diskN` |
| Health status | `sudo smartctl -H /dev/sdX` | `sudo smartctl -H /dev/diskN` |
| Attributes | `sudo smartctl -A /dev/sdX` | `sudo smartctl -A /dev/diskN` |
| Error log | `sudo smartctl -l error /dev/sdX` | `sudo smartctl -l error /dev/diskN` |

Note: macOS device paths are `/dev/disk0`, `/dev/disk1`, etc. (not `/dev/sda`)

**For NVMe drives:**

| Action | Linux | Windows |
|--------|-------|---------|
| List NVMe | `sudo nvme list` | N/A |
| SMART log | `sudo nvme smart-log /dev/nvmeXn1` | `powershell "Get-PhysicalDisk \| Select MediaType,HealthStatus,OperationalStatus,Wear"` |
| Via smartctl | `sudo smartctl -a /dev/nvmeXn1` | N/A |

Note: macOS does not natively support NVMe CLI tools. Use `smartctl` which has basic NVMe support.

**Windows SMART (alternative):**
```powershell
# PowerShell native disk health
Get-PhysicalDisk | Select-Object FriendlyName, MediaType, HealthStatus, OperationalStatus, Wear
Get-PhysicalDisk | Get-StorageReliabilityCounter | Select-Object Wear, Temperature, PowerOnHours
```

### 3. Analyze drive health indicators:

**For SSDs:**
- Wear leveling count
- Media wearout indicator
- Available spare capacity
- Percentage used
- Total bytes written
- Power-on hours
- Reallocated sectors

**For HDDs:**
- Reallocated sector count
- Current pending sectors
- Offline uncorrectable sectors
- Spin retry count
- Power-on hours
- Temperature
- UDMA CRC errors

**For NVMe:**
- Critical warning
- Temperature
- Available spare
- Percentage used
- Data units read/written
- Power cycles
- Unsafe shutdowns

### 4. Check filesystem health:

| Action | Linux | macOS | Windows |
|--------|-------|-------|---------|
| Disk errors in kernel log | `sudo dmesg \| grep -i "error\|fail" \| grep -i "sd\|nvme"` | `log show --predicate 'subsystem == "com.apple.iokit.IOStorageFamily"' --last 7d` | `powershell "Get-WinEvent @{ProviderName='disk'} -MaxEvents 20"` |
| System log errors | `sudo journalctl -p err -g "sd\|nvme" --since "7 days ago"` | `log show --predicate 'messageType == "error"' --last 7d --info` | `powershell "Get-WinEvent @{LogName='System'; Level=2} -MaxEvents 20"` |

### 5. Report findings:
- Summarize each drive's health status
- Highlight any concerning indicators:
  - High reallocated sectors
  - High wear level on SSDs
  - Temperature issues
  - Errors in logs
  - Pending sectors
- Calculate estimated remaining lifespan for SSDs based on wear indicators
- Provide recommendations:
  - Drives that should be replaced soon
  - Drives that need monitoring
  - Whether to enable SMART monitoring if not active
  - Backup recommendations if drives show signs of failure

## Important notes:
- Always detect OS first and use correct device paths
- Linux: `/dev/sda`, `/dev/sdb`, `/dev/nvme0n1`
- macOS: `/dev/disk0`, `/dev/disk1` (use `diskutil list` to identify)
- Windows: Use PowerShell `Get-PhysicalDisk` or WMI queries
- Use sudo for all SMART commands (Linux/macOS)
- Be clear about the severity of any issues found
- Distinguish between informational metrics and critical warnings
- Some drives may not support all SMART features - this is normal
