# Install pipx and Suggest Packages

You are helping the user install pipx and suggesting useful packages to install with it.

## Your tasks:

1. **Explain what pipx is:**
   pipx is a tool to install and run Python applications in isolated environments. Unlike pip which installs packages globally or in the current environment, pipx creates a separate virtual environment for each application.

2. **Check if pipx is already installed:**
   ```bash
   which pipx
   pipx --version
   ```

   If already installed:
   ```bash
   pipx list
   ```

3. **Install pipx:**

   **Method 1: Using apt (Ubuntu 23.04+):**
   ```bash
   sudo apt update
   sudo apt install pipx
   ```

   **Method 2: Using pip:**
   ```bash
   python3 -m pip install --user pipx
   python3 -m pipx ensurepath
   ```

   **Method 3: Using Homebrew (if installed):**
   ```bash
   brew install pipx
   ```

4. **Ensure pipx is on PATH:**
   ```bash
   pipx ensurepath
   ```

   Then restart shell or:
   ```bash
   source ~/.bashrc
   ```

5. **Verify installation:**
   ```bash
   pipx --version
   which pipx
   pipx list
   ```

6. **Explain pipx benefits:**
   - Each app in isolated environment (no dependency conflicts)
   - Easy to install/uninstall applications
   - Applications available system-wide
   - No need to activate virtual environments
   - Perfect for CLI tools
   - Automatic PATH configuration

7. **Show basic pipx usage:**
   - `pipx install <package>` - Install a package
   - `pipx uninstall <package>` - Uninstall a package
   - `pipx list` - List installed packages
   - `pipx upgrade <package>` - Upgrade a package
   - `pipx upgrade-all` - Upgrade all packages
   - `pipx run <package>` - Run without installing
   - `pipx inject <package> <dependency>` - Add dependency to app

8. **Suggest essential Python CLI tools:**

   **Development tools:**
   ```bash
   pipx install black          # Code formatter
   pipx install flake8         # Linter
   pipx install pylint         # Code analyzer
   pipx install mypy           # Static type checker
   pipx install isort          # Import sorter
   pipx install autopep8       # Auto formatter
   pipx install bandit         # Security linter
   ```

   **Project management:**
   ```bash
   pipx install poetry         # Dependency management
   pipx install pipenv         # Virtual environment manager
   pipx install cookiecutter   # Project templates
   pipx install tox            # Testing automation
   ```

   **Productivity tools:**
   ```bash
   pipx install httpie         # HTTP client (better than curl)
   pipx install youtube-dl     # Download videos
   pipx install yt-dlp         # youtube-dl fork (maintained)
   pipx install tldr           # Simplified man pages
   pipx install howdoi         # Code search from command line
   ```

   **Data science & analysis:**
   ```bash
   pipx install jupyter        # Jupyter notebooks
   pipx install jupyterlab     # JupyterLab
   pipx install datasette      # Data exploration
   pipx install csvkit         # CSV tools
   ```

   **File & text processing:**
   ```bash
   pipx install pdfplumber     # PDF text extraction
   pipx install pdf2image      # PDF to image converter
   pipx install rich-cli       # Rich text in terminal
   pipx install glances        # System monitoring
   ```

   **Cloud & infrastructure:**
   ```bash
   pipx install ansible        # Automation
   pipx install aws-cli        # AWS command line
   pipx install httpie         # API testing
   pipx install docker-compose # Docker orchestration
   ```

   **Documentation:**
   ```bash
   pipx install mkdocs         # Documentation generator
   pipx install sphinx         # Documentation tool
   pipx install doc8           # Documentation linter
   ```

   **Testing & quality:**
   ```bash
   pipx install pytest         # Testing framework
   pipx install coverage       # Code coverage
   pipx install pre-commit     # Git hooks manager
   ```

9. **Suggest packages based on user's interests:**
   Ask the user what they work with:
   - Web development?
   - Data science?
   - DevOps?
   - Security?
   - Content creation?

   Then suggest relevant packages.

