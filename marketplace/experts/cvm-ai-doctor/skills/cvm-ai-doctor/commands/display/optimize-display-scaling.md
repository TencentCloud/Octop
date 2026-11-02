# Optimize Display Scaling

You are helping the user configure HiDPI scaling and fractional scaling for optimal display clarity.

## Task

1. **Check current display information:**
   ```bash
   # Display server type
   echo $XDG_SESSION_TYPE

   # Current resolution and size
   kscreen-doctor -o  # Wayland/KDE
   # OR
   xrandr --query  # X11

   # Calculate DPI
   xdpyinfo | grep -B 2 resolution  # X11
   ```

2. **Determine optimal scaling:**
   - Display resolution
   - Physical size (diagonal in inches)
   - Calculate PPI: `sqrt(width² + height²) / diagonal_inches`
   - Recommended scaling:
     - PPI < 110: 100% (1x)
     - PPI 110-140: 125% (1.25x)
     - PPI 140-180: 150% (1.5x)
     - PPI 180-220: 200% (2x)
     - PPI > 220: 250% or higher

3. **For KDE Plasma (Wayland or X11):**
   ```bash
   # Set global scale factor (Wayland)
   kscreen-doctor output.DP-1.scale.1.5

   # Or use GUI
   kcmshell6 kcm_kscreen
   ```

   **Via settings file:**
   ```bash
   # Edit KDE scaling
   kwriteconfig6 --file kdeglobals --group KScreen --key ScaleFactor 1.5
   kquitapp6 plasmashell && kstart plasmashell
   ```

4. **For GNOME (Wayland):**
   ```bash
   # Enable fractional scaling
   gsettings set org.gnome.mutter experimental-features "['scale-monitor-framebuffer']"

   # Set scale factor (200% = 2.0)
   gsettings set org.gnome.desktop.interface scaling-factor 2
   ```

5. **For X11 systems (general):**
   ```bash
   # Set Xft DPI
   echo "Xft.dpi: 144" >> ~/.Xresources
   xrdb -merge ~/.Xresources

   # Set scale factor for Qt applications
   export QT_SCALE_FACTOR=1.5

   # Set scale factor for GTK applications
   export GDK_SCALE=2
   export GDK_DPI_SCALE=0.5
   ```

6. **Configure per-application scaling:**
   ```bash
   # For specific Qt apps
   QT_SCALE_FACTOR=1.5 application-name

   # Add to .bashrc or application launcher
   echo 'export QT_SCALE_FACTOR=1.5' >> ~/.bashrc
   ```

7. **Adjust font DPI:**
   ```bash
   # KDE
   kwriteconfig6 --file kcmfonts --group General --key forceFontDPI 144

   # GNOME
   gsettings set org.gnome.desktop.interface text-scaling-factor 1.25
   ```

8. **Handle cursor size:**
   ```bash
   # Set cursor size
   gsettings set org.gnome.desktop.interface cursor-size 32  # GNOME
   kwriteconfig6 --file kcminputrc --group Mouse --key cursorSize 32  # KDE
   ```

## Verify Configuration

1. **Check current settings:**
   ```bash
   echo $QT_SCALE_FACTOR
   echo $GDK_SCALE
   gsettings get org.gnome.desktop.interface scaling-factor  # GNOME
   ```

2. **Test applications:**
   - Open various applications (browser, terminal, file manager)
   - Check text clarity
   - Verify UI element sizes
   - Test both Qt and GTK applications

3. **Log out and back in** to apply system-wide changes

## Troubleshooting

- **Blurry applications:** Some apps don't support fractional scaling on X11
- **Inconsistent scaling:** Mix of Qt and GTK apps may scale differently
- **Wayland vs X11:** Wayland generally handles fractional scaling better
- **XWayland apps:** May appear blurry on Wayland with fractional scaling

**Solutions:**
```bash
# Force XWayland scaling
kwriteconfig6 --file kwinrc --group Xwayland --key Scale 1.5

# Disable fractional scaling for specific apps
env QT_SCALE_FACTOR=1 application-name
```

## Notes

- Wayland provides better fractional scaling support than X11
- Some applications may require restart to apply scaling
- Integer scaling (1x, 2x) is sharper than fractional (1.25x, 1.5x)
- Consider display distance when choosing scale factor
- Multi-monitor setups with different DPI may require per-monitor scaling
