# List Connected Displays

You are helping the user identify all connected displays and their current configurations.

## Task

1. **Detect display server** (Wayland vs X11):
   ```bash
   echo $XDG_SESSION_TYPE
   ```

2. **For Wayland systems:**
   ```bash
   # Using kscreen-doctor (KDE)
   kscreen-doctor -o

   # Using wlr-randr (wlroots-based compositors)
   wlr-randr

   # Using gnome-randr (GNOME)
   gnome-randr
   ```

3. **For X11 systems:**
   ```bash
   xrandr --query
   ```

4. **Get detailed information:**
   ```bash
   # List all display devices
   ls /sys/class/drm/card*/card*/status

   # Check connected displays
   for p in /sys/class/drm/card*/card*/status; do
     echo "$(dirname $p): $(cat $p)"
   done
   ```

5. **Show current resolution and refresh rate:**
   ```bash
   # X11
   xrandr | grep -E "^[^ ]|[0-9]+\.[0-9]+\*"

   # Wayland (KDE)
   kscreen-doctor -j | jq -r '.outputs[] | "\(.name): \(.currentMode.size.width)x\(.currentMode.size.height)@\(.currentMode.refreshRate)Hz"'
   ```

## Present to User

Summarize the findings:
- Number of connected displays
- Display names/identifiers
- Current resolution and refresh rate for each
- Primary display
- Display position/arrangement
- Whether using Wayland or X11

## Additional Information

If requested, also show:
- Supported resolutions and refresh rates
- Display manufacturer and model (from EDID)
- Connection type (HDMI, DisplayPort, etc.)
- Color depth and color space

## Notes

- Command availability depends on desktop environment and display server
- KDE Plasma uses kscreen-doctor
- GNOME may use different tools
- Some information requires parsing EDID data from `/sys/class/drm/`
