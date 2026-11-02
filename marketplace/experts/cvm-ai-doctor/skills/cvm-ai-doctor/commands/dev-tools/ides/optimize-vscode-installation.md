---
description: Evaluate VS Code installation and suggest optimizations like repo source changes
tags: [vscode, development, optimization, configuration, project, gitignored]
---

You are helping the user optimize their VS Code installation.

## Process

1. **Check how VS Code is installed**
   ```bash
   which code
   dpkg -l | grep code
   snap list | grep code
   flatpak list | grep code
   ```
   - Identify installation method: apt, snap, flatpak, manual

2. **Check VS Code version**
   ```bash
   code --version
   ```
   - Compare with latest version
   - Check if updates are available

3. **Evaluate current installation method**

   **APT (official repo) - Recommended:**
   - Pros: Native integration, automatic updates, best performance
   - Cons: Requires adding Microsoft repo

   **Snap:**
   - Pros: Easy install, sandboxed
   - Cons: Slower startup, snap overhead, potential issues with extensions

   **Flatpak:**
   - Pros: Sandboxed, cross-distro
   - Cons: Some filesystem access limitations

   **Manual .deb:**
   - Pros: Control over updates
   - Cons: Manual update process

4. **Suggest migration if needed**

   **If installed via Snap, suggest migrating to APT:**
   ```bash
   # Remove snap version
   sudo snap remove code

   # Add official Microsoft repo
   wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
   sudo install -o root -g root -m 644 packages.microsoft.gpg /etc/apt/trusted.gpg.d/
   sudo sh -c 'echo "deb [arch=amd64] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list'

   # Install via apt
   sudo apt update && sudo apt install code
   ```

   **If privacy-conscious, suggest VSCodium:**
   ```bash
   flatpak install flathub com.vscodium.codium
   ```

5. **Check VS Code configuration**
   - Review settings: `~/.config/Code/User/settings.json`
   - Check for optimization opportunities:
     - Telemetry settings
     - Auto-save
     - File watcher limits
     - Extension recommendations

6. **Optimize performance settings**
   Suggest adding to settings.json:
   ```json
   {
     "files.watcherExclude": {
       "**/.git/objects/**": true,
       "**/node_modules/**": true,
       "**/.venv/**": true
     },
     "files.exclude": {
       "**/__pycache__": true,
       "**/.pytest_cache": true
     },
     "search.exclude": {
       "**/node_modules": true,
       "**/venv": true
     },
     "telemetry.telemetryLevel": "off"
   }
   ```

7. **Check installed extensions**
   ```bash
   code --list-extensions
   ```
   - Identify potentially redundant extensions
   - Suggest disabling unused extensions for performance

8. **Suggest useful extensions**
   - Based on detected project types
   - Common useful extensions:
     - GitLens
     - Prettier
     - ESLint/Pylint
     - Docker
     - Remote-SSH
     - Live Server (web dev)

9. **Check for conflicts**
   - Multiple VS Code installations
   - Conflicting extensions
   - Settings sync issues

10. **Create backup of settings**
    - Offer to backup:
      - `~/.config/Code/User/settings.json`
      - `~/.config/Code/User/keybindings.json`
      - Extension list

## Output

Provide a report showing:
- Current installation method and version
- Recommended installation method
- Migration steps (if applicable)
- Performance optimization suggestions
- Extension recommendations
- Configuration backup status
- Next steps
