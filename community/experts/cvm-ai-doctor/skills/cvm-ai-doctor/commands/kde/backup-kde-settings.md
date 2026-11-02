# Backup KDE Settings

You are helping the user export and backup their KDE Plasma configuration settings.

## Task

1. **Identify KDE configuration locations:**
   ```bash
   # Main config directory
   echo "KDE Config: ~/.config/"

   # Local data directory
   echo "KDE Data: ~/.local/share/"

   # Cache directory
   echo "KDE Cache: ~/.cache/"
   ```

2. **List important KDE configuration files:**
   ```bash
   # Core KDE files
   ls -lh ~/.config/k* ~/.config/plasma* ~/.config/*rc 2>/dev/null | head -30

   # Desktop files
   ls -lh ~/.local/share/plasma* ~/.local/share/k* 2>/dev/null | head -20
   ```

3. **Create backup directory:**
   ```bash
   # Create timestamped backup directory
   BACKUP_DIR=~/.kde-backups/kde-backup-$(date +%Y%m%d-%H%M%S)
   mkdir -p "$BACKUP_DIR"
   echo "Backup directory: $BACKUP_DIR"
   ```

4. **Backup essential KDE configurations:**
   ```bash
   # Core Plasma configuration
   cp -r ~/.config/plasma* "$BACKUP_DIR/" 2>/dev/null
   cp -r ~/.config/k* "$BACKUP_DIR/" 2>/dev/null

   # Application-specific configs
   for config in kdeglobals kwinrc dolphinrc konsolerc katerc spectaclerc; do
     [ -f ~/.config/$config ] && cp ~/.config/$config "$BACKUP_DIR/"
   done

   # Desktop theme and appearance
   cp ~/.config/plasmarc "$BACKUP_DIR/" 2>/dev/null
   cp ~/.config/plasmashellrc "$BACKUP_DIR/" 2>/dev/null

   # Keyboard shortcuts
   cp ~/.config/kglobalshortcutsrc "$BACKUP_DIR/" 2>/dev/null
   cp ~/.config/khotkeysrc "$BACKUP_DIR/" 2>/dev/null
   ```

5. **Backup KDE desktop layouts:**
   ```bash
   # Plasma layouts
   cp -r ~/.local/share/plasma "$BACKUP_DIR/plasma-data" 2>/dev/null

   # Desktop scripts
   cp -r ~/.local/share/kservices5 "$BACKUP_DIR/kservices" 2>/dev/null

   # Plasmoids and widgets
   cp -r ~/.local/share/plasmashell "$BACKUP_DIR/plasmashell-data" 2>/dev/null
   ```

6. **Backup application data:**
   ```bash
   # Dolphin bookmarks and settings
   cp -r ~/.local/share/dolphin "$BACKUP_DIR/dolphin-data" 2>/dev/null

   # Konsole profiles
   cp -r ~/.local/share/konsole "$BACKUP_DIR/konsole-data" 2>/dev/null

   # KWallet (encrypted passwords)
   cp -r ~/.local/share/kwalletd "$BACKUP_DIR/kwallet-data" 2>/dev/null

   # Akonadi (if using KMail/contacts)
   # cp -r ~/.local/share/akonadi "$BACKUP_DIR/akonadi-data" 2>/dev/null
   ```

7. **Backup color schemes and themes:**
   ```bash
   # Color schemes
   cp -r ~/.local/share/color-schemes "$BACKUP_DIR/" 2>/dev/null

   # Plasma themes
   cp -r ~/.local/share/plasma/desktoptheme "$BACKUP_DIR/" 2>/dev/null

   # Icon themes
   cp -r ~/.local/share/icons "$BACKUP_DIR/" 2>/dev/null

   # Window decorations
   cp -r ~/.local/share/aurorae "$BACKUP_DIR/" 2>/dev/null
   ```

8. **Create backup manifest:**
   ```bash
   cat > "$BACKUP_DIR/BACKUP_INFO.txt" << EOF
   KDE Plasma Backup
   =================
   Date: $(date)
   Hostname: $(hostname)
   KDE Version: $(plasmashell --version)
   Qt Version: $(qmake --version | grep -i "Qt version")

   Backup Contents:
   ----------------
   $(find "$BACKUP_DIR" -type f | wc -l) files backed up
   $(du -sh "$BACKUP_DIR" | cut -f1) total size

   Configuration Files:
   $(ls -1 "$BACKUP_DIR"/*.rc "$BACKUP_DIR"/*config* 2>/dev/null | wc -l) config files

   Important Files:
   $(ls -lh "$BACKUP_DIR" | grep -E "plasma|kwin|dolphin|konsole|kdeglobals")
   EOF

   cat "$BACKUP_DIR/BACKUP_INFO.txt"
   ```

