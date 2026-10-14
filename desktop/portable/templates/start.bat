@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Octop green portable launcher (Windows)
rem Usage:
rem   start.bat
rem   start.bat --home D:\octop-data
rem   start.bat --home .\data --host 0.0.0.0 --port 8088

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "OCTOP_GREEN_PACKAGES=%ROOT%\packages"

if not defined OCTOP_HOME set "OCTOP_HOME=%ROOT%\data"
set "HOST="
set "PORT="
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
echo   bind_host / port      config.json ^(127.0.0.1:8088 when unset^)
echo.
echo --host and --port override config.json and are saved back to it.
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
set "BIND_ARGS="
if defined HOST set "BIND_ARGS=--host %HOST%"
if defined PORT (
  if defined BIND_ARGS (
    set "BIND_ARGS=!BIND_ARGS! --port %PORT%"
  ) else (
    set "BIND_ARGS=--port %PORT%"
  )
)
if defined HOST if defined PORT echo [octop] http://%HOST%:%PORT%
if defined HOST if not defined PORT echo [octop] host=%HOST% ^(port from config.json^)
if not defined HOST if defined PORT echo [octop] port=%PORT% ^(host from config.json^)
if not defined HOST if not defined PORT echo [octop] bind from config.json
"%PY%" "%ROOT%\launch.py" run !BIND_ARGS! %EXTRA%
exit /b %ERRORLEVEL%
