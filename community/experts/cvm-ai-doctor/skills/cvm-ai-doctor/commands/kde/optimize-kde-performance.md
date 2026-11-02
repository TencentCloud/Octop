# Optimize KDE Performance

You are helping the user tune KDE Plasma settings for better performance and responsiveness.

## Task

1. **Check current performance baseline:**
   ```bash
   # CPU/RAM usage of KDE processes
   ps aux | grep -E "plasma|kwin" | grep -v grep

   # Memory usage
   free -h

   # KWin resource usage
   top -b -n 1 | grep -E "plasma|kwin"
   ```

2. **Disable unnecessary visual effects:**
   ```bash
   # Reduce KWin effects
   kwriteconfig6 --file kwinrc --group Plugins --key blurEnabled false
   kwriteconfig6 --file kwinrc --group Plugins --key contrastEnabled false
   kwriteconfig6 --file kwinrc --group Plugins --key slidebackEnabled false
   kwriteconfig6 --file kwinrc --group Plugins --key zoomEnabled false

   # Disable desktop effects for slower systems
   kwriteconfig6 --file kwinrc --group Compositing --key Enabled false

   # Or keep compositing but reduce effects
   kwriteconfig6 --file kwinrc --group Compositing --key AnimationSpeed 3

   # Restart KWin to apply
   qdbus org.kde.KWin /KWin reconfigure
   ```

3. **Optimize compositor settings:**
   ```bash
   # Use OpenGL 3.1 (faster than 2.0, more compatible than 3.1 Core)
   kwriteconfig6 --file kwinrc --group Compositing --key GLCore false
   kwriteconfig6 --file kwinrc --group Compositing --key GLPlatformInterface egl

   # Set rendering backend (EGL is usually faster)
   kwriteconfig6 --file kwinrc --group Compositing --key Backend OpenGL

   # Disable VSync for lower latency (may cause tearing)
   # kwriteconfig6 --file kwinrc --group Compositing --key GLPreferBufferSwap n

   # Or use adaptive VSync
   kwriteconfig6 --file kwinrc --group Compositing --key GLPreferBufferSwap a

   # Reduce latency
   kwriteconfig6 --file kwinrc --group Compositing --key LatencyControl false

   qdbus org.kde.KWin /KWin reconfigure
   ```

4. **Disable Baloo file indexing (if not needed):**
   ```bash
   # Disable Baloo
   balooctl disable

   # Stop Baloo service
   balooctl stop

   # Check status
   balooctl status

   # Or configure to index only specific folders
   balooctl config add /home/daniel/Documents
   balooctl enable
   ```

5. **Reduce desktop search scope:**
   ```bash
   # Configure Baloo to exclude large directories
   kwriteconfig6 --file baloofilerc --group "General" --key "exclude filters" "*.tmp,*.o,*.pyc"
   kwriteconfig6 --file baloofilerc --group "General" --key "folders[$e]" "$HOME/Downloads/,$HOME/.cache/,$HOME/.local/share/Trash/"

   balooctl restart
   ```

6. **Optimize Plasma widget performance:**
   ```bash
   # Disable weather widget auto-update
   kwriteconfig6 --file plasma-org.kde.plasma.desktop-appletsrc --group "Containments" --group "1" --group "Applets" --group "org.kde.plasma.weather" --key "updateInterval" 3600

   # Reduce system monitor update frequency
   # (Edit via GUI: Right-click widget -> Configure)
   ```

7. **Reduce animation speed or disable:**
   ```bash
   # Faster animations
   kwriteconfig6 --file kdeglobals --group KDE --key AnimationDurationFactor 0.5

   # Disable animations entirely
   kwriteconfig6 --file kdeglobals --group KDE --key AnimationDurationFactor 0

   # Apply changes
   kquitapp6 plasmashell && kstart plasmashell
   ```

8. **Optimize KWin window management:**
   ```bash
   # Disable window focus effects
   kwriteconfig6 --file kwinrc --group Plugins --key diminactiveEnabled false
   kwriteconfig6 --file kwinrc --group Plugins --key dimscreenEnabled false

   # Faster window switching
   kwriteconfig6 --file kwinrc --group TabBox --key DelayTime 0

   # Instant window placement
   kwriteconfig6 --file kwinrc --group Windows --key Placement Smart

   qdbus org.kde.KWin /KWin reconfigure
   ```

9. **Disable unnecessary Plasma features:**
   ```bash
   # Disable desktop thumbnails
   kwriteconfig6 --file kwinrc --group Plugins --key thumbnailasideEnabled false

   # Disable desktop grid effect
   kwriteconfig6 --file kwinrc --group Effect-DesktopGrid --key ShowAddRemove false

   # Disable magic lamp effect
   kwriteconfig6 --file kwinrc --group Plugins --key magiclampEnabled false

   qdbus org.kde.KWin /KWin reconfigure
   ```

