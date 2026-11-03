---
description: Check user's basic git config and make any desired edits
tags: [git, configuration, settings, development, project, gitignored]
---

You are helping the user review and configure their git settings.

## Process

1. **Display current git configuration**
   - Global config: `git config --global --list`
   - Local config (if in repo): `git config --local --list`
   - Show config file location: `git config --global --list --show-origin`

2. **Check essential settings**

   **User identity:**
   ```bash
   git config --global user.name
   git config --global user.email
   ```
   - Verify these are set correctly
   - If not set, ask user for values

   **Default editor:**
   ```bash
   git config --global core.editor
   ```
   - Suggest: `nano`, `vim`, `code --wait`, etc.

   **Default branch name:**
   ```bash
   git config --global init.defaultBranch
   ```
   - Recommend: `main` or `master`

3. **Suggest useful configurations**

   **Color output:**
   ```bash
   git config --global color.ui auto
   ```

   **Credential helper:**
   ```bash
   git config --global credential.helper store
   # or for cache: git config --global credential.helper 'cache --timeout=3600'
   ```

   **Push behavior:**
   ```bash
   git config --global push.default simple
   git config --global push.autoSetupRemote true
   ```

   **Pull behavior:**
   ```bash
   git config --global pull.rebase false  # merge (default)
   # or: git config --global pull.rebase true  # rebase
   # or: git config --global pull.ff only  # fast-forward only
   ```

   **Line endings:**
   ```bash
   git config --global core.autocrlf input  # Linux/Mac
   ```

   **Diff and merge tools:**
   ```bash
   git config --global diff.tool meld
   git config --global merge.tool meld
   ```

4. **Aliases (optional but useful)**
   Ask if user wants common aliases:
   ```bash
   git config --global alias.st status
   git config --global alias.co checkout
   git config --global alias.br branch
   git config --global alias.ci commit
   git config --global alias.unstage 'reset HEAD --'
   git config --global alias.last 'log -1 HEAD'
   git config --global alias.lg "log --graph --pretty=format:'%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset' --abbrev-commit"
   ```

5. **GPG signing (optional)**
   ```bash
   git config --global commit.gpgsign true
   git config --global user.signingkey <GPG-KEY-ID>
   ```

6. **Show updated configuration**
   - Display all global settings
   - Highlight changes made

## Output

Provide a summary showing:
- Current git configuration
- Missing essential settings
- Recommended configurations
- Changes made (if any)
- Next steps or additional suggestions
