# Hardware Profile

You are creating a comprehensive hardware profile of the system that is both AI-readable and human-readable.

## Platform Detection

Before running commands, detect the OS:
```bash
OS_TYPE=$(uname -s 2>/dev/null)
# Linux → Linux, macOS → Darwin, Windows → MINGW*/MSYS*/CYGWIN*
```

## Your Task

Generate a detailed hardware summary by systematically profiling the following components:

### 1. CPU Profile

| Info | Linux | macOS | Windows |
|------|-------|-------|---------|
| Model/Specs | `lscpu` | `sysctl -n machdep.cpu.brand_string` | `wmic cpu get Name,NumberOfCores,NumberOfLogicalProcessors` |
| Architecture | `lscpu \| grep Architecture` | `uname -m` | `echo %PROCESSOR_ARCHITECTURE%` |
| Frequency | `lscpu \| grep MHz` or `cat /proc/cpuinfo \| grep MHz` | `sysctl -n hw.cpufrequency` | `wmic cpu get MaxClockSpeed` |
| Virtualization | `lscpu \| grep Virtualization` or `kvm-ok` | `sysctl -n machdep.cpu.features \| grep -i vmx` | `wmic cpu get VirtualizationFirmwareEnabled` |
| Vulnerabilities | `cat /sys/devices/system/cpu/vulnerabilities/*` | N/A (check Apple security updates) | Check Windows Update / Microsoft Security Response Center |

### 2. Memory Profile

| Info | Linux | macOS | Windows |
|------|-------|-------|---------|
| Total RAM | `free -h` | `sysctl -n hw.memsize` (bytes) | `wmic computersystem get TotalPhysicalMemory` |
| Memory type/speed | `sudo dmidecode -t memory` | `system_profiler SPMemoryDataType` | `wmic memorychip get Capacity,Speed,Manufacturer` |
| Module config | `sudo dmidecode -t memory \| grep -E "Size|Locator|Type"` | `system_profiler SPMemoryDataType` | `wmic memorychip get DeviceLocator,Capacity` |
| Swap | `swapon --show` | `sysctl vm.swapusage` | `wmic pagefileset get AllocatedBaseSize,Name` |
| Current usage | `free -h` | `vm_stat` + `sysctl hw.memsize` | `wmic OS get TotalVisibleMemorySize,FreePhysicalMemory` |

### 3. Storage Profile

| Info | Linux | macOS | Windows |
|------|-------|-------|---------|
| List devices | `lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,MODEL` | `diskutil list` | `wmic diskdrive get Model,Size,MediaType,InterfaceType` |
| Detailed layout | `sudo fdisk -l` | `diskutil list -plist` | `wmic partition get Name,Size,Type` |
| SMART health | `sudo smartctl -a /dev/sdX` | `sudo smartctl -a /dev/diskN` | `powershell "Get-PhysicalDisk \| Select HealthStatus,Wear"` |
| Usage/Mounts | `df -h` | `df -h` | `wmic logicaldisk get caption,size,freespace,filesystem` |

### 4. Graphics Profile

| Info | Linux | macOS | Windows |
|------|-------|-------|---------|
| GPU info | `lspci \| grep -i vga` | `system_profiler SPDisplaysDataType` | `powershell "Get-WmiObject Win32_VideoController"` |
| Detailed | `sudo lshw -C display` | `system_profiler SPDisplaysDataType` | `wmic path win32_VideoController get Name,AdapterRAM,DriverVersion` |
| NVIDIA | `nvidia-smi` | `system_profiler SPDisplaysDataType` | `powershell "nvidia-smi"` (if NVIDIA driver) |
| OpenGL/Vulkan | `glxinfo \| grep "OpenGL version"` | `system_profiler SPDisplaysDataType` | `dxdiag` or GPU-Z |

### 5. Network Profile

| Info | Linux | macOS | Windows |
|------|-------|-------|---------|
| Interfaces | `ip addr` or `ifconfig` | `ifconfig` or `networksetup -listallhardwareports` | `ipconfig /all` |
| Details | `sudo lshw -C network` | `system_profiler SPNetworkDataType` | `wmic nic get Name,MACAddress,Speed` |
| WiFi | `iwconfig` or `iw dev` | `system_profiler SPAirPortDataType` | `netsh wlan show interfaces` |
| Link speed | `ethtool eth0` | `networksetup -getinfo Ethernet` | `wmic nic get Name,Speed` |

