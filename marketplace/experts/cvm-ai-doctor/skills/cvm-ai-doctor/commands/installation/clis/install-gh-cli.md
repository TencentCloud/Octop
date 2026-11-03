# Install and Authenticate GitHub CLI (gh)

You are helping the user install and authenticate the GitHub CLI tool.

## Your tasks:

1. **Check if gh is already installed:**
   ```bash
   which gh
   gh --version
   ```

   If already installed and authenticated:
   ```bash
   gh auth status
   ```

2. **Install GitHub CLI (if not installed):**

   **Method 1: Using official repository (recommended):**
   ```bash
   # Add the GPG key
   sudo mkdir -p -m 755 /etc/apt/keyrings
   wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null
   sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg

   # Add the repository
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null

   # Install
   sudo apt update
   sudo apt install gh
   ```

   **Method 2: Using snap:**
   ```bash
   sudo snap install gh
   ```

   **Method 3: Using Homebrew (if installed):**
   ```bash
   brew install gh
   ```

3. **Verify installation:**
   ```bash
   gh --version
   which gh
   ```

4. **Authenticate with GitHub:**

   **Interactive authentication (recommended):**
   ```bash
   gh auth login
   ```

   This will prompt for:
   - GitHub.com or GitHub Enterprise Server
   - Preferred protocol (HTTPS or SSH)
   - Authentication method (web browser or token)

   **Via web browser (easiest):**
   - Select "Login with a web browser"
   - Follow the one-time code and URL
   - Authorize in browser

   **Via token:**
   - Generate a token at https://github.com/settings/tokens
   - Select "Login with authentication token"
   - Paste the token

5. **Verify authentication:**
   ```bash
   gh auth status
   ```

   Should show:
   - Logged in to github.com
   - Account name
   - Token scopes

6. **Configure gh settings:**

   **Set default editor:**
   ```bash
   gh config set editor vim
   # or
   gh config set editor nano
   # or
   gh config set editor code  # VS Code
   ```

   **Set default protocol:**
   ```bash
   gh config set git_protocol ssh
   # or
   gh config set git_protocol https
   ```

   **View all config:**
   ```bash
   gh config list
   ```

7. **Set up SSH key (if using SSH protocol):**
   ```bash
   # Generate SSH key if needed
   ssh-keygen -t ed25519 -C "your_email@example.com"

   # Add to ssh-agent
   eval "$(ssh-agent -s)"
   ssh-add ~/.ssh/id_ed25519

   # Add to GitHub
   gh ssh-key add ~/.ssh/id_ed25519.pub --title "My Ubuntu Desktop"

   # Or copy public key to GitHub manually
   cat ~/.ssh/id_ed25519.pub
   ```

8. **Test GitHub connectivity:**
   ```bash
   # Test SSH connection
   ssh -T git@github.com

   # Test gh CLI
   gh repo list
   gh auth status
   ```

9. **Configure git to use gh for credentials:**
   ```bash
   gh auth setup-git
   ```

   This configures git to use gh as a credential helper.

10. **Show basic gh commands:**

    **Repository operations:**
    - `gh repo create` - Create a repository
    - `gh repo clone <repo>` - Clone a repository
    - `gh repo view` - View repository details
    - `gh repo list` - List your repositories
    - `gh repo fork` - Fork a repository

    **Pull requests:**
    - `gh pr create` - Create a pull request
    - `gh pr list` - List pull requests
    - `gh pr view <number>` - View a PR
    - `gh pr checkout <number>` - Checkout a PR
    - `gh pr merge <number>` - Merge a PR
    - `gh pr review <number>` - Review a PR

    **Issues:**
    - `gh issue create` - Create an issue
    - `gh issue list` - List issues
    - `gh issue view <number>` - View an issue
    - `gh issue close <number>` - Close an issue

    **Workflows:**
    - `gh workflow list` - List workflows
    - `gh workflow view <workflow>` - View workflow
    - `gh workflow run <workflow>` - Trigger a workflow
    - `gh run list` - List workflow runs
    - `gh run view <run>` - View a run

    **Gists:**
    - `gh gist create <file>` - Create a gist
    - `gh gist list` - List gists
    - `gh gist view <gist>` - View a gist

11. **Set up shell completion:**

    **For bash:**
    ```bash
    gh completion -s bash > ~/.gh-completion.bash
    echo 'source ~/.gh-completion.bash' >> ~/.bashrc
    source ~/.bashrc
    ```

    **For zsh:**
    ```bash
    gh completion -s zsh > ~/.gh-completion.zsh
    echo 'source ~/.gh-completion.zsh' >> ~/.zshrc
    source ~/.zshrc
    ```

12. **Configure multiple accounts (if needed):**
    ```bash
    # Add another account
    GH_HOST=github.com gh auth login

    # Switch between accounts
    gh auth switch
    ```

13. **Set up aliases (optional):**
    ```bash
    gh alias set pv 'pr view'
    gh alias set co 'pr checkout'
    gh alias set bugs 'issue list --label=bug'
    ```

    List aliases:
    ```bash
    gh alias list
    ```

14. **Authenticate with GitHub Enterprise (if applicable):**
    ```bash
    gh auth login --hostname github.example.com
    ```

15. **Troubleshooting common issues:**

    **Permission denied:**
    - Check auth status: `gh auth status`
    - Re-authenticate: `gh auth login`
    - Check token scopes

    **SSH issues:**
    - Verify SSH key: `ssh -T git@github.com`
    - Add SSH key to GitHub: `gh ssh-key add`
    - Check ssh-agent: `ssh-add -l`

    **Rate limiting:**
    - Check rate limit: `gh api rate_limit`
    - Use authentication to increase limits

16. **Update gh:**
    ```bash
    sudo apt update
    sudo apt upgrade gh
    # or
    brew upgrade gh
    # or
    sudo snap refresh gh
    ```

17. **Advanced configuration:**

    **Custom API endpoint:**
    ```bash
    gh config set api_endpoint https://api.github.com
    ```

    **Disable prompts:**
    ```bash
    gh config set prompt disabled
    ```

    **Configure pager:**
    ```bash
    gh config set pager less
    ```

18. **Security best practices:**
    - Use SSH keys instead of HTTPS when possible
    - Use tokens with minimal required scopes
    - Rotate tokens regularly
    - Don't share tokens
    - Use different tokens for different machines
    - Enable 2FA on GitHub account
    - Review authorized applications regularly

19. **Provide workflow examples:**

    **Create a repo and push:**
    ```bash
    mkdir my-project
    cd my-project
    git init
    echo "# My Project" > README.md
    git add README.md
    git commit -m "Initial commit"
    gh repo create my-project --public --source=. --push
    ```

    **Fork and clone:**
    ```bash
    gh repo fork owner/repo --clone
    ```

    **Create PR from current branch:**
    ```bash
    gh pr create --title "My changes" --body "Description of changes"
    ```

20. **Report findings:**
    Summarize:
    - Installation status
    - Authentication status
    - Configured settings
    - Available accounts
    - Next steps

## Important notes:
- gh is the official GitHub CLI
- Requires GitHub account
- Can use HTTPS or SSH protocol
- SSH is generally more secure and convenient
- gh can replace many git operations with simpler syntax
- Shell completion is very helpful
- Keep gh updated for latest features
- Multiple accounts are supported
- Works with both GitHub.com and GitHub Enterprise
- Tokens should have minimal required scopes
