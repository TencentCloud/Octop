You are tasked with installing and configuring ClamAV (command-line antivirus) and ClamTK (GUI frontend) on this Linux system if they are not already installed.

## Your Task

Set up a complete antivirus solution using ClamAV with the ClamTK graphical interface for easy management.

## Installation Steps

### 1. Check Current Installation Status
- Verify if ClamAV is already installed: `dpkg -l | grep clamav`
- Verify if ClamTK is already installed: `dpkg -l | grep clamtk`
- If both are installed and working, inform the user and skip to configuration verification

### 2. Install Packages (if needed)
Install the following packages using apt:
- `clamav` - Core antivirus engine
- `clamav-daemon` - ClamAV daemon for background scanning
- `clamav-freshclam` - Virus definition updater
- `clamtk` - Graphical user interface for ClamAV

Use sudo for installation.

### 3. Initial Configuration

After installation:
- Stop the freshclam service: `sudo systemctl stop clamav-freshclam`
- Update virus definitions manually first: `sudo freshclam`
- Start the freshclam service: `sudo systemctl start clamav-freshclam`
- Enable freshclam to start on boot: `sudo systemctl enable clamav-freshclam`

### 4. Configure ClamAV Daemon
- Start the ClamAV daemon: `sudo systemctl start clamav-daemon`
- Enable it for automatic startup: `sudo systemctl enable clamav-daemon`
- Verify daemon is running: `sudo systemctl status clamav-daemon`

### 5. Verify Installation
- Check ClamAV version: `clamscan --version`
- Check virus definition database date: `sudo freshclam --version` and verify freshclam status
- Verify ClamTK launches: Inform user they can test by running `clamtk` from terminal or application menu

### 6. Initial Scan Setup Recommendations
Provide guidance on:
- Running a quick test scan: `clamscan -r /home/[username]/Downloads`
- Setting up scheduled scans via ClamTK
- Configuring scan exclusions if needed
- Understanding quarantine location

## Post-Installation Information

Provide the user with:
- Location of ClamAV logs: `/var/log/clamav/`
- How to update definitions manually: `sudo freshclam`
- How to run a full system scan: `sudo clamscan -r /`
- ClamTK location in application menu (typically under System or Utilities)
- Recommendation to set up automatic scheduled scans via ClamTK GUI

## Output Format

```
CLAMAV/CLAMTK INSTALLATION REPORT

=== INSTALLATION STATUS ===
ClamAV: [Installed/Already Present]
ClamAV Daemon: [Running/Status]
FreshClam: [Running/Status]
ClamTK: [Installed/Already Present]

=== VIRUS DEFINITIONS ===
Last Updated: [date/time]
Database Version: [version]
Signatures: [number]

=== SERVICES STATUS ===
clamav-daemon: [active/inactive]
clamav-freshclam: [active/inactive]

=== NEXT STEPS ===
[Recommendations for first scan, scheduled scans, etc.]
```

## Important Notes

- Use sudo for all installation and system configuration commands
- Handle cases where packages are already installed gracefully
- Ensure virus definitions are updated before declaring success
- Verify services are running and enabled
- If any step fails, provide clear error messages and troubleshooting steps
- For Ubuntu/Debian systems, use apt package manager
- Initial virus definition update may take several minutes - be patient
