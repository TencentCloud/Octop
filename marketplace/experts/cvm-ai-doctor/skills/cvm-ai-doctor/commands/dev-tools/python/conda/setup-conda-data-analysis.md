---
description: Set up conda environment for data analysis
tags: [python, conda, data-analysis, jupyter, pandas, project, gitignored]
---

You are helping the user set up a conda environment for data analysis.

## Process

1. **Create base environment**
   ```bash
   conda create -n data-analysis python=3.11 -y
   conda activate data-analysis
   ```

2. **Install core data analysis libraries**
   ```bash
   conda install -c conda-forge pandas numpy scipy -y
   ```

3. **Install visualization libraries**
   ```bash
   conda install -c conda-forge matplotlib seaborn plotly -y
   pip install altair
   pip install bokeh
   ```

4. **Install Jupyter ecosystem**
   ```bash
   conda install -c conda-forge jupyter jupyterlab ipywidgets -y
   pip install jupyterlab-git
   pip install jupyterlab-lsp
   ```

5. **Install statistical and ML libraries**
   ```bash
   conda install -c conda-forge scikit-learn statsmodels -y
   pip install scipy
   pip install pingouin        # Statistics
   ```

6. **Install data processing tools**
   ```bash
   conda install -c conda-forge openpyxl xlrd -y  # Excel support
   pip install pyarrow fastparquet  # Parquet support
   pip install sqlalchemy      # Database connectivity
   pip install beautifulsoup4  # Web scraping
   pip install requests        # HTTP requests
   ```

7. **Install data manipulation tools**
   ```bash
   pip install polars          # Fast DataFrame library
   pip install dask            # Parallel computing
   pip install vaex            # Big data processing
   ```

8. **Install database drivers**
   ```bash
   pip install psycopg2-binary  # PostgreSQL
   pip install pymongo          # MongoDB
   pip install redis            # Redis
   ```

9. **Install development tools**
   ```bash
   pip install black           # Code formatting
   pip install pylint          # Linting
   pip install ipdb            # Debugging
   ```

10. **Configure Jupyter extensions**
   - Enable useful extensions
   - Set up theme preferences
   - Configure autosave

11. **Create example notebook**
   - Offer to create `~/notebooks/data-analysis-template.ipynb` with common imports

## Output

Provide a summary showing:
- Environment name and setup status
- Installed libraries grouped by category
- Jupyter Lab configuration
- Example import statements
- Suggested workflows
- Links to documentation
