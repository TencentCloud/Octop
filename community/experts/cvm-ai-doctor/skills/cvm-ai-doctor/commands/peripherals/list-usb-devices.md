# List USB Devices

You are helping the user view all connected USB devices with detailed information.

## Task

1. **Basic USB device listing:**
   ```bash
   # Simple list
   lsusb

   # With tree structure showing hubs
   lsusb -t

   # Verbose output
   lsusb -v | less
   ```

2. **Detailed information for each device:**
   ```bash
   # Iterate through all devices
   for device in $(lsusb | awk '{print $2":"$4}' | sed 's/:$//' | tr ':' '/'); do
     bus=$(echo $device | cut -d'/' -f1)
     dev=$(echo $device | cut -d'/' -f2)
     echo "=== Device: Bus $bus Device $dev ==="
     lsusb -v -s $bus:$dev 2>/dev/null | head -30
     echo ""
   done
   ```

3. **Show USB devices by type:**
   ```bash
   echo "=== Input Devices (Keyboards, Mice) ==="
   lsusb | grep -iE "keyboard|mouse|input"

   echo -e "\n=== Storage Devices ==="
   lsusb | grep -iE "storage|disk|flash|card reader"

   echo -e "\n=== Audio Devices ==="
   lsusb | grep -iE "audio|sound|headset|microphone"

   echo -e "\n=== Video Devices ==="
   lsusb | grep -iE "camera|video|webcam"

   echo -e "\n=== Bluetooth Adapters ==="
   lsusb | grep -i bluetooth

   echo -e "\n=== Network Adapters ==="
   lsusb | grep -iE "network|ethernet|wifi|802.11"
   ```

4. **USB device details from sysfs:**
   ```bash
   # List all USB devices with details
   for dev in /sys/bus/usb/devices/*; do
     if [ -f "$dev/manufacturer" ] && [ -f "$dev/product" ]; then
       echo "Device: $(cat $dev/product 2>/dev/null)"
       echo "Manufacturer: $(cat $dev/manufacturer 2>/dev/null)"
       echo "Serial: $(cat $dev/serial 2>/dev/null)"
       echo "Speed: $(cat $dev/speed 2>/dev/null) Mbps"
       echo "---"
     fi
   done
   ```

5. **USB device mount points and block devices:**
   ```bash
   # Show USB storage devices
   lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,MODEL | grep -i usb

   # USB device names in /dev
   ls -l /dev/sd* /dev/nvme* 2>/dev/null | grep -E "^b"

   # Detailed block device info
   lsblk -f
   ```

6. **USB power consumption:**
   ```bash
   # Check power usage
   for device in /sys/bus/usb/devices/*/power/active_duration; do
     dev=$(dirname $(dirname $device))
     if [ -f "$dev/product" ]; then
       echo "$(cat $dev/product): Power: $(cat $dev/power/level) Active: $(cat $device)ms"
     fi
   done
   ```

7. **USB device speed and capabilities:**
   ```bash
   # USB version and speed
   for dev in /sys/bus/usb/devices/usb*; do
     echo "USB Bus $(basename $dev):"
     echo "  Version: $(cat $dev/version 2>/dev/null)"
     echo "  Speed: $(cat $dev/speed 2>/dev/null) Mbps"
     echo "  Max Child: $(cat $dev/maxchild 2>/dev/null) ports"
     echo ""
   done
   ```

8. **Create formatted device report:**
   ```bash
   cat > /tmp/usb-devices.txt << EOF
   USB Devices Report
   ==================
   Generated: $(date)
   Hostname: $(hostname)

   === Connected USB Devices ===
   EOF

   lsusb >> /tmp/usb-devices.txt
   echo -e "\n=== USB Device Tree ===" >> /tmp/usb-devices.txt
   lsusb -t >> /tmp/usb-devices.txt

   echo -e "\n=== USB Storage Devices ===" >> /tmp/usb-devices.txt
   lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,MODEL | grep -i usb >> /tmp/usb-devices.txt

   echo -e "\n=== USB Device Details ===" >> /tmp/usb-devices.txt
   usb-devices >> /tmp/usb-devices.txt

   cat /tmp/usb-devices.txt
   ```

