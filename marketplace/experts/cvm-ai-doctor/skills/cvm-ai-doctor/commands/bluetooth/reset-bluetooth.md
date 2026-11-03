# Reset Bluetooth

You are helping the user completely reset the Bluetooth subsystem to fix persistent issues.

## Task

**WARNING:** This will remove all paired Bluetooth devices and require re-pairing.

1. **Ask user to confirm:**
   - This will unpair all Bluetooth devices
   - Devices will need to be paired again
   - Bluetooth service will be restarted

2. **Stop Bluetooth service:**
   ```bash
   # Stop Bluetooth
   sudo systemctl stop bluetooth

   # Verify stopped
   systemctl is-active bluetooth
   ```

3. **Kill any remaining Bluetooth processes:**
   ```bash
   # Kill bluetoothd
   sudo killall bluetoothd 2>/dev/null

   # Kill bluetooth-related processes
   ps aux | grep bluetooth | grep -v grep
   sudo killall -9 bluez-alsa bluez-obexd 2>/dev/null
   ```

4. **Remove Bluetooth pairing cache:**
   ```bash
   # Remove paired devices database
   sudo rm -rf /var/lib/bluetooth/*

   # Show what was removed
   echo "Removed all paired device data from /var/lib/bluetooth/"
   ```

5. **Clear user Bluetooth cache:**
   ```bash
   # Remove user Bluetooth cache
   rm -rf ~/.cache/bluetooth 2>/dev/null
   rm -rf ~/.local/share/bluetooth 2>/dev/null

   echo "Cleared user Bluetooth cache"
   ```

6. **Reset Bluetooth modules:**
   ```bash
   # Remove Bluetooth kernel modules
   sudo modprobe -r bnep
   sudo modprobe -r bluetooth
   sudo modprobe -r btusb
   sudo modprobe -r btintel  # Intel Bluetooth
   sudo modprobe -r btrtl    # Realtek Bluetooth

   echo "Bluetooth modules unloaded"
   sleep 2
   ```

7. **Reload Bluetooth modules:**
   ```bash
   # Reload modules
   sudo modprobe bluetooth
   sudo modprobe btusb
   sudo modprobe bnep

   # Load vendor-specific modules if needed
   sudo modprobe btintel 2>/dev/null
   sudo modprobe btrtl 2>/dev/null

   echo "Bluetooth modules reloaded"
   ```

8. **Reset HCI interface:**
   ```bash
   # Bring down Bluetooth controller
   sudo hciconfig hci0 down 2>/dev/null

   sleep 1

   # Bring it back up
   sudo hciconfig hci0 up 2>/dev/null

   # Reset the controller
   sudo hciconfig hci0 reset 2>/dev/null

   echo "HCI interface reset"
   ```

9. **Unblock Bluetooth:**
   ```bash
   # Unblock Bluetooth (soft and hard)
   sudo rfkill unblock bluetooth

   # Verify not blocked
   rfkill list bluetooth
   ```

10. **Start Bluetooth service:**
    ```bash
    # Start and enable Bluetooth
    sudo systemctl start bluetooth
    sudo systemctl enable bluetooth

    # Wait for service to fully start
    sleep 3

    # Check status
    systemctl status bluetooth --no-pager
    ```

11. **Power on Bluetooth controller:**
    ```bash
    # Turn on Bluetooth
    bluetoothctl power on

    # Set as discoverable (optional)
    bluetoothctl discoverable on

    # Set pairable
    bluetoothctl pairable on

    # Show controller info
    bluetoothctl show
    ```

12. **Verify Bluetooth is working:**
    ```bash
    # Check service
    echo "Service status: $(systemctl is-active bluetooth)"

    # Check controller
    echo "Controller powered: $(bluetoothctl show | grep Powered)"

    # Check for adapters
    hciconfig -a

    # Start scanning to test
    echo "Starting scan for 10 seconds..."
    timeout 10 bluetoothctl scan on

    bluetoothctl devices
    ```

13. **Create reset report:**
    ```bash
    cat > /tmp/bluetooth-reset-report.txt << EOF
    Bluetooth Reset Report
    ======================
    Date: $(date)

    === Service Status ===
    $(systemctl status bluetooth --no-pager)

    === Controller Info ===
    $(bluetoothctl show)

    === Hardware Info ===
    $(hciconfig -a)

    === RF Kill Status ===
    $(rfkill list bluetooth)

    === Loaded Modules ===
    $(lsmod | grep -E "bluetooth|bnep|btusb")

    === Kernel Messages (last 20) ===
    $(dmesg | grep -i bluetooth | tail -20)

    Next Steps:
    1. Your Bluetooth has been reset
    2. All previous pairings have been removed
    3. Put your device in pairing mode
    4. Use: bluetoothctl scan on
    5. Use: bluetoothctl pair <DEVICE_MAC>
    6. Use: bluetoothctl connect <DEVICE_MAC>
    EOF

    cat /tmp/bluetooth-reset-report.txt
    ```

