You are performing an exhaustive motherboard (system board) profile of the system.

## Your Task

Generate a comprehensive motherboard analysis covering all aspects of the system board, chipset, firmware, and connectivity.

### 1. Motherboard Identification
- **Manufacturer**: Board manufacturer (ASUS, Gigabyte, MSI, etc.)
- **Product name**: Board model/SKU
- **Version**: Board revision number
- **Serial number**: Board serial number
- **Asset tag**: Asset tag (if configured)
- **Location in chassis**: Board location descriptor
- **Board type**: Motherboard, server board, embedded, etc.

### 2. Chipset Information
- **Chipset manufacturer**: Intel, AMD, etc.
- **Chipset model**: Specific chipset name
- **Chipset features**: Key capabilities
- **PCH/FCH revision**: Platform controller hub revision
- **South bridge**: Legacy south bridge info
- **North bridge**: Legacy north bridge info (if separate)

### 3. BIOS/UEFI Firmware
- **Firmware type**: BIOS or UEFI
- **Vendor**: BIOS manufacturer (AMI, Award, Phoenix, etc.)
- **Version**: Current BIOS version
- **Release date**: BIOS release date
- **Revision**: Firmware major/minor revision
- **ROM size**: BIOS ROM capacity
- **UEFI mode**: Legacy or UEFI boot mode
- **Secure boot**: Status and configuration

### 4. Expansion Slots
- **PCIe slots**: Count and generations (PCIe 3.0/4.0/5.0)
- **Slot types**: x16, x8, x4, x1 configurations
- **Slot usage**: Which slots are occupied
- **M.2 slots**: Count, key types, and generations
- **Legacy slots**: PCI, AGP (if any)
- **Slot sharing**: Lane sharing configurations

### 5. Storage Controllers and Interfaces
- **SATA ports**: Count and generation (SATA II/III)
- **SATA controllers**: Onboard controller details
- **NVMe support**: M.2 NVMe slot count and PCIe lanes
- **RAID support**: Hardware RAID capabilities
- **Storage modes**: AHCI, RAID, IDE
- **eSATA**: External SATA ports
- **U.2/U.3**: Enterprise NVMe support

### 6. I/O Connectivity
- **USB controllers**: USB controller chipsets
- **USB ports**: Count by version (2.0, 3.0, 3.1, 3.2, 4.0)
- **USB-C ports**: Count and capabilities
- **Thunderbolt**: Version and port count
- **Internal USB headers**: Front panel USB headers
- **PS/2 ports**: Legacy keyboard/mouse ports
- **Serial ports**: RS-232 COM ports
- **Parallel port**: LPT port (rare)

### 7. Network Interfaces
- **Ethernet controllers**: Onboard NIC chipsets
- **Ethernet ports**: Count and speeds (1G, 2.5G, 10G)
- **WiFi**: Onboard WiFi chipset and standard
- **Bluetooth**: Bluetooth version
- **MAC addresses**: Physical addresses of NICs

### 8. Audio Subsystem
- **Audio codec**: Onboard audio chipset
- **Audio channels**: 2.0, 5.1, 7.1 support
- **Audio ports**: Line-in, line-out, mic, optical
- **Audio features**: Special audio technologies
- **HDMI/DP audio**: Audio over display connections

### 9. Display and Graphics
- **Integrated graphics**: iGPU support (if applicable)
- **Display outputs**: HDMI, DisplayPort, DVI, VGA
- **Multi-monitor**: Maximum displays supported
- **Display port versions**: HDMI 2.1, DP 1.4, etc.

### 10. Power Delivery
- **Power phases**: VRM phase count
- **Power connectors**: ATX 24-pin, EPS 8-pin, etc.
- **CPU power**: 4-pin, 8-pin, 8+4 pin configuration
- **PCIe power**: Additional PCIe power headers
- **Fan headers**: Count and type (PWM/DC)
- **RGB headers**: Addressable RGB headers
- **Power monitoring**: Voltage monitoring points

