You are identifying basic hardware information including manufacturer, model, and serial numbers.

## Your Task

Extract and display system identification information:

### 1. System Identity
- **Manufacturer**: System/chassis manufacturer
- **Product name**: System model/product name
- **Serial number**: System serial number
- **UUID**: System UUID
- **SKU**: Stock keeping unit number (if available)

### 2. Motherboard Identity
- **Manufacturer**: Board manufacturer
- **Product name**: Board model
- **Serial number**: Board serial number
- **Version**: Board version/revision

### 3. BIOS/UEFI Identity
- **Vendor**: BIOS manufacturer
- **Version**: BIOS version
- **Release date**: BIOS release date
- **Revision**: Firmware revision

### 4. Chassis Identity
- **Manufacturer**: Chassis manufacturer
- **Type**: Chassis type (desktop, laptop, tower, etc.)
- **Serial number**: Chassis serial number
- **Asset tag**: Asset tag (if configured)

## Commands to Use

**Primary identification:**
- `sudo dmidecode -t system`
- `sudo dmidecode -t baseboard`
- `sudo dmidecode -t bios`
- `sudo dmidecode -t chassis`

**Additional information:**
- `hostnamectl` - System hostname and other details
- `cat /sys/class/dmi/id/product_name`
- `cat /sys/class/dmi/id/sys_vendor`
- `cat /sys/class/dmi/id/board_vendor`
- `cat /sys/class/dmi/id/bios_version`

**Hardware summary:**
- `sudo lshw -short` - Quick hardware overview
- `inxi -M` - Machine data (if available)

## Output Format

Present a clean identification card format:

```
=============================================================================
                        HARDWARE IDENTIFICATION
=============================================================================

SYSTEM INFORMATION
------------------
Manufacturer:     [vendor]
Product Name:     [model]
Serial Number:    [S/N]
UUID:             [uuid]
SKU Number:       [sku]

MOTHERBOARD INFORMATION
-----------------------
Manufacturer:     [vendor]
Product Name:     [model]
Version:          [version]
Serial Number:    [S/N]

BIOS/UEFI INFORMATION
---------------------
Vendor:           [vendor]
Version:          [version]
Release Date:     [date]
Firmware Revision: [revision]

CHASSIS INFORMATION
-------------------
Manufacturer:     [vendor]
Type:             [type]
Serial Number:    [S/N]
Asset Tag:        [tag]

=============================================================================
```

### JSON Format (AI-Readable)

```json
{
  "system": {
    "manufacturer": "",
    "product_name": "",
    "serial_number": "",
    "uuid": "",
    "sku": ""
  },
  "motherboard": {
    "manufacturer": "",
    "product_name": "",
    "version": "",
    "serial_number": ""
  },
  "bios": {
    "vendor": "",
    "version": "",
    "release_date": "",
    "revision": ""
  },
  "chassis": {
    "manufacturer": "",
    "type": "",
    "serial_number": "",
    "asset_tag": ""
  }
}
```

## Execution Guidelines

1. **Use sudo**: dmidecode requires root privileges
2. **Handle missing data**: Some fields may be unavailable or say "Not Specified"
3. **Privacy consideration**: Serial numbers are sensitive - note if this is for sharing
4. **Validate output**: Cross-check using multiple methods
5. **Format cleanly**: Align fields for easy reading

## Important Notes

- Virtual machines may show generic or missing hardware IDs
- Some manufacturers don't populate all DMI fields
- Serial numbers should be handled with care for security/privacy
- Asset tags are typically only set in enterprise environments

Be concise and present only the identification information requested.
