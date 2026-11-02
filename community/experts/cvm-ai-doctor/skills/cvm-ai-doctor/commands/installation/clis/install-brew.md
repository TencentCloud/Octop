# Install Homebrew on Linux

You are helping the user install Homebrew (brew) package manager on Linux.

## Your tasks:

1. **Check if Homebrew is already installed:**
   - Check: `which brew`
   - If installed: `brew --version`
   - If already installed, ask if they want to update or reconfigure it

2. **Check prerequisites:**
   Homebrew requires:
   - Git: `git --version`
   - Curl: `curl --version`
   - GCC: `gcc --version`
   - Build essentials

   Install missing prerequisites:
   ```bash
   sudo apt update
   sudo apt install build-essential procps curl file git
   ```

3. **Download and run Homebrew installer:**
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

   The script will:
   - Install to `/home/linuxbrew/.linuxbrew` (multi-user) or `~/.linuxbrew` (single user)
   - Set up necessary directories
   - Install Homebrew

4. **Add Homebrew to PATH:**
   The installer will suggest adding Homebrew to your PATH. Add to ~/.bashrc or ~/.profile:

   ```bash
   echo 'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"' >> ~/.bashrc
   source ~/.bashrc
   ```

   Or for single-user installation:
   ```bash
   echo 'eval "$($HOME/.linuxbrew/bin/brew shellenv)"' >> ~/.bashrc
   source ~/.bashrc
   ```

5. **Verify installation:**
   ```bash
   brew --version
   which brew
   brew doctor
   ```

6. **Run brew doctor and fix issues:**
   `brew doctor` will check for common issues. Follow its recommendations:
   - Install recommended dependencies
   - Fix PATH issues
   - Update outdated software

7. **Install recommended packages:**
   Homebrew recommends installing gcc:
   ```bash
   brew install gcc
   ```

8. **Configure Homebrew (optional):**
   - Disable analytics: `brew analytics off`
   - Set up auto-update preferences
   - Configure tap repositories

9. **Show basic Homebrew usage:**
   Explain to the user:
   - `brew install <package>` - Install a package
   - `brew uninstall <package>` - Remove a package
   - `brew upgrade` - Upgrade all packages
   - `brew update` - Update Homebrew itself
   - `brew list` - List installed packages
   - `brew search <package>` - Search for packages
   - `brew info <package>` - Get package info
   - `brew doctor` - Check for issues
   - `brew cleanup` - Remove old versions

10. **Set up common taps (optional):**
    Ask if user wants popular taps:
    ```bash
    brew tap homebrew/cask-fonts  # for fonts
    brew tap homebrew/cask-versions  # for alternative versions
    ```

11. **Handle path conflicts:**
    Check if Homebrew binaries conflict with system packages:
    ```bash
    which -a python3
    which -a git
    ```
    Explain that Homebrew packages take precedence if in PATH correctly.

12. **Performance optimization:**
    - Set up Homebrew bottle (binary package) cache
    - Configure number of parallel downloads:
      ```bash
      echo 'export HOMEBREW_MAKE_JOBS=4' >> ~/.bashrc
      ```

13. **Provide best practices:**
    - Run `brew update` regularly
    - Run `brew upgrade` to keep packages current
    - Run `brew cleanup` to free up space
    - Use `brew doctor` to diagnose issues
    - Pin packages you don't want upgraded: `brew pin <package>`
    - Prefer Homebrew for development tools, apt for system packages
    - Don't run brew with sudo

## Important notes:
- Homebrew on Linux is called "Linuxbrew"
- Don't use sudo with brew commands
- Homebrew compiles from source if no bottle (binary) is available
- Can coexist with apt/apt-get
- Takes up significant disk space
- Compilation can take time
- Keep PATH properly configured