### 6. System Board and Firmware

| Info | Linux | macOS | Windows |
|------|-------|-------|---------|
| Motherboard | `sudo dmidecode -t baseboard` | `system_profiler SPHardwareDataType` | `wmic baseboard get Manufacturer,Product,Version` |
| BIOS/UEFI | `sudo dmidecode -t bios` | `system_profiler SPHardwareDataType` | `wmic bios get SMBIOSBIOSVersion,ReleaseDate` |
| System model | `sudo dmidecode -t system` | `system_profiler SPHardwareDataType` | `wmic computersystem get Manufacturer,Model` |
| Serial | `sudo dmidecode -t system \| grep Serial` | `system_profiler SPHardwareDataType \| grep Serial` | `wmic bios get SerialNumber` |

### 7. Peripherals and Devices

| Info | Linux | macOS | Windows |
|------|-------|-------|---------|
| USB | `lsusb -v` | `system_profiler SPUSBDataType` | `powershell "Get-PnpDevice -Class USB"` |
| PCI | `lspci -v` | N/A (Apple Silicon has no traditional PCI) | `wmic path Win32_PnPEntity where "Name like '%PCI%'"` |
| Audio | `aplay -l` or `sudo lshw -C sound` | `system_profiler SPAudioDataType` | `wmic path Win32_SoundDevice get Name,Status` |
| Input devices | `xinput list` (GUI) or `cat /proc/bus/input/devices` | `system_profiler SPUSBDataType` (keyboards/mice) | `powershell "Get-PnpDevice -Class Keyboard,Mouse"` |

### 8. Thermal and Power

| Info | Linux | macOS | Windows |
|------|-------|-------|---------|
| Temperature | `sensors` (needs lm-sensors) | `sudo powermetrics --samplers thermal -i 3000 -n 1` | `powershell "Get-WmiObject MSAcpi_ThermalZoneTemperature"` |
| Fan | `sensors` (fan speeds if supported) | `sudo powermetrics --samplers thermal` | `powershell "Get-WmiObject Win32_Fan"` |
| Battery | `upower -i /org/freedesktop/UPower/devices/battery_BAT0` | `system_profiler SPPowerDataType` | `powercfg /batteryreport` or `wmic path Win32_Battery get EstimatedChargeRemaining` |
| Power mgmt | `cat /sys/class/power_supply/*/type` | `pmset -g` | `powercfg /list` |

## Commands to Use (by Platform)

**Linux:**
- Overview: `inxi -Fxz` or `hwinfo --short`
- CPU: `lscpu`, `cat /proc/cpuinfo`
- Memory: `free -h`, `sudo dmidecode -t memory`
- Storage: `lsblk`, `sudo fdisk -l`, `sudo smartctl -a /dev/sdX`
- GPU: `lspci | grep -i vga`, `sudo lshw -C display`
- Network: `ip addr`, `sudo lshw -C network`
- Motherboard: `sudo dmidecode -t baseboard`, `sudo dmidecode -t bios`
- Peripherals: `lsusb`, `lspci`, `sensors`

**macOS:**
- Overview: `system_profiler SPHardwareDataType`
- CPU: `sysctl -n machdep.cpu.brand_string hw.ncpu hw.cpufrequency`
- Memory: `system_profiler SPMemoryDataType`, `sysctl -n hw.memsize`
- Storage: `diskutil list`, `df -h`
- GPU: `system_profiler SPDisplaysDataType`
- Network: `networksetup -listallhardwareports`, `ifconfig`
- Motherboard: `system_profiler SPHardwareDataType`
- Peripherals: `system_profiler SPUSBDataType`, `system_profiler SPAudioDataType`
- Battery: `system_profiler SPPowerDataType`, `pmset -g`

