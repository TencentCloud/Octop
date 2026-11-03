# Setup Multi-Monitor Configuration

You are helping the user configure multiple monitors on their Linux desktop.

## Task

1. **Detect current setup:**
   ```bash
   # Check display server type
   echo $XDG_SESSION_TYPE

   # List connected displays
   kscreen-doctor -o  # KDE/Wayland
   # OR
   xrandr --query  # X11
   ```

2. **Ask the user about their desired configuration:**
   - Which display should be primary?
   - How should displays be arranged? (left-of, right-of, above, below, mirrored)
   - What resolution for each display?
   - What refresh rate for each display?

3. **For X11 systems using xrandr:**
   ```bash
   # Example: Two monitors side by side
   xrandr --output HDMI-1 --mode 1920x1080 --rate 60 \
          --output DP-1 --mode 2560x1440 --rate 144 --right-of HDMI-1 --primary

   # Example: Mirror displays
   xrandr --output HDMI-1 --mode 1920x1080 \
          --output DP-1 --same-as HDMI-1 --mode 1920x1080
   ```

4. **For Wayland/KDE systems using kscreen-doctor:**
   ```bash
   # Example: Configure displays
   kscreen-doctor output.HDMI-1.mode.1920x1080@60 \
                  output.DP-1.mode.2560x1440@144 \
                  output.DP-1.position.1920,0 \
                  output.DP-1.primary
   ```

5. **For GNOME (Wayland):**
   ```bash
   # Use gnome-control-center or gnome-randr
   gnome-randr modify DP-1 --mode 2560x1440 --rate 144 --primary --pos 1920x0
   ```

6. **Make configuration persistent:**

   **X11:**
   - Configuration is typically saved by the desktop environment
   - Can add xrandr commands to `~/.xprofile` or startup scripts

   **Wayland/KDE:**
   - KDE saves configuration automatically in `~/.local/share/kscreen/`

   **Create startup script if needed:**
   ```bash
   # Create script
   cat > ~/.config/autostart-scripts/monitor-setup.sh << 'EOF'
   #!/bin/bash
   # Monitor setup commands here
   EOF

   chmod +x ~/.config/autostart-scripts/monitor-setup.sh
   ```

7. **Test and verify:**
   - Check if all displays are showing correctly
   - Verify resolution and refresh rates
   - Test primary display setting
   - Check display arrangement by moving windows

## Troubleshooting

If issues occur:
- Check if displays are detected: `xrandr --listmonitors` or `kscreen-doctor -o`
- Verify supported modes for each display
- Try lower refresh rates if displays flicker
- Check cable connections and quality
- Look for errors in logs: `journalctl -b | grep -i drm`

## Notes

- Commands differ significantly between X11 and Wayland
- Desktop environment may provide GUI tools (System Settings)
- Some configurations may require restarting the display manager
- High refresh rates require appropriate cables (DisplayPort 1.4, HDMI 2.1)
