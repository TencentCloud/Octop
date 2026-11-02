# Python Environment Manager Identification

You are helping the user identify their system Python installation and all Python environment managers in use.

## Your tasks:

1. **Identify system Python:**
   - System Python version: `python3 --version`
   - System Python location: `which python3`
   - Check if python (unversioned) exists: `which python`
   - Python paths: `python3 -c "import sys; print(sys.executable)"`
   - List all Python installations: `which -a python python3 python2`

2. **Check for pyenv:**
   - Check if installed: `which pyenv`
   - If installed:
     - Version: `pyenv --version`
     - Root directory: `echo $PYENV_ROOT` or default `~/.pyenv`
     - Installed Python versions: `pyenv versions`
     - Global Python: `pyenv global`
     - Local Python (if set): `pyenv local`
     - Check if properly initialized in shell: `grep -r "pyenv init" ~/.bashrc ~/.zshrc ~/.profile 2>/dev/null`

3. **Check for Conda/Miniconda/Anaconda:**
   - Check if conda is installed: `which conda`
   - If installed:
     - Version: `conda --version`
     - Conda info: `conda info`
     - Base environment location: `echo $CONDA_PREFIX`
     - List environments: `conda env list`
     - Current environment: `echo $CONDA_DEFAULT_ENV`
     - Check initialization: `grep -r "conda initialize" ~/.bashrc ~/.zshrc ~/.profile 2>/dev/null`

4. **Check for Mamba:**
   - Check if installed: `which mamba`
   - If installed:
     - Version: `mamba --version`
     - Environments: `mamba env list`

5. **Check for Poetry:**
   - Check if installed: `which poetry`
   - If installed:
     - Version: `poetry --version`
     - Config location: `poetry config --list`
     - Virtual environment settings: `poetry config virtualenvs.path`

6. **Check for pipenv:**
   - Check if installed: `which pipenv`
   - If installed:
     - Version: `pipenv --version`
     - Environment variable settings: `echo $PIPENV_VENV_IN_PROJECT`

7. **Check for virtualenv/venv:**
   - Check if virtualenv is installed: `which virtualenv`
   - Check for virtualenvwrapper: `which virtualenvwrapper.sh`
   - If virtualenvwrapper found:
     - Check workon home: `echo $WORKON_HOME`
     - List environments: `lsvirtualenv` (if available)

8. **Check for other Python version managers:**
   - asdf with Python plugin: `which asdf` and `asdf plugin list | grep python`
   - pythonz: `which pythonz`
   - Check for manual Python installations in common locations:
     - `/usr/local/bin/python*`
     - `/opt/python*`
     - `~/.local/bin/python*`

9. **Analyze pip installations:**
   - System pip: `pip3 --version`
   - Pip location: `which pip3 pip`
   - User site packages: `python3 -m site --user-site`
   - List globally installed packages: `pip3 list --user`

10. **Report summary:**
    - System Python version and location
    - All detected environment managers with versions
    - Which manager is currently active (if any)
    - Any conflicts or issues detected (e.g., multiple managers competing)
    - Recommendations:
      - If no environment manager is detected, suggest installing one (pyenv or conda)
      - If multiple managers are detected, explain their different use cases
      - Suggest best practices for the detected setup
      - Warn about potential PATH conflicts

## Important notes:
- Don't use sudo for these checks (environment managers are typically user-level)
- Be clear about which Python is currently active vs. available
- Explain the difference between system Python and managed versions
- If shell initialization is missing for detected managers, point that out
