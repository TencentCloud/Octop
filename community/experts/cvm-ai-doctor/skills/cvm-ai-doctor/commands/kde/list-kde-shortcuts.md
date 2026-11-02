# List KDE Shortcuts

You are helping the user view all configured keyboard shortcuts in KDE Plasma.

## Task

1. **Display global shortcuts:**
   ```bash
   # Read global shortcuts config
   cat ~/.config/kglobalshortcutsrc
   ```

2. **Parse and format shortcuts nicely:**
   ```bash
   # Extract and format shortcuts
   grep -E "^[A-Za-z].*=" ~/.config/kglobalshortcutsrc | \
   grep -v "^_" | \
   sed 's/\\t/\t/g' | \
   column -t -s= | \
   head -50
   ```

3. **List shortcuts by category:**

   **KWin (Window Manager) shortcuts:**
   ```bash
   grep -A 200 "^\[kwin\]" ~/.config/kglobalshortcutsrc | \
   grep -v "^_" | \
   grep "=" | \
   sed 's/,.*$//' | \
   column -t -s=
   ```

   **Plasma Desktop shortcuts:**
   ```bash
   grep -A 100 "^\[plasmashell\]" ~/.config/kglobalshortcutsrc | \
   grep -v "^_" | \
   grep "=" | \
   sed 's/,.*$//' | \
   column -t -s=
   ```

   **Application shortcuts:**
   ```bash
   grep -A 50 "^\[org.kde.dolphin\]" ~/.config/kglobalshortcutsrc | \
   grep "=" | \
   column -t -s=
   ```

4. **Find specific shortcut by key combination:**
   ```bash
   # Search for Meta (Super) key shortcuts
   grep -i "meta" ~/.config/kglobalshortcutsrc | grep -v "^_" | head -20

   # Search for Ctrl+Alt shortcuts
   grep -i "ctrl.*alt" ~/.config/kglobalshortcutsrc | grep -v "^_" | head -20

   # Search for F-key shortcuts
   grep -E "F[0-9]+" ~/.config/kglobalshortcutsrc | grep -v "^_" | head -20
   ```

5. **Create formatted shortcut reference:**
   ```bash
   cat > /tmp/kde-shortcuts.txt << 'EOF'
   KDE Plasma Keyboard Shortcuts
   ==============================
   Generated: $(date)

   === WINDOW MANAGEMENT (KWin) ===
   EOF

   grep -A 200 "^\[kwin\]" ~/.config/kglobalshortcutsrc | \
   grep -v "^_" | \
   grep "=" | \
   sed 's/=\(.*\),.*/\t\1/' | \
   sed 's/\\t/\t→\t/' >> /tmp/kde-shortcuts.txt

   echo -e "\n\n=== PLASMA DESKTOP ===" >> /tmp/kde-shortcuts.txt
   grep -A 100 "^\[plasmashell\]" ~/.config/kglobalshortcutsrc | \
   grep -v "^_" | \
   grep "=" | \
   sed 's/=\(.*\),.*/\t\1/' | \
   sed 's/\\t/\t→\t/' >> /tmp/kde-shortcuts.txt

   cat /tmp/kde-shortcuts.txt
   ```

6. **Show default vs custom shortcuts:**
   ```bash
   # Compare with default config
   diff <(grep "=" /usr/share/kconf_update/kglobalshortcutsrc 2>/dev/null | sort) \
        <(grep "=" ~/.config/kglobalshortcutsrc | sort) | \
   grep "^>" | \
   head -20
   ```

7. **List application-specific shortcuts:**

   **Dolphin:**
   ```bash
   kreadconfig6 --file ~/.config/dolphinrc --group "Shortcuts"
   ```

   **Konsole:**
   ```bash
   kreadconfig6 --file ~/.config/konsolerc --group "Shortcuts"
   ```

   **Kate:**
   ```bash
   grep -A 100 "^\[Shortcuts\]" ~/.config/katerc 2>/dev/null
   ```

8. **Export shortcuts to easily readable format:**
   ```bash
   # Create markdown format
   cat > /tmp/kde-shortcuts.md << 'EOF'
   # KDE Plasma Keyboard Shortcuts

   ## Window Management

   | Action | Shortcut |
   |--------|----------|
   EOF

   grep -A 200 "^\[kwin\]" ~/.config/kglobalshortcutsrc | \
   grep -v "^_" | \
   grep "=" | \
   sed 's/=\([^,]*\),.*/|\1|/' | \
   sed 's/\\t/|/' | \
   sed 's/^/|/' >> /tmp/kde-shortcuts.md

   cat /tmp/kde-shortcuts.md
   ```