### 11. Memory Support
- **Memory slots**: Total DIMM slots
- **Maximum capacity**: Maximum RAM supported
- **Memory types**: DDR4, DDR5, ECC support
- **Memory speeds**: Supported frequencies
- **Memory channels**: Dual, quad channel
- **XMP/DOCP**: Overclocking profile support

### 12. Form Factor and Physical
- **Form factor**: ATX, Micro-ATX, Mini-ITX, EATX, etc.
- **Dimensions**: Board dimensions
- **Mounting holes**: Standoff pattern
- **Contained devices**: Onboard devices count

### 13. Special Features
- **Overclocking**: OC features and BIOS options
- **TPM**: Trusted Platform Module version
- **BIOS flashback**: No-CPU BIOS update
- **Q-Flash/M-Flash**: Motherboard-specific tools
- **POST code display**: Onboard debug LEDs/display
- **Dual BIOS**: Backup BIOS chip
- **Clear CMOS**: CMOS reset button/jumper
- **BIOS recovery**: Recovery mechanisms

### 14. Temperature and Monitoring
- **Temperature sensors**: Onboard sensor locations
- **Fan control**: Hardware fan control capabilities
- **Voltage monitoring**: Monitored voltage rails
- **Hardware monitoring chip**: Super I/O or monitoring IC

### 15. System Slots and Headers
- **Front panel headers**: Power, reset, LED headers
- **Internal headers**: All internal connectors
- **System fan headers**: Chassis fan connectors
- **Pump headers**: Water cooling pump headers
- **Addressable RGB**: ARGB/DRGB header count
- **Temperature probe headers**: External sensor inputs

## Commands to Use

**Motherboard identification:**
- `sudo dmidecode -t baseboard`
- `sudo dmidecode -t 2`
- `cat /sys/class/dmi/id/board_vendor`
- `cat /sys/class/dmi/id/board_name`
- `cat /sys/class/dmi/id/board_version`

**BIOS/UEFI information:**
- `sudo dmidecode -t bios`
- `sudo dmidecode -t 0`
- `cat /sys/class/dmi/id/bios_vendor`
- `cat /sys/class/dmi/id/bios_version`
- `cat /sys/class/dmi/id/bios_date`
- `efibootmgr -v` (if UEFI)
- `[ -d /sys/firmware/efi ] && echo "UEFI" || echo "BIOS"`

**Chipset information:**
- `lspci | grep -i "ISA bridge"`
- `lspci -v | grep -A 10 "ISA bridge"`
- `sudo dmidecode -t 9` - System slots

**PCI/PCIe slots and devices:**
- `lspci -tv` - Tree view of PCI devices
- `lspci -vv` - Verbose PCI information
- `sudo dmidecode -t 9` - System slot information
- `sudo lspci -vvv -s <slot>` - Specific slot details

**Storage controllers:**
- `lspci | grep -i "sata\|raid\|storage"`
- `lspci -v | grep -A 10 -i "sata\|ahci"`
- `ls /sys/class/ata_port/` - SATA ports
- `ls /sys/block/nvme*` - NVMe devices

**USB controllers:**
- `lspci | grep -i usb`
- `lsusb -v`
- `lsusb -t` - USB device tree
- `cat /sys/kernel/debug/usb/devices`

**Network controllers:**
- `lspci | grep -i "ethernet\|network"`
- `sudo lshw -class network`
- `ip link show`

**Audio controller:**
- `lspci | grep -i audio`
- `aplay -l`
- `cat /proc/asound/cards`

**System information:**
- `sudo dmidecode -t system`
- `sudo dmidecode -t chassis`
- `sudo lshw -short`
- `sudo lshw -businfo`

**Hardware monitoring:**
- `sensors` (if lm-sensors configured)
- `cat /sys/class/hwmon/hwmon*/name`
- `sudo i2cdetect -l` (I2C buses)

**Firmware and boot:**
- `sudo dmidecode -t 13` - BIOS language
- `bootctl status` (systemd-boot)
- `efibootmgr -v` (UEFI variables)

**Memory slots:**
- `sudo dmidecode -t 16` - Physical memory array
- `sudo dmidecode -t 17` - Memory devices