9. **Compress backup:**
   ```bash
   # Create compressed archive
   cd ~/.kde-backups
   tar czf "$(basename "$BACKUP_DIR").tar.gz" "$(basename "$BACKUP_DIR")"

   # Show results
   ls -lh "$(basename "$BACKUP_DIR").tar.gz"
   echo "Backup archived: ~/.kde-backups/$(basename "$BACKUP_DIR").tar.gz"
   ```

10. **Optional: Sync to cloud or external storage:**
    ```bash
    # Ask user if they want to copy backup elsewhere
    # Example: Copy to NAS
    # scp "$(basename "$BACKUP_DIR").tar.gz" user@nas:/backups/kde/

    # Example: Copy to external drive
    # cp "$(basename "$BACKUP_DIR").tar.gz" /mnt/external/kde-backups/
    ```

## Restoration Instructions

Create a restoration guide in the backup:
```bash
cat > "$BACKUP_DIR/RESTORE.md" << 'EOF'
# KDE Backup Restoration

## To restore this backup:

1. **Extract the archive:**
   ```bash
   cd ~/.kde-backups
   tar xzf kde-backup-TIMESTAMP.tar.gz
   ```

2. **Close all KDE applications** (important!)

3. **Restore configuration files:**
   ```bash
   cd kde-backup-TIMESTAMP
   cp -r k* plasma* *.rc ~/.config/
   ```

4. **Restore data files:**
   ```bash
   cp -r plasma-data ~/.local/share/plasma
   cp -r dolphin-data ~/.local/share/dolphin
   cp -r konsole-data ~/.local/share/konsole
   ```

5. **Restart Plasma:**
   ```bash
   kquitapp6 plasmashell && kstart plasmashell
   ```

   Or log out and back in.

## Selective Restoration

To restore only specific components:
- Shortcuts: `cp kglobalshortcutsrc ~/.config/`
- Theme: `cp plasmarc ~/.config/`
- Panel/Desktop: `cp -r plasma-data ~/.local/share/plasma`
- Dolphin: `cp -r dolphin-data ~/.local/share/dolphin`

EOF
```

## Minimal vs Complete Backup

**Minimal backup** (most important settings):
```bash
# Just essential configs
tar czf ~/.kde-backups/kde-minimal-backup.tar.gz \
  ~/.config/kdeglobals \
  ~/.config/kwinrc \
  ~/.config/plasmarc \
  ~/.config/kglobalshortcutsrc \
  ~/.local/share/plasma
```

**Complete backup** (everything):
```bash
# All KDE data
tar czf ~/.kde-backups/kde-complete-backup.tar.gz \
  ~/.config/k* \
  ~/.config/plasma* \
  ~/.local/share/plasma* \
  ~/.local/share/k* \
  --exclude="*.lock" \
  --exclude="*cache*"
```

## Scheduled Backups

Create a cron job for automatic backups:
```bash
# Add to crontab
(crontab -l 2>/dev/null; echo "0 2 * * 0 $HOME/.local/bin/backup-kde.sh") | crontab -

# Create backup script
cat > ~/.local/bin/backup-kde.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=~/.kde-backups/kde-backup-$(date +%Y%m%d)
mkdir -p "$BACKUP_DIR"
cp -r ~/.config/{k*,plasma*} "$BACKUP_DIR/" 2>/dev/null
cp -r ~/.local/share/plasma "$BACKUP_DIR/" 2>/dev/null
tar czf "$BACKUP_DIR.tar.gz" "$BACKUP_DIR"
rm -rf "$BACKUP_DIR"
# Keep only last 4 backups
cd ~/.kde-backups && ls -t | tail -n +5 | xargs rm -f
EOF

chmod +x ~/.local/bin/backup-kde.sh
```

## Notes

- KDE 5 uses `kf5` directory structure, KDE 6 uses `kf6`
- Plasma 6 may have different config locations
- Don't backup cache files (*.lock, cache directories)
- KWallet passwords require the same user password to decrypt
- Some configs are machine-specific (display settings)
- Consider using Konsave (KDE settings manager) for easy backups
- Large data folders (Akonadi, Baloo index) can be skipped for config backups