10. **Configure KWin for better performance:**
    ```bash
    # Unredirect fullscreen windows (better gaming performance)
    kwriteconfig6 --file kwinrc --group Compositing --key UnredirectFullscreen true

    # Allow tearing for low latency
    kwriteconfig6 --file kwinrc --group Compositing --key AllowTearing true

    # Refresh rate (match your monitor)
    kwriteconfig6 --file kwinrc --group Compositing --key RefreshRate 0  # Auto-detect

    qdbus org.kde.KWin /KWin reconfigure
    ```

11. **Optimize system tray:**
    ```bash
    # Remove unnecessary system tray icons
    # (Done via GUI: Right-click system tray -> Configure System Tray -> Entries)

    # Check what's running in system tray
    qdbus | grep "org.kde.StatusNotifierItem"
    ```

12. **Reduce memory usage:**
    ```bash
    # Clear Plasma cache
    rm -rf ~/.cache/plasma*
    rm -rf ~/.cache/kwin*

    # Disable clipboard history
    kwriteconfig6 --file klipperrc --group General --key KeepClipboardContents false

    # Reduce clipboard history size
    kwriteconfig6 --file klipperrc --group General --key MaxClipItems 5
    ```

13. **Disable KDE Connect if not needed:**
    ```bash
    # Stop KDE Connect
    kdeconnect-cli --refresh
    systemctl --user stop kdeconnect
    systemctl --user disable kdeconnect
    ```

14. **Optimize font rendering:**
    ```bash
    # Disable font anti-aliasing for speed (not recommended for readability)
    # kwriteconfig6 --file kcmfonts --group General --key forceFontDPI 96

    # Use faster font rendering
    kwriteconfig6 --file kcmfonts --group General --key XftAntialias true
    kwriteconfig6 --file kcmfonts --group General --key XftHintStyle hintslight
    ```

15. **Monitor performance improvements:**
    ```bash
    # Before and after comparison
    echo "=== Plasma Performance ==="
    ps aux | grep plasmashell | grep -v grep | awk '{print "CPU: "$3"% RAM: "$4"%"}'

    echo "=== KWin Performance ==="
    ps aux | grep kwin | grep -v grep | awk '{print "CPU: "$3"% RAM: "$4"%"}'

    echo "=== Total KDE Memory Usage ==="
    ps aux | grep -E "plasma|kwin|kde" | awk '{sum+=$6} END {print sum/1024 " MB"}'
    ```

## Performance Testing

Create benchmark script:
```bash
cat > /tmp/kde-performance-test.sh << 'EOF'
#!/bin/bash

echo "KDE Performance Test"
echo "===================="
echo ""

# Test 1: Plasma shell responsiveness
echo "Test 1: Measuring Plasma restart time..."
start=$(date +%s%N)
kquitapp6 plasmashell && kstart plasmashell
sleep 3
end=$(date +%s%N)
echo "Plasma restart: $((($end-$start)/1000000)) ms"

# Test 2: KWin reconfigure time
echo "Test 2: Measuring KWin reconfigure time..."
start=$(date +%s%N)
qdbus org.kde.KWin /KWin reconfigure
end=$(date +%s%N)
echo "KWin reconfigure: $((($end-$start)/1000000)) ms"

# Test 3: Resource usage
echo "Test 3: Current resource usage..."
ps aux | grep -E "plasma|kwin" | grep -v grep | awk '{print $11 ": CPU="$3"% MEM="$4"%"}'

EOF

chmod +x /tmp/kde-performance-test.sh
/tmp/kde-performance-test.sh
```

## Revert to Defaults

If optimizations cause issues:
```bash
# Backup then remove KWin config
mv ~/.config/kwinrc ~/.config/kwinrc.optimized
kquitapp6 kwin_wayland && kstart kwin_wayland

# Reset Plasma config
mv ~/.config/plasmarc ~/.config/plasmarc.optimized
kquitapp6 plasmashell && kstart plasmashell

# Reset KDE globals
mv ~/.config/kdeglobals ~/.config/kdeglobals.optimized
```

## Hardware-Specific Optimizations

**For AMD GPUs:**
```bash
# Use AMDGPU backend
kwriteconfig6 --file kwinrc --group Compositing --key GLPlatformInterface egl

# Enable TearFree if tearing occurs
# (Set in xorg.conf or kernel parameters)
```

**For older/slower systems:**
```bash
# Minimal effects
kwriteconfig6 --file kwinrc --group Plugins --key kwin4_effect_translucyEnabled false
kwriteconfig6 --file kwinrc --group Plugins --key kwin4_effect_fadeEnabled false

# Disable compositing entirely
kwriteconfig6 --file kwinrc --group Compositing --key Enabled false
```

**For high-end systems:**
```bash
# Enable all effects
kwriteconfig6 --file kwinrc --group Compositing --key AnimationSpeed 1
kwriteconfig6 --file kwinrc --group Plugins --key blurEnabled true
```

## Notes

- Test changes one at a time to identify what helps
- Some changes require logging out/in to fully apply
- Disabling compositing may cause tearing and disable effects
- Baloo indexing can be heavy on CPU/disk during initial index
- Keep compositor enabled for VRR/FreeSync support
- Monitor GPU usage with `radeontop` or `nvidia-smi`
- Check KWin compositor info: `qdbus org.kde.KWin /KWin supportInformation`
