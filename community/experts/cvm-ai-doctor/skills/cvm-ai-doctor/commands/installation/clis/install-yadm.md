# Install YADM (Yet Another Dotfiles Manager)

You are helping the user install and set up YADM for managing their dotfiles.

## Your tasks:

1. **Check if YADM is already installed:**
   - Check: `which yadm`
   - If installed: `yadm version`
   - If already installed, ask the user if they want to:
     - Configure it for first use
     - Upgrade to the latest version
     - Or exit

2. **Install YADM:**

   **Option 1: Using apt (recommended for Ubuntu):**
   ```bash
   sudo apt update
   sudo apt install yadm
   ```

   **Option 2: Using the install script (for latest version):**
   ```bash
   curl -fsSL https://github.com/TheLocehiliosan/yadm/raw/master/bootstrap/install_yadm.sh | sudo bash
   ```

   Ask the user which installation method they prefer.

3. **Verify installation:**
   - Check version: `yadm version`
   - Check location: `which yadm`

4. **Initialize YADM (if user wants to set it up):**

   **For new setup:**
   ```bash
   yadm init
   ```

   **For cloning existing dotfiles:**
   Ask the user if they have an existing dotfiles repository to clone.
   If yes, get the repository URL and run:
   ```bash
   yadm clone <repository-url>
   ```

5. **Guide the user through initial configuration:**

   **Add existing dotfiles:**
   Suggest common dotfiles to track:
   - `~/.bashrc`
   - `~/.bash_profile`
   - `~/.profile`
   - `~/.gitconfig`
   - `~/.ssh/config` (if exists)
   - `~/.config/` directories (ask which ones)

   Show how to add files:
   ```bash
   yadm add ~/.bashrc
   yadm add ~/.gitconfig
   yadm commit -m "Initial dotfiles commit"
   ```

6. **Set up remote repository (if user wants):**
   Ask if they want to set up a remote repository:
   ```bash
   yadm remote add origin <repository-url>
   yadm push -u origin main
   ```

7. **Explain basic YADM usage:**
   - `yadm status` - Check status
   - `yadm add <file>` - Track a file
   - `yadm commit -m "message"` - Commit changes
   - `yadm push` - Push to remote
   - `yadm pull` - Pull from remote
   - `yadm list` - List tracked files
   - `yadm diff` - Show differences

8. **Set up encryption (optional):**
   Ask if the user wants to encrypt sensitive files:
   ```bash
   echo ".ssh/id_rsa" >> ~/.config/yadm/encrypt
   yadm encrypt
   ```

9. **Set up bootstrap (optional):**
   Explain that YADM can run a bootstrap script on new systems.
   Offer to create a basic `~/.config/yadm/bootstrap` script:
   ```bash
   #!/bin/bash
   # Install common packages
   sudo apt update
   sudo apt install -y git vim tmux
   ```

10. **Provide next steps and best practices:**
    - Regularly commit dotfile changes: `yadm add -u && yadm commit -m "Update dotfiles"`
    - Use branches for experimental configurations
    - Use `.config/yadm/encrypt` for sensitive files
    - Consider alternate files for different systems (using YADM's alternate file feature)
    - Backup remote repository (GitHub/GitLab)

## Important notes:
- Ask before making any commits or pushes
- Explain the difference between YADM and regular git (YADM operates on $HOME)
- Warn about not committing sensitive information unencrypted
- If user already has dotfiles in a git repo, explain migration process
- Be clear that YADM commands work like git commands