9. **Check USB controller info:**
   ```bash
   # List USB controllers
   lspci | grep -i usb

   # Detailed controller info
   for controller in $(lspci | grep -i usb | cut -d' ' -f1); do
     echo "=== Controller $controller ==="
     lspci -v -s $controller | head -20
     echo ""
   done
   ```

10. **Monitor USB events in real-time:**
    ```bash
    # Watch for USB connect/disconnect
    udevadm monitor --subsystem-match=usb

    # Or use dmesg
    dmesg -w | grep -i usb
    ```

11. **Check USB autosuspend settings:**
    ```bash
    # Check which devices have autosuspend enabled
    for dev in /sys/bus/usb/devices/*/power/control; do
      device=$(dirname $(dirname $dev))
      if [ -f "$device/product" ]; then
        echo "$(cat $device/product): $(cat $dev)"
      fi
    done
    ```

12. **Find USB device by vendor/product ID:**
    ```bash
    # Search by ID
    # Example: Find device 046d:c52b
    lsusb -d 046d:c52b -v

    # Find all devices from vendor
    lsusb -d 046d: # Logitech devices
    ```

13. **Check USB permissions:**
    ```bash
    # Show device permissions
    ls -l /dev/bus/usb/*/* | head -20

    # Find device files for specific bus
    ls -l /dev/bus/usb/001/

    # Check udev rules for USB
    ls -l /etc/udev/rules.d/*usb*
    ```

## Formatted Output

Create a nice summary:
```bash
cat > /tmp/usb-summary.sh << 'EOF'
#!/bin/bash

echo "╔════════════════════════════════════════════════════════╗"
echo "║          USB Devices Summary                           ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

echo "Total USB devices: $(lsusb | wc -l)"
echo ""

echo "--- By Type ---"
echo "Input devices: $(lsusb | grep -ciE 'keyboard|mouse|input')"
echo "Storage devices: $(lsusb | grep -ciE 'storage|disk|flash')"
echo "Audio devices: $(lsusb | grep -ci audio)"
echo "Video devices: $(lsusb | grep -ciE 'camera|video')"
echo "Network devices: $(lsusb | grep -ciE 'network|ethernet|wifi')"
echo "Bluetooth adapters: $(lsusb | grep -ci bluetooth)"
echo ""

echo "--- USB Controllers ---"
lspci | grep -i usb
echo ""

echo "--- Storage Devices ---"
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT | grep -A 10 -E "^sd|^nvme"
echo ""

echo "--- Recent USB Events ---"
journalctl -k --since "1 hour ago" | grep -i usb | tail -10

EOF

chmod +x /tmp/usb-summary.sh
bash /tmp/usb-summary.sh
```

## Troubleshooting

**Device not detected:**
```bash
# Check kernel messages
dmesg | grep -i usb | tail -20

# Check if ports working
cat /sys/kernel/debug/usb/devices

# Rescan USB bus
echo 1 | sudo tee /sys/bus/pci/rescan
```

**Device keeps disconnecting:**
```bash
# Disable autosuspend for problematic device
# Find device path
device_path=$(find /sys/bus/usb/devices/ -name "DEVICE_NAME*")

# Disable autosuspend
echo 'on' | sudo tee $device_path/power/control
```

**Permission denied:**
```bash
# Add user to plugdev group
sudo usermod -aG plugdev $USER

# Create udev rule for device
# /etc/udev/rules.d/50-mydevice.rules
# SUBSYSTEM=="usb", ATTR{idVendor}=="1234", ATTR{idProduct}=="5678", MODE="0666"
```

## Export Device Information

```bash
# Create detailed report
usb-devices > ~/usb-devices-$(date +%Y%m%d).txt

# Or with lsusb
lsusb -v > ~/usb-devices-verbose-$(date +%Y%m%d).txt
```

## Notes

- USB 1.1: 12 Mbps (Full Speed)
- USB 2.0: 480 Mbps (High Speed)
- USB 3.0: 5 Gbps (SuperSpeed)
- USB 3.1: 10 Gbps (SuperSpeed+)
- USB 3.2: 20 Gbps
- USB 4.0: 40 Gbps

- Vendor ID format: `046d` (Logitech), `8086` (Intel), etc.
- Product ID format: `c52b` (specific device model)
- USB device path: `/dev/bus/usb/BUS/DEVICE`
- Use `usbutils` package for lsusb and usb-devices commands
