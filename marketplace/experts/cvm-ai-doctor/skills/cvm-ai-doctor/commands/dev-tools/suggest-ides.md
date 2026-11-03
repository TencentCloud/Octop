---
description: Suggest IDEs the user may wish to install
tags: [development, ide, editors, tools, project, gitignored]
---

You are helping the user identify useful IDEs and code editors to install.

## Process

1. **Check currently installed editors/IDEs**
   ```bash
   which code vim nvim nano emacs gedit kate
   dpkg -l | grep -E "code|editor|ide"
   flatpak list | grep -E "code|editor|ide"
   ```

2. **Identify user's programming needs**
   - Ask about programming languages used:
     - Python
     - JavaScript/TypeScript
     - Java/Kotlin
     - C/C++/Rust
     - Go
     - Web development
     - Data science
     - Mobile development

3. **Suggest IDEs by category**

   **General Purpose (recommended):**
   - **VS Code** - Most popular, extensive plugins
   - **VSCodium** - VS Code without telemetry
   - **JetBrains Fleet** - Modern, lightweight
   - **Sublime Text** - Fast, elegant
   - **Atom** (deprecated, suggest alternatives)

   **Language-Specific:**
   - **PyCharm** - Python (Community/Professional)
   - **IntelliJ IDEA** - Java/Kotlin
   - **WebStorm** - JavaScript/TypeScript
   - **RustRover** - Rust
   - **GoLand** - Go
   - **Android Studio** - Android development

   **Lightweight Editors:**
   - **Neovim** - Modern Vim
   - **Helix** - Modern modal editor
   - **Micro** - Terminal editor, easy to use
   - **Geany** - GTK editor with IDE features

   **Data Science:**
   - **JupyterLab** - Notebooks
   - **RStudio** - R development
   - **Spyder** - Python for scientific computing

   **Web Development:**
   - **Zed** - Collaborative, fast
   - **Brackets** - Live preview

4. **Installation methods**

   **VS Code:**
   ```bash
   # Official repo
   wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
   sudo install -o root -g root -m 644 packages.microsoft.gpg /etc/apt/trusted.gpg.d/
   sudo sh -c 'echo "deb [arch=amd64] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list'
   sudo apt update && sudo apt install code
   ```

   **VSCodium:**
   ```bash
   flatpak install flathub com.vscodium.codium
   ```

   **JetBrains Toolbox:**
   ```bash
   # Download from jetbrains.com/toolbox/
   # Or use snap: snap install jetbrains-toolbox --classic
   ```

   **Neovim:**
   ```bash
   sudo apt install neovim
   ```

5. **Suggest based on current setup**
   - If Python user: Suggest PyCharm
   - If web dev: Suggest VS Code with extensions
   - If systems programming: Suggest Neovim with LSP
   - If prefer FOSS: Suggest VSCodium

6. **Recommend extensions/plugins**
   - For VS Code/VSCodium:
     - Python
     - Pylance
     - GitLens
     - Docker
     - Remote SSH
     - Prettier
     - ESLint

7. **Alternative: Check installed editors quality**
   - Vim/Neovim configuration quality
   - VS Code extension count
   - Suggest improvements to existing setup

## Output

Provide a report showing:
- Currently installed editors/IDEs
- Recommended IDEs based on user's needs
- Installation commands for suggestions
- Extension/plugin recommendations
- Comparison of options (pros/cons)
