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
set "HOST=127.0.0.1"
set "PORT=8088"
set "HOST_SET="
set "PORT_SET="
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
  set "HOST_SET=1"
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
  set "PORT_SET=1"
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
echo   --host / --port       config.json (fresh install: 127.0.0.1:8088)
echo.
echo Without --host/--port the bind address is read from config.json and the
echo launcher never rewrites it.
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

rem Only forward --host/--port the user passed explicitly: `octop run` persists
rem CLI overrides into config.json, so unconditionally passing the launcher
rem defaults rewrote hand-edited bind settings on every start (issue #1816).
set "BIND_ARGS="
if defined HOST_SET set "BIND_ARGS=!BIND_ARGS! --host %HOST%"
if defined PORT_SET set "BIND_ARGS=!BIND_ARGS! --port %PORT%"

echo [octop] home=%OCTOP_HOME%
if defined HOST_SET if defined PORT_SET echo [octop] http://%HOST%:%PORT%
if defined HOST_SET if not defined PORT_SET echo [octop] host %HOST% from --host, port from config.json
if not defined HOST_SET if defined PORT_SET echo [octop] http://127.0.0.1:%PORT% - host from config.json
if not defined HOST_SET if not defined PORT_SET echo [octop] bind host/port come from config.json
"%PY%" "%ROOT%\launch.py" run%BIND_ARGS% %EXTRA%
exit /b %ERRORLEVEL%
