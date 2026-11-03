---
description: Evaluate wake devices and help remove them for better hibernation
tags: [power, hibernation, wake-devices, optimization, project, gitignored]
---

You are helping the user evaluate and configure wake devices to improve hibernation/sleep behavior.

## Process

1. **Check current wake-enabled devices**
   - List devices that can wake system: `cat /proc/acpi/wakeup`
   - Show USB wake devices: `grep . /sys/bus/usb/devices/*/power/wakeup`
   - Check PCI wake devices: `grep . /sys/bus/pci/devices/*/power/wakeup`

2. **Identify wake sources**
   - Check what woke the system last: `journalctl -b -1 -n 50 | grep -i "wakeup\|wake"`
   - Review systemd sleep logs: `journalctl -u systemd-suspend -n 50`
   - Check for spurious wakeups

3. **Common wake device categories**
   - Keyboard/Mouse (USB devices)
   - Network cards (Ethernet/WiFi)
   - Bluetooth adapters
   - USB hubs
   - Audio devices
   - ACPI devices (power buttons, lid switches)

4. **Disable unnecessary wake devices**

   **Temporary (until reboot):**
   - Disable USB device: `echo disabled > /sys/bus/usb/devices/<device>/power/wakeup`
   - Disable ACPI: `echo disabled > /proc/acpi/wakeup`

   **Permanent (via udev rules):**
   - Create rule: `/etc/udev/rules.d/90-disable-wakeup.rules`
   - Example:
     ```
     # Disable USB wakeup for all USB devices except keyboard
     ACTION=="add", SUBSYSTEM=="usb", DRIVER=="usb", ATTR{power/wakeup}="disabled"
     ```

   **Via systemd service:**
   - Create: `/etc/systemd/system/disable-usb-wakeup.service`
   - Set wake devices on boot

5. **Test configuration**
   - Suspend system: `systemctl suspend`
   - Try to wake with various devices
   - Verify unwanted devices don't wake system

6. **Suggest optimal configuration**
   - Typically keep enabled:
     - Power button
     - Keyboard (if wired)
     - Laptop lid switch
   - Typically disable:
     - Mice
     - USB hubs
     - Network cards (unless Wake-on-LAN needed)
     - Bluetooth

7. **Create persistent configuration**
   - Offer to create udev rules
   - Offer to create systemd service
   - Provide script to restore settings on boot

## Output

Provide a report showing:
- Currently wake-enabled devices
- Devices that have caused wakeups
- Recommended devices to disable
- Configuration method (udev/systemd)
- Commands to apply changes
- How to test and verify