**Windows:**
- Overview: `wmic computersystem get Manufacturer,Model,TotalPhysicalMemory`
- CPU: `wmic cpu get Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed`
- Memory: `wmic memorychip get Capacity,Speed,Manufacturer,DeviceLocator`
- Storage: `wmic diskdrive get Model,Size,MediaType`, `Get-PhysicalDisk`
- GPU: `powershell "Get-WmiObject Win32_VideoController"`
- Network: `ipconfig /all`, `wmic nic get Name,MACAddress,Speed`
- Motherboard: `wmic baseboard get Manufacturer,Product,Version`
- Peripherals: `powershell "Get-PnpDevice"`, `wmic path Win32_SoundDevice get Name`

## Output Format

Create a structured report with the following sections:

### Executive Summary
- System type (desktop/laptop/server)
- Detected OS and version
- Overall hardware generation/age
- Primary use case capabilities (gaming, development, general use)

### Detailed Hardware Profile

**CPU:**
- Model: [full CPU name]
- Cores/Threads: [physical cores]/[logical threads]
- Base/Max Frequency: [GHz]
- Cache: L1/L2/L3 sizes
- Features: [virtualization, security features]

**Memory:**
- Total: [GB] ([type] @ [speed])
- Configuration: [X modules in Y slots]
- Swap: [size] ([type])

**Storage:**
- Drive 1: [model] ([type]) - [capacity] - Health: [status]
- Drive 2: ...
- Total capacity: [TB]
- Partition layout: [summary]

**Graphics:**
- GPU: [model]
- Driver: [version and type]
- VRAM: [size]
- Displays: [count and configuration]

**Network:**
- Ethernet: [model] - [speed]
- WiFi: [model] - [protocols]
- Active connections: [summary]

**Motherboard:**
- Manufacturer: [brand]
- Model: [model number]
- BIOS: [version] ([date])

**Peripherals:**
- [List of notable USB/PCI devices]

**Thermal/Power:**
- Current temperatures: [CPU/GPU/etc.]
- Battery: [status if laptop]

### Hardware Capabilities Assessment

Rate and describe:
- **Performance tier**: Entry/Mid/High-end for [CPU/GPU/Storage/RAM]
- **Bottlenecks**: Identify any limiting components
- **Upgrade recommendations**: Suggest meaningful upgrades if applicable
- **Compatibility notes**: Driver status on detected OS, known issues

### AI-Readable Summary (JSON)

Provide a structured JSON object:
```json
{
  "system_type": "desktop|laptop|server",
  "os_type": "linux|macos|windows",
  "cpu": {
    "model": "",
    "cores": 0,
    "threads": 0,
    "base_ghz": 0.0,
    "max_ghz": 0.0
  },
  "memory": {
    "total_gb": 0,
    "type": "",
    "speed_mhz": 0
  },
  "storage": [
    {
      "device": "",
      "type": "nvme|ssd|hdd",
      "capacity_gb": 0,
      "health": "good|warning|critical"
    }
  ],
  "gpu": {
    "model": "",
    "vendor": "nvidia|amd|intel|apple",
    "driver": "",
    "vram_gb": 0
  },
  "network": {
    "ethernet": {"present": true, "speed_mbps": 0},
    "wifi": {"present": true, "standard": ""}
  }
}
```

## Execution Guidelines

1. **Detect OS first** — use platform-appropriate commands for all subsequent checks
2. **Run commands systematically** in the order listed above
3. **Handle missing tools gracefully**: Note if `inxi`, `hwinfo`, `smartctl`, or `sensors` are not installed and provide install commands
4. **Use sudo appropriately**: Many hardware queries require root privileges (Linux/macOS)
5. **Parse output carefully**: Extract relevant information, filter noise
6. **Cross-reference data**: Verify findings using multiple tools when possible
7. **Format for readability**: Use tables, bullet points, and clear hierarchies
8. **Include context**: Add brief explanations for technical specs
9. **Flag concerns**: Highlight any hardware issues, deprecated drivers, or thermal problems

## Important Notes

- macOS uses `system_profiler` as the primary hardware query tool (replaces lshw, dmidecode, lsusb, lspci, etc.)
- Windows uses WMI/PowerShell as the primary hardware query tool
- Some commands may require installation of additional packages
- SMART data requires drives that support it (most modern SSDs/HDDs)
- GPU information varies significantly by vendor
- Thermal data availability depends on sensor support
- Always respect privacy: avoid exposing serial numbers in shared contexts
