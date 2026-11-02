---
description: Install pyenv and help user set up various Python versions
tags: [python, development, pyenv, versions, setup, project, gitignored]
---

You are helping the user install pyenv and set up multiple Python versions.

## Process

1. **Check if pyenv is already installed**
   - Run `pyenv --version` to check
   - Check `~/.pyenv` directory

2. **Install pyenv if needed**
   - Install dependencies: `sudo apt install -y make build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev`
   - Clone pyenv: `curl https://pyenv.run | bash`
   - Add to shell config (`~/.bashrc` or `~/.zshrc`):
     ```bash
     export PYENV_ROOT="$HOME/.pyenv"
     export PATH="$PYENV_ROOT/bin:$PATH"
     eval "$(pyenv init -)"
     eval "$(pyenv virtualenv-init -)"
     ```
   - Reload shell: `source ~/.bashrc`

3. **Check currently installed Python versions**
   - Run `pyenv versions` to see installed versions
   - Run `python --version` to see system Python

4. **Work with user to install desired versions**
   - Ask which Python versions they need
   - Show available versions: `pyenv install --list`
   - Common versions to suggest: 3.11.x, 3.12.x, 3.13.x
   - Install versions: `pyenv install 3.12.7` (example)

5. **Configure Python versions**
   - Set global default: `pyenv global 3.12.7`
   - Set local (directory-specific): `pyenv local 3.11.5`
   - Show how to create virtualenvs: `pyenv virtualenv 3.12.7 myproject`

6. **Verify installation**
   - Check active version: `pyenv version`
   - Test Python: `python --version`
   - Test pip: `pip --version`

## Output

Provide a summary showing:
- pyenv installation status
- List of installed Python versions
- Current global/local version settings
- Suggestions for useful versions based on user's needs