## USB Bluetooth Adapter Reset

If using USB Bluetooth adapter:
```bash
# Find USB Bluetooth device
usb_bt=$(lsusb | grep -i bluetooth | head -1)
echo "Found: $usb_bt"

# Get bus and device numbers
bus=$(echo $usb_bt | awk '{print $2}')
dev=$(echo $usb_bt | awk '{print $4}' | tr -d ':')

# Reset USB device
echo "Resetting USB device: Bus $bus Device $dev"
sudo usb_modeswitch -v 0x$(lsusb | grep -i bluetooth | awk '{print $6}' | cut -d: -f1) \
                     -p 0x$(lsusb | grep -i bluetooth | awk '{print $6}' | cut -d: -f2) \
                     --reset-usb 2>/dev/null

# Alternative: unbind and rebind
device_path="/sys/bus/usb/devices/$bus-*"
echo "Unbinding and rebinding USB device"
echo "$bus-*" | sudo tee /sys/bus/usb/drivers/usb/unbind 2>/dev/null
sleep 2
echo "$bus-*" | sudo tee /sys/bus/usb/drivers/usb/bind 2>/dev/null
```

## Firmware Reload

If firmware issues persist:
```bash
# Check firmware files
ls -l /lib/firmware/ | grep -i bluetooth

# Reload firmware (device-specific)
# For Intel Bluetooth:
sudo rmmod btintel
sudo modprobe btintel

# For Realtek:
sudo rmmod btrtl
sudo modprobe btrtl

# Check if firmware loaded
dmesg | grep -i "bluetooth.*firmware" | tail -5
```

## Complete System Reset

Nuclear option if nothing else works:
```bash
# Stop everything
sudo systemctl stop bluetooth
sudo killall -9 bluetoothd

# Remove all data
sudo rm -rf /var/lib/bluetooth/*
rm -rf ~/.cache/bluetooth
rm -rf ~/.local/share/bluetooth

# Remove and reload all modules
sudo modprobe -r bnep bluetooth btusb btintel btrtl
sleep 3
sudo modprobe bluetooth btusb bnep

# Remove config (will regenerate)
sudo mv /etc/bluetooth/main.conf /etc/bluetooth/main.conf.backup

# Reboot system
echo "A system reboot is recommended for complete reset"
# sudo reboot
```

## Post-Reset Pairing

Guide user through pairing:
```bash
cat << 'EOF'
To pair a device after reset:

1. Put device in pairing mode
2. Start Bluetooth scan:
   bluetoothctl scan on

3. Find your device MAC address in the list

4. Pair the device:
   bluetoothctl pair XX:XX:XX:XX:XX:XX

5. Trust the device:
   bluetoothctl trust XX:XX:XX:XX:XX:XX

6. Connect:
   bluetoothctl connect XX:XX:XX:XX:XX:XX

7. Stop scanning:
   bluetoothctl scan off

For audio devices, you may need to restart PipeWire:
   systemctl --user restart pipewire wireplumber
EOF
```

## Troubleshooting

**Reset didn't work:**
```bash
# Try full reboot
sudo reboot

# Or try removing Bluetooth packages and reinstalling
# sudo apt remove bluez bluetooth
# sudo apt install bluez bluetooth
```

**Service won't start:**
```bash
# Check for errors
journalctl -u bluetooth --since "5 minutes ago" --no-pager

# Check if masked
sudo systemctl unmask bluetooth

# Force restart
sudo systemctl restart bluetooth
```

**No adapters found:**
```bash
# Check hardware detection
lsusb | grep -i bluetooth
lspci | grep -i bluetooth

# Check kernel modules
lsmod | grep bluetooth
```

## Notes

- Backup `/var/lib/bluetooth/` before reset if you want to preserve pairings
- Some devices may require specific PIN codes during pairing
- Audio devices may need additional PipeWire/PulseAudio configuration
- Bluetooth 5.0+ devices are backward compatible
- LE (Low Energy) devices may require special pairing procedures
- System reboot recommended after complete reset
- Check `/var/log/syslog` for detailed Bluetooth errors
