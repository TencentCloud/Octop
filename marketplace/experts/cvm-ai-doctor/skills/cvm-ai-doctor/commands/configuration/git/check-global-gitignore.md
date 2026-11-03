---
description: Check if user has global gitignore and create one if not
tags: [git, configuration, gitignore, development, project, gitignored]
---

You are helping the user set up a global gitignore file.

## Process

1. **Check if global gitignore exists**
   - Run: `git config --global core.excludesfile`
   - Check common locations:
     - `~/.gitignore_global`
     - `~/.gitignore`
     - `~/.config/git/ignore`

2. **If global gitignore doesn't exist, create one**
   - Choose location: `~/.gitignore_global`
   - Configure git to use it:
     ```bash
     git config --global core.excludesfile ~/.gitignore_global
     ```

3. **Populate with common patterns**
   - Create comprehensive gitignore with patterns for:

   **Operating System:**
   ```
   # macOS
   .DS_Store
   .AppleDouble
   .LSOverride

   # Linux
   *~
   .directory
   .Trash-*

   # Windows
   Thumbs.db
   Desktop.ini
   ```

   **IDEs and Editors:**
   ```
   # VS Code
   .vscode/
   *.code-workspace

   # JetBrains
   .idea/
   *.iml

   # Vim
   *.swp
   *.swo
   *~

   # Emacs
   *~
   \#*\#
   ```

   **Languages and Frameworks:**
   ```
   # Python
   __pycache__/
   *.py[cod]
   *$py.class
   .venv/
   venv/
   ENV/
   .Python
   *.egg-info/
   dist/
   build/

   # Node.js
   node_modules/
   npm-debug.log
   yarn-error.log
   .npm/

   # Ruby
   *.gem
   .bundle/
   vendor/bundle/

   # Rust
   target/
   Cargo.lock

   # Go
   *.exe
   *.test
   *.out
   ```

   **Build artifacts:**
   ```
   *.o
   *.a
   *.so
   *.dylib
   *.dll
   *.class
   *.jar
   ```

   **Misc:**
   ```
   # Logs
   *.log
   logs/

   # Temporary files
   *.tmp
   *.temp
   .cache/

   # Environment files
   .env
   .env.local

   # Database files
   *.sqlite
   *.db
   ```

4. **Review existing gitignore if it exists**
   - Read current file
   - Suggest additions if patterns are missing
   - Offer to back up before modifying

5. **Test the configuration**
   - Verify config: `git config --global core.excludesfile`
   - Show the file: `cat ~/.gitignore_global`

## Output

Provide a summary showing:
- Global gitignore location
- Whether it was created or already existed
- List of patterns included
- Verification of git configuration
