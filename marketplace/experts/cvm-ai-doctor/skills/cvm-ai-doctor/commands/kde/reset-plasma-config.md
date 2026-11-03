# Reset Plasma Configuration

You are helping the user reset corrupted or problematic KDE Plasma settings back to defaults.

## Task

**WARNING:** This will reset KDE customizations. Back up first if you want to preserve any settings.

1. **Ask user what to reset:**
   - Full Plasma reset (panels, desktop, all settings)
   - Plasma desktop and panels only
   - Specific application (Dolphin, Konsole, etc.)
   - Window manager (KWin) only
   - Shortcuts only

2. **Backup current configuration (recommended):**
   ```bash
   # Create backup before reset
   BACKUP_DIR=~/.kde-backups/pre-reset-$(date +%Y%m%d-%H%M%S)
   mkdir -p "$BACKUP_DIR"
   cp -r ~/.config/plasma* ~/.config/k* "$BACKUP_DIR/" 2>/dev/null
   echo "Backup created: $BACKUP_DIR"
   ```

3. **Full Plasma Reset:**
   ```bash
   # Stop Plasma
   kquitapp6 plasmashell

   # Remove Plasma configuration
   rm -rf ~/.config/plasma*
   rm ~/.config/plasmarc
   rm ~/.config/plasmashellrc

   # Remove desktop and panel configs
   rm -rf ~/.local/share/plasma
   rm -rf ~/.local/share/plasmashell

   # Optional: Reset KDE globals
   rm ~/.config/kdeglobals

   # Restart Plasma
   kstart plasmashell
   ```

4. **Reset Panels and Desktop Only:**
   ```bash
   # Stop Plasma
   kquitapp6 plasmashell

   # Remove panel and desktop layouts
   rm -rf ~/.config/plasma-org.kde.plasma.desktop-appletsrc
   rm -rf ~/.local/share/plasma/plasmoids
   rm -rf ~/.local/share/plasma/layout-templates

   # Restart Plasma
   kstart plasmashell
   ```

5. **Reset Window Manager (KWin):**
   ```bash
   # Stop KWin (will restart automatically)
   kwin_x11 --replace &  # For X11
   # OR
   kwin_wayland --replace &  # For Wayland

   # Or reset KWin config
   mv ~/.config/kwinrc ~/.config/kwinrc.backup
   kquitapp6 kwin_wayland && kstart kwin_wayland
   ```

6. **Reset Keyboard Shortcuts:**
   ```bash
   # Backup then remove shortcuts
   cp ~/.config/kglobalshortcutsrc ~/.config/kglobalshortcutsrc.backup
   rm ~/.config/kglobalshortcutsrc

   # Restart to apply
   kquitapp6 plasmashell && kstart plasmashell
   ```

7. **Reset Specific Applications:**

   **Dolphin:**
   ```bash
   rm ~/.config/dolphinrc
   rm -rf ~/.local/share/dolphin
   ```

   **Konsole:**
   ```bash
   rm ~/.config/konsolerc
   rm -rf ~/.local/share/konsole  # Removes custom profiles
   ```

   **Kate:**
   ```bash
   rm ~/.config/katerc
   rm ~/.config/kateschemarc
   rm -rf ~/.local/share/kate
   ```

   **Spectacle (screenshots):**
   ```bash
   rm ~/.config/spectaclerc
   ```

   **System Settings:**
   ```bash
   rm ~/.config/systemsettingsrc
   ```

8. **Reset Theme and Appearance:**
   ```bash
   # Remove theme configs
   rm ~/.config/plasmarc
   rm ~/.config/kcmfonts
   rm ~/.config/kcminputrc

   # Remove custom color schemes
   rm -rf ~/.local/share/color-schemes

   # Reset to default theme
   kwriteconfig6 --file plasmarc --group Theme --key name breeze
   ```

9. **Clear Plasma Cache:**
   ```bash
   # Remove cached data
   rm -rf ~/.cache/plasma*
   rm -rf ~/.cache/kwin
   rm -rf ~/.cache/icon-cache.kcache

   # Rebuild icon cache
   kbuildsycoca6 --noincremental
   ```

10. **Nuclear Option - Complete KDE Reset:**
    ```bash
    # ONLY if really needed - this resets EVERYTHING
    kquitapp6 plasmashell

    # Move all KDE configs (preserves them for recovery)
    mkdir -p ~/kde-config-backup-$(date +%Y%m%d)
    mv ~/.config/k* ~/kde-config-backup-$(date +%Y%m%d)/ 2>/dev/null
    mv ~/.config/plasma* ~/kde-config-backup-$(date +%Y%m%d)/ 2>/dev/null
    mv ~/.local/share/k* ~/kde-config-backup-$(date +%Y%m%d)/ 2>/dev/null
    mv ~/.local/share/plasma* ~/kde-config-backup-$(date +%Y%m%d)/ 2>/dev/null

    # Log out and back in to regenerate all configs
    qdbus org.kde.ksmserver /KSMServer logout 0 0 0
    ```

## Verification Steps

After reset:
1. Check if Plasma is running: `pgrep plasmashell`
2. Verify panels appeared: Look at screen
3. Check System Settings opens: `systemsettings`
4. Test application launches
5. Check for error logs: `journalctl --user -xe | grep -i plasma`

## Common Issues & Solutions

**Plasma doesn't restart:**
```bash
# Force start
plasmashell &

# Or from TTY (Ctrl+Alt+F2)
export DISPLAY=:0
plasmashell &
```

**Black screen after reset:**
```bash
# Check if running
pgrep plasmashell || plasmashell &

# Restart display manager
sudo systemctl restart sddm
```

**Settings not actually reset:**
```bash
# Make sure Plasma was stopped first
killall plasmashell
sleep 2
rm ~/.config/plasmarc
plasmashell &
```

**Want to undo reset:**
```bash
# Restore from backup
kquitapp6 plasmashell
cp -r $BACKUP_DIR/* ~/.config/
kstart plasmashell
```

## Selective Config Removal

Remove only problematic configs:
```bash
# List all KDE configs with sizes
ls -lhS ~/.config/k* ~/.config/plasma* 2>/dev/null

# Check modification dates to find recently changed
ls -lt ~/.config/k* ~/.config/plasma* 2>/dev/null | head -20

# Move suspect config instead of deleting
mv ~/.config/problematic-file ~/.config/problematic-file.old
```

## When to Use Each Reset

- **Panel disappeared:** Reset panels only
- **Widgets broken:** Clear Plasma cache + restart
- **Shortcuts not working:** Reset kglobalshortcutsrc
- **Window effects glitching:** Reset KWin config
- **Dolphin crashes:** Reset Dolphin config only
- **Everything broken:** Full Plasma reset
- **Fresh start needed:** Nuclear option

## Recovery Tools

```bash
# View current Plasma errors
journalctl --user -xe | grep -iE "plasma|kwin"

# Check config file syntax
kreadconfig6 --file plasmarc --group Theme --key name

# Rebuild KDE config cache
kbuildsycoca6

# Check for corrupt databases
rm ~/.local/share/kactivitymanagerd/resources/database*
```

## Notes

- Always backup before resetting
- Some settings are in `~/.local/share/` not `~/.config/`
- Plasma 6 uses different file locations than Plasma 5
- Window rules are stored in `~/.config/kwinrulesrc`
- Desktop effects settings in `~/.config/kwinrc`
- After major resets, you may need to log out/in instead of just restarting Plasma
- Custom installed widgets/plasmoids may need to be reinstalled