9. **Check for shortcut conflicts:**
   ```bash
   # Find duplicate key bindings
   grep "=" ~/.config/kglobalshortcutsrc | \
   sed 's/.*=\([^,]*\),.*/\1/' | \
   grep -v "^$\|none" | \
   sort | \
   uniq -d
   ```

10. **Interactive shortcut search:**
    ```bash
    # Function to search shortcuts
    cat > /tmp/search-shortcuts.sh << 'EOF'
    #!/bin/bash

    if [ -z "$1" ]; then
      echo "Usage: $0 <search_term>"
      echo "Example: $0 desktop"
      echo "Example: $0 Meta+D"
      exit 1
    fi

    echo "Searching for: $1"
    echo "================================"

    grep -i "$1" ~/.config/kglobalshortcutsrc | \
    grep "=" | \
    grep -v "^_" | \
    sed 's/=\([^,]*\),.*/\t→\t\1/' | \
    sed 's/\\t/\t/'
    EOF

    chmod +x /tmp/search-shortcuts.sh

    # Example usage
    /tmp/search-shortcuts.sh "window"
    ```

## Common Shortcuts Reference

Create a quick reference of most-used shortcuts:
```bash
cat > /tmp/kde-common-shortcuts.md << 'EOF'
# KDE Plasma - Common Default Shortcuts

## Window Management
- `Meta + Arrow` - Snap window to edge
- `Meta + PageUp/PageDown` - Window to desktop above/below
- `Alt + F2` - Run command (KRunner)
- `Alt + F3` - Window menu
- `Alt + F4` - Close window
- `Meta + Tab` - Switch windows

## Desktop
- `Meta + D` - Show desktop
- `Ctrl + F1-F12` - Switch virtual desktops
- `Meta + PgUp/PgDn` - Move to desktop above/below

## Plasma
- `Alt + Space` - KRunner
- `Meta` - Application Launcher
- `Ctrl + Esc` - System Activity (task manager)

## Screenshots
- `Print` - Full screen screenshot
- `Meta + Print` - Window screenshot
- `Meta + Shift + Print` - Region screenshot

## Applications
- `Meta + E` - Dolphin (file manager)
- `Ctrl + Alt + T` - Terminal (if configured)
EOF

cat /tmp/kde-common-shortcuts.md
```

## GUI Shortcut Management

If user prefers GUI:
```bash
# Open System Settings to Shortcuts
kcmshell6 keys
# OR
systemsettings kcm_keys
```

## Export for Documentation

```bash
# Create detailed export
cat > ~/kde-shortcuts-export-$(date +%Y%m%d).txt << EOF
KDE Plasma Keyboard Shortcuts Export
=====================================
Date: $(date)
User: $USER
Hostname: $(hostname)
Plasma Version: $(plasmashell --version)

EOF

# Add all shortcuts by category
for section in kwin plasmashell org_kde_powerdevil khotkeys; do
  echo -e "\n=== $section ===\n" >> ~/kde-shortcuts-export-$(date +%Y%m%d).txt
  grep -A 500 "^\[$section\]" ~/.config/kglobalshortcutsrc | \
  grep "=" | \
  grep -v "^_" | \
  head -100 >> ~/kde-shortcuts-export-$(date +%Y%m%d).txt
done

echo "Exported to: ~/kde-shortcuts-export-$(date +%Y%m%d).txt"
```

## Find Unassigned Actions

```bash
# Actions that have no shortcut assigned
grep "=none" ~/.config/kglobalshortcutsrc | \
grep -v "^_" | \
sed 's/=.*//' | \
head -30
```

## Troubleshooting

**Shortcuts not working:**
```bash
# Check if shortcuts are enabled
kreadconfig6 --file kglobalshortcutsrc --group "KDE Keyboard Layout Switcher" --key "_k_friendly_name"

# Restart KDE shortcuts daemon
kquitapp6 kglobalaccel
kglobalaccel &
```

**Reset shortcuts to defaults:**
```bash
# Backup current
cp ~/.config/kglobalshortcutsrc ~/.config/kglobalshortcutsrc.backup

# Remove custom shortcuts
rm ~/.config/kglobalshortcutsrc

# Restart Plasma
kquitapp6 plasmashell && kstart plasmashell
```

## Notes

- Shortcuts are stored in `~/.config/kglobalshortcutsrc`
- Format: `action=key,friendly_name,component`
- `Meta` key = Super/Windows key
- Some apps store shortcuts in their own config files
- Use System Settings GUI for easier shortcut management
- Custom shortcuts can be added via khotkeys
- Conflicts are usually handled automatically by KDE
