# Manage Conda Environments

You are helping the user list conda environments and work with them to add packages.

## Your tasks:

1. **Check if conda is installed:**
   ```bash
   which conda
   conda --version
   conda info
   ```

   If not installed, offer to help install Miniconda or Anaconda.

2. **List all conda environments:**
   ```bash
   conda env list
   # or
   conda info --envs
   ```

   This shows:
   - All environment names
   - Their locations
   - Current active environment (marked with *)

3. **Show current environment:**
   ```bash
   echo $CONDA_DEFAULT_ENV
   conda info --envs | grep "*"
   ```

4. **Display detailed environment information:**
   For each environment, show:
   ```bash
   # List packages in specific environment
   conda list -n <env-name>

   # Show environment details
   conda env export -n <env-name>

   # Show size
   du -sh ~/miniconda3/envs/<env-name>
   # or
   du -sh ~/anaconda3/envs/<env-name>
   ```

5. **Ask user which environment to work with:**
   Present the list and ask which environment they want to modify or examine.

6. **Activate environment:**
   ```bash
   conda activate <env-name>
   ```

   Verify activation:
   ```bash
   conda info --envs
   python --version
   which python
   ```

7. **Show packages in environment:**
   ```bash
   conda list
   # or for specific environment
   conda list -n <env-name>

   # Show only explicitly installed packages
   conda env export --from-history -n <env-name>
   ```

8. **Search for packages:**
   Ask what packages user wants to install:
   ```bash
   conda search <package-name>
   conda search <package-name> --info
   ```

9. **Install packages:**

   **Single package:**
   ```bash
   conda install <package-name>
   # or specify environment
   conda install -n <env-name> <package-name>
   ```

   **Multiple packages:**
   ```bash
   conda install <package1> <package2> <package3>
   ```

   **Specific version:**
   ```bash
   conda install <package-name>=<version>
   # Example:
   conda install python=3.11
   conda install numpy=1.24.0
   ```

   **From specific channel:**
   ```bash
   conda install -c conda-forge <package-name>
   ```

10. **Suggest common packages by category:**

    **Data Science:**
    ```bash
    conda install numpy pandas matplotlib seaborn scikit-learn
    conda install jupyter jupyterlab notebook
    conda install scipy statsmodels
    ```

    **Machine Learning:**
    ```bash
    conda install tensorflow pytorch torchvision
    conda install keras scikit-learn xgboost
    conda install -c conda-forge lightgbm
    ```

    **Development:**
    ```bash
    conda install ipython black flake8 pytest
    conda install requests beautifulsoup4 selenium
    conda install flask django fastapi
    ```

    **Visualization:**
    ```bash
    conda install matplotlib seaborn plotly
    conda install bokeh altair
    ```

    **Database:**
    ```bash
    conda install sqlalchemy psycopg2 pymongo
    conda install sqlite
    ```

11. **Update packages:**

    **Update specific package:**
    ```bash
    conda update <package-name>
    ```

    **Update all packages in environment:**
    ```bash
    conda update --all
    ```

    **Update conda itself:**
    ```bash
    conda update conda
    ```

12. **Remove packages:**
    ```bash
    conda remove <package-name>
    # or from specific environment
    conda remove -n <env-name> <package-name>
    ```

13. **Create new environment:**
    Offer to create a new environment:
    ```bash
    # Basic environment
    conda create -n <env-name> python=3.11

    # With packages
    conda create -n myenv python=3.11 numpy pandas jupyter

    # From file
    conda env create -f environment.yml
    ```

14. **Export environment:**
    Help user export environment for sharing:

    **Full export (with all dependencies):**
    ```bash
    conda env export -n <env-name> > environment.yml
    ```

    **Only explicitly installed packages:**
    ```bash
    conda env export --from-history -n <env-name> > environment.yml
    ```

    **As requirements.txt:**
    ```bash
    conda list -n <env-name> --export > requirements.txt
    ```

15. **Clone environment:**
    ```bash
    conda create --name <new-env> --clone <existing-env>
    ```

16. **Clean up conda:**
    ```bash
    # Remove unused packages and caches
    conda clean --all

    # Remove packages cache
    conda clean --packages

    # Remove tarballs
    conda clean --tarballs

    # Check what would be removed
    conda clean --all --dry-run
    ```

17. **Check environment conflicts:**
    ```bash
    # Check for broken dependencies
    conda info <package-name>

    # Verify environment
    conda env export -n <env-name> | conda env create -n test-env -f -
    ```

18. **Show environment size:**
    ```bash
    # Size of all environments
    du -sh ~/miniconda3/envs/*
    # or
    du -sh ~/anaconda3/envs/*

    # Total conda size
    du -sh ~/miniconda3
    ```

19. **Configure conda:**

    **Add channels:**
    ```bash
    conda config --add channels conda-forge
    conda config --add channels bioconda
    ```

    **Set channel priority:**
    ```bash
    conda config --set channel_priority strict
    ```

    **Show configuration:**
    ```bash
    conda config --show
    conda config --show channels
    ```

    **Remove channel:**
    ```bash
    conda config --remove channels <channel-name>
    ```

20. **Use mamba (faster alternative):**
    If user has performance issues:
    ```bash
    # Install mamba
    conda install mamba -n base -c conda-forge

    # Use mamba instead of conda
    mamba install <package-name>
    mamba search <package-name>
    mamba env create -f environment.yml
    ```

21. **Troubleshooting common issues:**

    **Environment not activating:**
    ```bash
    conda init bash
    source ~/.bashrc
    ```

    **Package conflicts:**
    ```bash
    # Create new environment instead
    conda create -n new-env python=3.11 <packages>
    ```

    **Slow package resolution:**
    ```bash
    # Use mamba
    conda install mamba -c conda-forge
    # or
    conda config --set solver libmamba
    ```

    **Conda command not found:**
    ```bash
    export PATH="$HOME/miniconda3/bin:$PATH"
    conda init bash
    ```

22. **Best practices to share:**
    - Create separate environment for each project
    - Use environment.yml for reproducibility
    - Pin important package versions
    - Use conda-forge channel for latest packages
    - Regularly clean up with `conda clean --all`
    - Don't install packages in base environment
    - Use mamba for faster package resolution
    - Export environments before major changes
    - Keep Python version explicit in environment
    - Use `--from-history` for cross-platform compatibility

23. **Show workflow example:**
    ```bash
    # Create environment
    conda create -n data-project python=3.11

    # Activate it
    conda activate data-project

    # Install packages
    conda install numpy pandas jupyter matplotlib scikit-learn

    # Verify
    conda list

    # Export for sharing
    conda env export --from-history > environment.yml

    # Deactivate when done
    conda deactivate
    ```

24. **Integration with Jupyter:**
    ```bash
    # Install ipykernel in environment
    conda activate <env-name>
    conda install ipykernel

    # Register environment as Jupyter kernel
    python -m ipykernel install --user --name=<env-name>

    # Now available in Jupyter
    jupyter lab
    ```

25. **Report current status:**
    Summarize:
    - Number of environments
    - Active environment
    - Total disk usage
    - conda version
    - Suggested actions based on user needs

## Important notes:
- Always activate environment before installing packages
- Base environment should be kept minimal
- Use `-n <env-name>` to work with environments without activating
- conda-forge channel has more packages than default
- mamba is drop-in replacement, much faster
- Environment.yml files ensure reproducibility
- Pin versions in production environments
- Clean up regularly to save disk space
- Don't mix pip and conda unless necessary (prefer conda)
- Use `--from-history` when exporting for other OS
- Jupyter needs ipykernel in each environment
- conda init modifies .bashrc - check if needed