10. **Install a few essential packages:**
    Recommend installing at minimum:
    ```bash
    pipx install httpie         # Better HTTP client
    pipx install tldr           # Quick command help
    pipx install black          # Python formatter (if they code)
    pipx install glances        # System monitor
    ```

11. **Show how to use pipx run (temporary usage):**
    ```bash
    # Run without installing
    pipx run pycowsay "Hello!"
    pipx run black --version

    # Useful for one-off tasks
    pipx run cookiecutter gh:audreyr/cookiecutter-pypackage
    ```

12. **Show how to manage installations:**

    **List all installed apps:**
    ```bash
    pipx list
    pipx list --verbose
    ```

    **Upgrade specific package:**
    ```bash
    pipx upgrade black
    ```

    **Upgrade all packages:**
    ```bash
    pipx upgrade-all
    ```

    **Uninstall package:**
    ```bash
    pipx uninstall black
    ```

    **Reinstall package:**
    ```bash
    pipx reinstall black
    ```

13. **Show how to inject additional dependencies:**
    Some apps need extra packages:
    ```bash
    pipx install ansible
    pipx inject ansible ansible-lint
    pipx inject ansible molecule
    ```

14. **Configure pipx:**

    **Check current configuration:**
    ```bash
    pipx environment
    ```

    **Change installation location (if needed):**
    ```bash
    export PIPX_HOME=~/.local/pipx
    export PIPX_BIN_DIR=~/.local/bin
    ```

15. **Show differences between pip and pipx:**
    - `pip install <package>` - Installs in current environment
    - `pipx install <package>` - Installs in isolated environment
    - Use pip for: libraries, dependencies
    - Use pipx for: CLI applications, standalone tools

16. **Troubleshooting:**

    **Package not in PATH:**
    ```bash
    pipx ensurepath
    source ~/.bashrc
    echo $PATH | grep .local/bin
    ```

    **Broken installation:**
    ```bash
    pipx reinstall <package>
    ```

    **Clean up:**
    ```bash
    pipx uninstall-all
    ```

17. **Advanced usage:**

    **Specify Python version:**
    ```bash
    pipx install --python python3.11 black
    ```

    **Install from git:**
    ```bash
    pipx install git+https://github.com/user/repo.git
    ```

    **Install with extras:**
    ```bash
    pipx install 'package[extra1,extra2]'
    ```

18. **Integration with other tools:**

    **pre-commit integration:**
    ```bash
    pipx install pre-commit
    pre-commit install
    ```

    **VSCode integration:**
    - Installed tools (black, flake8, mypy) are auto-detected
    - No need to install in each project

19. **Maintenance commands:**
    ```bash
    # Update pipx itself
    python3 -m pip install --user --upgrade pipx

    # Upgrade all installed packages
    pipx upgrade-all

    # List outdated packages
    pipx list --verbose | grep -A 2 "upgrade available"
    ```

20. **Provide recommendations:**
    - Use pipx for all Python CLI tools
    - Keep applications updated with `pipx upgrade-all`
    - Don't use pip for global installations anymore
    - Use `pipx run` to try packages before installing
    - Install project-specific tools (black, flake8) with pipx
    - Consider adding `pipx upgrade-all` to crontab
    - Keep separate from project dependencies (use venv/poetry for those)

21. **Show common workflow:**
    ```bash
    # Install essential tools
    pipx install black
    pipx install flake8
    pipx install mypy

    # In your project
    cd my-project
    black .
    flake8 .
    mypy .

    # No need to activate virtual environment!
    ```

## Important notes:
- pipx requires Python 3.6+
- Each app gets its own virtual environment
- Apps are available system-wide after installation
- Perfect for CLI tools, not for libraries
- Keeps system Python clean
- No dependency conflicts between apps
- Must be on PATH - use `pipx ensurepath`
- Can coexist with pip and venv
- Use pip for project dependencies, pipx for tools
- Regular updates recommended: `pipx upgrade-all`
