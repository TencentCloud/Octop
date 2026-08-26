@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Octop green portable launcher (Windows)
rem Usage:
rem   start.bat
rem   start.bat --home D:\octop-data
rem   start.bat --home .\data --host 0.0.0.0 --port 8088

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not defined OCTOP_HOME set "OCTOP_HOME=%ROOT%\data"
set "HOST=127.0.0.1"
set "PORT=8088"
set "EXTRA="

:parse
if "%~1"=="" goto run
if /I "%~1"=="--home" (
  if "%~2"=="" (
    echo start.bat: --home requires a path
    exit /b 1
  )
  set "OCTOP_HOME=%~2"
  shift
  shift
  goto parse
)
if /I "%~1"=="--host" (
  if "%~2"=="" (
    echo start.bat: --host requires a value
    exit /b 1
  )
  set "HOST=%~2"
  shift
  shift
  goto parse
)
if /I "%~1"=="--port" (
  if "%~2"=="" (
    echo start.bat: --port requires a value
    exit /b 1
  )
  set "PORT=%~2"
  shift
  shift
  goto parse
)
if /I "%~1"=="-h" goto help
if /I "%~1"=="--help" goto help
set "EXTRA=!EXTRA! %~1"
shift
goto parse

:help
echo Octop green portable launcher
echo.
echo Usage: start.bat [--home DIR] [--host HOST] [--port PORT] [octop run args...]
echo.
echo Defaults:
echo   OCTOP_HOME / --home   %%ROOT%%\data
echo   --host                127.0.0.1
echo   --port                8088
exit /b 0

:run
if not exist "%OCTOP_HOME%" mkdir "%OCTOP_HOME%"

set "PY=%ROOT%\runtime\python.exe"
if not exist "%PY%" (
  echo start.bat: portable Python not found at %PY%
  exit /b 1
)

if not exist "%ROOT%\launch.py" (
  echo start.bat: launch.py missing — rebuild the green package
  exit /b 1
)

rem Prefer launch.py (site.addsitedir + pywin32 DLL path). Do not set PYTHONPATH.
set "PYTHONNOUSERSITE=1"
set "PYTHONPATH="

echo [octop] home=%OCTOP_HOME%
echo [octop] http://%HOST%:%PORT%
"%PY%" "%ROOT%\launch.py" run --host %HOST% --port %PORT% %EXTRA%
exit /b %ERRORLEVEL%
