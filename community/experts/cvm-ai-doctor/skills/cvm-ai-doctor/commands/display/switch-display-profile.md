# Switch Display Profile

You are helping the user switch between different display configurations/profiles (e.g., docked, laptop only, presentation).

## Task

1. **Check current display setup:**
   ```bash
   # Display server type
   echo $XDG_SESSION_TYPE

   # Connected displays
   kscreen-doctor -o  # KDE/Wayland
   # OR
   xrandr --query  # X11
   ```

2. **Ask user which profile they want:**
   - **Laptop only** (internal display only)
   - **Docked** (external monitors only or primary external)
   - **Extended** (laptop + external monitors)
   - **Mirrored** (same output on all displays)
   - **Presentation** (external display as primary)
   - **Custom** (user-defined configuration)

3. **KDE Plasma - Use saved profiles:**
   ```bash
   # List saved display configurations
   ls ~/.local/share/kscreen/

   # KDE automatically switches profiles based on connected displays
   # Force reload configuration
   kscreen-doctor --reload
   ```

4. **Create/Use autorandr (X11):**
   ```bash
   # Install if not present
   sudo apt install autorandr

   # Save current configuration as profile
   autorandr --save profile-name

   # Switch to saved profile
   autorandr --load profile-name

   # Auto-detect and load appropriate profile
   autorandr --change
   ```

5. **Manual X11 configuration examples:**

   **Laptop only:**
   ```bash
   xrandr --output eDP-1 --auto --primary \
          --output HDMI-1 --off \
          --output DP-1 --off
   ```

   **Docked (external monitors only):**
   ```bash
   xrandr --output eDP-1 --off \
          --output HDMI-1 --auto --primary \
          --output DP-1 --auto --right-of HDMI-1
   ```

   **Extended (laptop + external):**
   ```bash
   xrandr --output eDP-1 --auto \
          --output HDMI-1 --auto --primary --above eDP-1
   ```

   **Mirrored:**
   ```bash
   xrandr --output eDP-1 --auto \
          --output HDMI-1 --auto --same-as eDP-1
   ```

6. **Wayland/KDE configuration:**
   ```bash
   # Laptop only
   kscreen-doctor output.eDP-1.enable \
                  output.HDMI-1.disable \
                  output.DP-1.disable

   # Docked
   kscreen-doctor output.eDP-1.disable \
                  output.HDMI-1.enable output.HDMI-1.primary \
                  output.DP-1.enable output.DP-1.position.1920,0

   # Extended
   kscreen-doctor output.eDP-1.enable \
                  output.HDMI-1.enable output.HDMI-1.primary \
                  output.HDMI-1.position.0,-1080
   ```

7. **Create quick-switch scripts:**
   ```bash
   # Create scripts directory
   mkdir -p ~/.local/bin/display-profiles

   # Example: Laptop only script
   cat > ~/.local/bin/display-profiles/laptop-only.sh << 'EOF'
   #!/bin/bash
   xrandr --output eDP-1 --auto --primary \
          --output HDMI-1 --off \
          --output DP-1 --off
   notify-send "Display Profile" "Switched to: Laptop Only"
   EOF

   chmod +x ~/.local/bin/display-profiles/laptop-only.sh
   ```

8. **Create keyboard shortcuts (KDE):**
   ```bash
   # Add custom shortcut
   kwriteconfig6 --file kglobalshortcutsrc \
                 --group "Display Profile - Laptop" \
                 --key "_k_friendly_name" "Laptop Display Only"
   ```

9. **Automatic profile switching with udev:**
   ```bash
   # Create udev rule for auto-switching when docking
   sudo tee /etc/udev/rules.d/95-monitor-hotplug.rules << 'EOF'
   ACTION=="change", SUBSYSTEM=="drm", RUN+="/usr/local/bin/display-switch.sh"
   EOF

   # Create switch script
   sudo tee /usr/local/bin/display-switch.sh << 'EOF'
   #!/bin/bash
   export DISPLAY=:0
   export XAUTHORITY=/home/daniel/.Xauthority
   /usr/bin/autorandr --change
   EOF

   sudo chmod +x /usr/local/bin/display-switch.sh
   sudo udevadm control --reload-rules
   ```

## Verify Configuration

- Check display arrangement with GUI or commands
- Test window movement between displays
- Verify primary display setting
- Check resolution and refresh rates
- Test systray/panel positioning

## Troubleshooting

**Profile not loading:**
- Verify display names with `xrandr` or `kscreen-doctor -o`
- Check saved profile files
- Ensure all referenced displays are connected

**Automatic switching not working:**
- Check udev rule syntax
- Verify script permissions and paths
- Check logs: `journalctl -f` while connecting/disconnecting displays

**Black screen after switching:**
- Use Ctrl+Alt+F2 to access TTY
- Reset display configuration: `xrandr --auto`
- Restart display manager: `sudo systemctl restart sddm` (or gdm, lightdm)

## Notes

- autorandr is the most reliable tool for X11 profile management
- KDE Plasma handles profile switching automatically on Wayland
- Save profiles for different scenarios (home office, conference room, etc.)
- Consider using descriptive names for profiles
- Test profiles before relying on them for important presentations