**Expansion and slots:**
- `sudo dmidecode -t 9` - System slots
- `sudo biosdecode` - Additional BIOS info

**TPM and security:**
- `cat /sys/class/tpm/tpm0/device/description`
- `tpm2_getcap properties-fixed` (if TPM 2.0 tools)

## Output Format

### Executive Summary
```
Motherboard: [manufacturer] [model] (rev [version])
Chipset: [chipset model]
Form Factor: [ATX/mATX/ITX]
BIOS: [vendor] v[version] ([date])
Features: [key features]
```

### Detailed Motherboard Profile

**Board Identification:**
- Manufacturer: [vendor]
- Product Name: [model]
- Version: [revision]
- Serial Number: [S/N]
- Asset Tag: [tag]
- Type: [motherboard type]

**Chipset:**
- Manufacturer: [Intel/AMD]
- Model: [chipset name]
- Revision: [revision]
- Features: [key capabilities]

**BIOS/UEFI:**
- Type: [BIOS/UEFI]
- Vendor: [manufacturer]
- Version: [version]
- Release Date: [date]
- Revision: [major.minor]
- ROM Size: [KB/MB]
- Boot Mode: [Legacy/UEFI]
- Secure Boot: [Enabled/Disabled]

**Expansion Slots:**
- PCIe x16 Slots: [count] (Gen [3.0/4.0/5.0])
  - Slot 1: PCIe [gen] x16 - [occupied by: device]
  - Slot 2: PCIe [gen] x16 (runs at x8) - [status]
- PCIe x1 Slots: [count]
- M.2 Slots: [count]
  - M.2_1: Key M, PCIe [gen] x4 - [device]
  - M.2_2: Key M, PCIe [gen] x4 - [empty]

**Storage Interfaces:**
- SATA Ports: [count] x SATA [II/III]
- SATA Controller: [chipset model]
- NVMe Support: [count] x M.2 slots (PCIe [gen] x4)
- RAID Support: [0, 1, 5, 10]
- Storage Mode: [AHCI/RAID/IDE]

**I/O Connectivity:**
- USB Controllers: [chipset models]
- USB Ports:
  - USB 2.0: [count] ports
  - USB 3.0/3.1 Gen 1: [count] ports
  - USB 3.1 Gen 2: [count] ports
  - USB 3.2 Gen 2x2: [count] ports
  - USB4/Thunderbolt: [count] ports
- USB-C: [count] ports ([capabilities])
- Internal USB Headers: [count]
- Legacy Ports: [PS/2, Serial, Parallel]

**Network:**
- Ethernet Controllers: [chipset models]
- Ethernet Ports: [count] x [1G/2.5G/10G]
- WiFi: [chipset] ([802.11 standard])
- Bluetooth: [version]

**Audio:**
- Audio Codec: [chipset model]
- Channels: [2.0/5.1/7.1]
- Audio Ports: [count and types]
- Features: [special audio tech]

**Display Outputs (if integrated graphics):**
- HDMI: [count] x HDMI [version]
- DisplayPort: [count] x DP [version]
- DVI: [count] ports
- VGA: [count] ports

**Power Delivery:**
- VRM Phases: [count]-phase ([digital/analog])
- ATX Power: 24-pin
- CPU Power: [4/8/8+4]-pin
- PCIe Power: [auxiliary power headers]
- Fan Headers: [count] ([PWM/DC])
- RGB Headers: [count] ([ARGB/RGB])

**Memory Support:**
- DIMM Slots: [count]
- Maximum Capacity: [GB]
- Memory Type: [DDR4/DDR5]
- Supported Speeds: Up to [MT/s]
- Channel Mode: [Dual/Quad] Channel
- ECC Support: [Yes/No]
- XMP/DOCP: [version]

**Form Factor:**
- Standard: [ATX/mATX/Mini-ITX/EATX]
- Dimensions: [mm x mm]
- Mounting: [ATX standard]

