Octop green portable package
============================

Extract this zip anywhere. It includes a portable CPython runtime and Octop
dependencies. No system Python install is required.

Start
-----
  macOS / Linux:  ./start.sh
  Windows:        start.bat

Listen address and port come from data/config.json (default
http://127.0.0.1:8088). Data dir = ./data (OCTOP_HOME).

  ./start.sh --home /path/to/data
  ./start.sh --host 0.0.0.0 --port 8088

--host and --port are saved back to config.json. Omit them to keep the file.

First launch follows the normal Octop setup wizard (create admin password).

Layout
------
  runtime/     portable CPython
  packages/    Octop + locked dependencies (site-packages)
  launch.py    entry bootstrap (loads packages/ + Windows pywin32 DLLs)
  start.sh / start.bat
  README.txt
  VERSION.txt

Notes
-----
  Do not set PYTHONPATH=packages. Always start via start.sh / start.bat /
  launch.py so .pth files (pywin32) are processed.

  macOS: if Gatekeeper quarantines the unzipped folder:

    xattr -dr com.apple.quarantine .

Windows: if import pywintypes fails, rebuild from a current
  green package (launch.py + pywin32 DLL copy). Do not set PYTHONPATH manually.
