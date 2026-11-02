# Troubleshoot Bluetooth

You are helping the user diagnose and fix Bluetooth connectivity issues.

## Task

1. **Check Bluetooth service status:**
   ```bash
   # Service status
   systemctl status bluetooth

   # Is it running?
   systemctl is-active bluetooth

   # Is it enabled to start on boot?
   systemctl is-enabled bluetooth
   ```

2. **Check Bluetooth hardware:**
   ```bash
   # List Bluetooth adapters
   hciconfig -a

   # Or using rfkill
   rfkill list bluetooth

   # Check if Bluetooth is soft/hard blocked
   rfkill list

   # Detailed hardware info
   lsusb | grep -i bluetooth
   lspci | grep -i bluetooth
   ```

3. **Check Bluetooth controller status:**
   ```bash
   # Controller info
   bluetoothctl show

   # List controllers
   bluetoothctl list

   # Check if powered on
   bluetoothctl show | grep "Powered:"
   ```

4. **Check for firmware issues:**
   ```bash
   # Look for firmware errors in journal
   journalctl -u bluetooth | grep -i firmware

   # Check dmesg for Bluetooth firmware loading
   dmesg | grep -i "bluetooth\|firmware" | tail -20

   # Check kernel modules
   lsmod | grep bluetooth
   ```

5. **Common fixes - Restart Bluetooth:**
   ```bash
   # Restart Bluetooth service
   sudo systemctl restart bluetooth

   # Reset Bluetooth controller
   sudo hciconfig hci0 down
   sudo hciconfig hci0 up

   # Or use bluetoothctl
   bluetoothctl power off
   sleep 2
   bluetoothctl power on
   ```

6. **Unblock Bluetooth if blocked:**
   ```bash
   # Check if blocked
   rfkill list bluetooth

   # Unblock if soft-blocked
   sudo rfkill unblock bluetooth

   # Power on controller
   bluetoothctl power on
   ```

7. **Scan for devices:**
   ```bash
   # Start scanning
   bluetoothctl scan on

   # Wait 10 seconds
   sleep 10

   # List discovered devices
   bluetoothctl devices

   # Stop scanning
   bluetoothctl scan off
   ```

8. **Check paired devices:**
   ```bash
   # List paired devices
   bluetoothctl paired-devices

   # Show info about specific device
   bluetoothctl info DEVICE_MAC_ADDRESS
   ```

9. **Remove and re-pair problematic device:**
   ```bash
   # Ask user for device MAC address
   # Remove device
   bluetoothctl remove DEVICE_MAC_ADDRESS

   # Scan again
   bluetoothctl scan on
   sleep 10

   # Pair device
   bluetoothctl pair DEVICE_MAC_ADDRESS

   # Trust device
   bluetoothctl trust DEVICE_MAC_ADDRESS

   # Connect to device
   bluetoothctl connect DEVICE_MAC_ADDRESS
   ```

10. **Check Bluetooth configuration:**
    ```bash
    # Main config file
    cat /etc/bluetooth/main.conf

    # Check for problematic settings
    grep -E "^(Name|Class|DiscoverableTimeout|AutoEnable)" /etc/bluetooth/main.conf
    ```

11. **Check for interference:**
    ```bash
    # Check WiFi and Bluetooth coexistence
    iw dev | grep -i channel

    # Bluetooth operates on 2.4GHz
    # WiFi on 2.4GHz can interfere
    echo "Consider switching WiFi to 5GHz if available"
    ```

12. **Detailed diagnostics:**
    ```bash
    # Bluetooth subsystem logs
    journalctl -u bluetooth --since "1 hour ago" --no-pager

    # Kernel Bluetooth messages
    dmesg | grep -i bluetooth | tail -30

    # Check for errors
    journalctl -u bluetooth | grep -iE "error|fail|timeout"
    ```

13. **Audio-specific Bluetooth issues:**
    ```bash
    # Check PulseAudio/PipeWire Bluetooth modules
    pactl list | grep -i bluetooth

    # PipeWire Bluetooth
    pw-cli ls Device | grep -i bluetooth

    # Load Bluetooth module (PulseAudio)
    # pactl load-module module-bluetooth-discover

    # Restart audio with Bluetooth
    systemctl --user restart pipewire pipewire-pulse wireplumber
    ```

14. **Generate diagnostic report:**
    ```bash
    cat > /tmp/bluetooth-diagnostic.txt << EOF
    Bluetooth Diagnostic Report
    ===========================
    Date: $(date)

    === Service Status ===
    $(systemctl status bluetooth --no-pager)

    === Hardware Detection ===
    $(rfkill list bluetooth)
    $(hciconfig -a)

    === Controller Info ===
    $(bluetoothctl show)

    === Paired Devices ===
    $(bluetoothctl paired-devices)

    === Recent Bluetooth Logs ===
    $(journalctl -u bluetooth --since "1 hour ago" --no-pager | tail -50)

    === Kernel Messages ===
    $(dmesg | grep -i bluetooth | tail -30)

    === Loaded Modules ===
    $(lsmod | grep bluetooth)

    === Configuration ===
    $(grep -v "^#\|^$" /etc/bluetooth/main.conf)
    EOF

    cat /tmp/bluetooth-diagnostic.txt
    ```

## Common Issues & Solutions

**Bluetooth not starting:**
```bash
# Check if service masked
systemctl unmask bluetooth
sudo systemctl enable --now bluetooth
```

**Device pairs but won't connect:**
```bash
# Remove and re-pair
bluetoothctl remove DEVICE_MAC
bluetoothctl scan on
# Wait for device to appear
bluetoothctl pair DEVICE_MAC
bluetoothctl trust DEVICE_MAC
bluetoothctl connect DEVICE_MAC
```

**Audio stuttering or quality issues:**
```bash
# Check Bluetooth audio codec
pactl list | grep -i "bluetooth\|codec"

# Try different codec
# Edit /etc/bluetooth/main.conf
# [General]
# Enable=Source,Sink,Media,Socket
```

**Bluetooth adapter not found:**
```bash
# Reload Bluetooth module
sudo rmmod btusb
sudo modprobe btusb

# Or all Bluetooth modules
sudo rmmod bnep btusb bluetooth
sudo modprobe bluetooth
sudo modprobe btusb
sudo modprobe bnep
```

**Random disconnections:**
```bash
# Increase page timeout
sudo hciconfig hci0 pageto 8192

# Disable power management for USB Bluetooth
# Add to /etc/udev/rules.d/50-bluetooth.rules:
# ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="YOUR_VENDOR", ATTR{power/autosuspend}="-1"
```

**LE (Low Energy) devices not working:**
```bash
# Enable LE in bluetoothctl
bluetoothctl
[bluetooth]# menu scan
[bluetooth]# transport le
[bluetooth]# scan on
```

## Reset Bluetooth Completely

If nothing else works:
```bash
# Stop Bluetooth
sudo systemctl stop bluetooth

# Remove paired devices cache
sudo rm -rf /var/lib/bluetooth/*

# Restart Bluetooth
sudo systemctl start bluetooth

# Re-pair all devices
```

## Notes

- Most Bluetooth adapters work with btusb kernel module
- Firmware files typically in `/lib/firmware/`
- Check if kernel has Bluetooth support: `zgrep BLUETOOTH /proc/config.gz`
- Some devices require specific pairing codes
- Audio devices may need PulseAudio/PipeWire Bluetooth modules
- USB Bluetooth adapters: check with `usb-devices | grep -A 10 Bluetooth`
- Bluetooth 5.x adapters are backward compatible with older devices
- Distance and obstacles affect connection quality