**Special Features:**
- TPM: [version] ([enabled/disabled])
- BIOS Flashback: [Yes/No]
- Dual BIOS: [Yes/No]
- POST Code Display: [Yes/No]
- Clear CMOS: [Button/Jumper]
- Overclocking: [features list]

**Temperature Monitoring:**
- Sensors: [locations]
- Fan Control: [PWM headers count]
- Voltage Monitoring: [rails monitored]
- Monitoring Chip: [IC model]

### Connectivity Matrix

```
PCIe Slot Layout:
Slot 1: PCIe 4.0 x16 (CPU) → [GPU installed]
Slot 2: PCIe 4.0 x16 (runs at x4, chipset) → [empty]
Slot 3: PCIe 3.0 x1 (chipset) → [WiFi card]
M.2_1:  PCIe 4.0 x4 (CPU) → [NVMe SSD]
M.2_2:  PCIe 3.0 x4 (chipset) → [empty]

Storage Ports:
SATA0-SATA3: [devices]
SATA4-SATA7: [empty]
```

### Upgrade and Expansion Potential

- Available PCIe slots: [count and type]
- Available M.2 slots: [count]
- RAM expansion: [X GB current / Y GB max]
- Storage expansion: [available ports]
- BIOS updates: [status]

### AI-Readable JSON

```json
{
  "board": {
    "manufacturer": "",
    "product_name": "",
    "version": "",
    "serial_number": "",
    "form_factor": "ATX|mATX|ITX|EATX"
  },
  "chipset": {
    "manufacturer": "intel|amd",
    "model": "",
    "revision": ""
  },
  "bios": {
    "type": "BIOS|UEFI",
    "vendor": "",
    "version": "",
    "release_date": "",
    "secure_boot": false
  },
  "expansion_slots": {
    "pcie_x16": [
      {
        "slot_number": 1,
        "generation": "3.0|4.0|5.0",
        "lanes": 16,
        "occupied": true,
        "device": ""
      }
    ],
    "pcie_x1": 0,
    "m2_slots": 0
  },
  "storage": {
    "sata_ports": 0,
    "sata_generation": "II|III",
    "nvme_slots": 0,
    "raid_support": []
  },
  "io": {
    "usb": {
      "usb_2_0": 0,
      "usb_3_0": 0,
      "usb_3_1": 0,
      "usb_3_2": 0,
      "usb_c": 0
    },
    "ethernet_ports": 0,
    "wifi": false,
    "bluetooth": false
  },
  "audio": {
    "codec": "",
    "channels": ""
  },
  "power": {
    "vrm_phases": 0,
    "fan_headers": 0,
    "rgb_headers": 0
  },
  "memory": {
    "dimm_slots": 0,
    "max_capacity_gb": 0,
    "type": "DDR4|DDR5",
    "max_speed_mts": 0,
    "ecc_support": false
  },
  "features": {
    "tpm": "",
    "bios_flashback": false,
    "dual_bios": false,
    "post_code_display": false
  }
}
```

## Execution Guidelines

1. **Use dmidecode extensively**: Primary source for board info
2. **Cross-reference with lspci**: Verify chipset and slots
3. **Check physical vs. logical**: Some slots share lanes
4. **Document slot usage**: What's installed where
5. **Identify chipset features**: What the board can do
6. **BIOS version importance**: Check for updates
7. **Expansion planning**: Available upgrade paths
8. **Power delivery assessment**: Adequacy for components
9. **I/O inventory**: Complete port count
10. **Format comprehensively**: Present all findings clearly

## Important Notes

- Requires root/sudo for most detailed information
- dmidecode is the primary tool for board identification
- Some data may not be available in virtual machines
- BIOS version is critical for compatibility and security
- PCIe lane sharing is common on consumer boards
- M.2 slots may disable SATA ports when used
- Form factor determines case compatibility
- VRM quality affects overclocking and stability
- TPM may require BIOS enablement
- UEFI vs. Legacy affects boot configuration
- Some features require specific BIOS settings
- Motherboard manual provides definitive specifications

Be extremely thorough - document every aspect of the motherboard.
