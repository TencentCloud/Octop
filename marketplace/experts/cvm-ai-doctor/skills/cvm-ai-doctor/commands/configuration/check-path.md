# Check and Analyze PATH

You are helping the user analyze what's on their PATH and suggest additions or improvements.

## Your tasks:

1. **Display current PATH:**
   ```bash
   echo $PATH | tr ':' '\n'
   ```

2. **Check which paths actually exist:**
   ```bash
   echo $PATH | tr ':' '\n' | while read p; do
     if [ -d "$p" ]; then
       echo "✓ $p"
     else
       echo "✗ $p (does not exist)"
     fi
   done
   ```

3. **Check for duplicate PATH entries:**
   ```bash
   echo $PATH | tr ':' '\n' | sort | uniq -d
   ```

4. **Identify where PATH is being set:**
   Check common locations:
   ```bash
   grep -n "PATH" ~/.bashrc ~/.bash_profile ~/.profile /etc/environment /etc/profile 2>/dev/null
   ```

5. **Check for common development tool paths:**

   **Programming languages:**
   - Python user packages: `~/.local/bin`
   - Rust cargo: `~/.cargo/bin`
   - Go: `~/go/bin` or `$GOPATH/bin`
   - Ruby gems: Check with `gem environment`
   - Node/npm: Check with `npm config get prefix`

   **Package managers:**
   - Homebrew: `/home/linuxbrew/.linuxbrew/bin`
   - SDKMAN: `~/.sdkman/candidates/*/current/bin`
   - pipx: `~/.local/bin`

   **Version managers:**
   - pyenv: `~/.pyenv/bin`
   - rbenv: `~/.rbenv/bin`
   - nvm: (check ~/.nvm/)
   - asdf: `~/.asdf/bin`

   **System tools:**
   - User binaries: `~/bin`, `~/.local/bin`
   - Snap: `/snap/bin`
   - Flatpak: `/var/lib/flatpak/exports/bin`

6. **Check what's installed in each PATH directory:**
   For each directory in PATH:
   ```bash
   echo "Contents of $dir:"
   ls -la "$dir" | head -10
   ```

7. **Suggest missing common paths:**
   Check and suggest if not in PATH:

   - `~/.local/bin` (Python user packages, pipx)
   - `~/bin` (User scripts)
   - `~/.cargo/bin` (Rust packages)
   - `~/go/bin` (Go packages)
   - `/snap/bin` (Snap packages)
   - `~/.npm-global/bin` (npm global packages)

   For each missing path that has executables, suggest adding it.

8. **Check for security issues:**
   - Warn if `.` (current directory) is in PATH
   - Warn if world-writable directories are in PATH:
     ```bash
     echo $PATH | tr ':' '\n' | while read p; do
       if [ -d "$p" ] && [ -w "$p" ]; then
         ls -ld "$p"
       fi
     done
     ```

9. **Check PATH order/precedence:**
   Explain that earlier paths take precedence.
   Show which binary would be executed:
   ```bash
   which -a python python3 java gcc git node npm
   ```

10. **Check for conflicting tools:**
    ```bash
    type -a python
    type -a python3
    type -a java
    ```

11. **Suggest PATH organization:**
    Recommended order:
    1. User binaries (`~/bin`, `~/.local/bin`)
    2. Version managers (pyenv, rbenv, nvm)
    3. Language-specific paths (cargo, go)
    4. Homebrew
    5. System binaries (`/usr/local/bin`, `/usr/bin`, `/bin`)

12. **Check environment-specific paths:**

    **Python:**
    ```bash
    python3 -m site --user-base
    # Suggests adding $(python3 -m site --user-base)/bin
    ```

    **Node/npm:**
    ```bash
    npm config get prefix
    # Suggests adding <prefix>/bin
    ```

    **Go:**
    ```bash
    go env GOPATH
    # Suggests adding $GOPATH/bin
    ```

    **Rust:**
    ```bash
    echo $CARGO_HOME
    # Suggests adding ~/.cargo/bin
    ```

13. **Generate suggested PATH setup:**
    Based on findings, create suggested additions for ~/.bashrc:

    ```bash
    # User binaries
    export PATH="$HOME/bin:$PATH"
    export PATH="$HOME/.local/bin:$PATH"

    # Python
    export PATH="$HOME/.local/bin:$PATH"

    # Rust
    export PATH="$HOME/.cargo/bin:$PATH"

    # Go
    export PATH="$HOME/go/bin:$PATH"

    # SDKMAN
    # Added by sdkman-init.sh

    # pyenv
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init --path)"

    # Homebrew
    eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
    ```

14. **Check for broken symlinks in PATH:**
    ```bash
    echo $PATH | tr ':' '\n' | while read dir; do
      if [ -d "$dir" ]; then
        find "$dir" -maxdepth 1 -type l ! -exec test -e {} \; -print 2>/dev/null
      fi
    done
    ```

15. **Provide recommendations:**
    - Remove non-existent directories from PATH
    - Add missing common paths that have executables
    - Fix duplicate entries
    - Correct PATH order if needed
    - Remove security issues (`.` in PATH, world-writable dirs)
    - Consolidate PATH modifications into one file (prefer ~/.bashrc)
    - Document what each PATH addition is for

16. **Show how to temporarily modify PATH:**
    ```bash
    # Add to front (takes precedence)
    export PATH="/new/path:$PATH"

    # Add to end
    export PATH="$PATH:/new/path"

    # Remove from PATH
    export PATH=$(echo $PATH | tr ':' '\n' | grep -v "/path/to/remove" | tr '\n' ':')
    ```

17. **Show how to make PATH changes permanent:**
    ```bash
    echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
    source ~/.bashrc
    ```

## Important notes:
- Changes to PATH only affect current shell unless made permanent
- Order matters - earlier paths have precedence
- Don't add current directory (`.`) to PATH
- Use absolute paths when possible
- Source ~/.bashrc after changes: `source ~/.bashrc`
- Some tools (pyenv, conda, nvm) modify PATH dynamically
- Check for PATH modifications in multiple files
