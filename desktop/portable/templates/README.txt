Octop green portable package
============================

Extract this zip anywhere. It includes a portable CPython runtime and Octop
dependencies. No system Python install is required.

Start
-----
  macOS / Linux:  ./start.sh
  Windows:        start.bat

Defaults: http://127.0.0.1:8088   data dir = ./data (OCTOP_HOME)

  ./start.sh --home /path/to/data --host 127.0.0.1 --port 8088

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
