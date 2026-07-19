@echo off
setlocal EnableDelayedExpansion

REM Octop Installer for Windows (cmd.exe)
REM Usage: install.bat [-Version X.Y.Z] [-FromSource] [-SourceDir DIR] [-Extras browser] [-Help]

if defined OCTOP_HOME (set "OCTOP_HOME=%OCTOP_HOME%") else (set "OCTOP_HOME=%USERPROFILE%\.octop")
set "OCTOP_VENV=%OCTOP_HOME%\venv"
set "OCTOP_BIN=%OCTOP_HOME%\bin"
set "PYTHON_VERSION=3.12"
if defined OCTOP_REPO (set "OCTOP_REPO=%OCTOP_REPO%") else (set "OCTOP_REPO=https://github.com/TencentCloud/Octop.git")

set "ARG_VERSION="
set "ARG_FROM_SOURCE=0"
set "ARG_SOURCE_DIR="
set "ARG_EXTRAS="
set "ARG_UV_PATH="
set "CONSOLE_AVAILABLE=0"

:parse_args
if "%~1"=="" goto :done_args
if /i "%~1"=="-Version"    (set "ARG_VERSION=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="-FromSource" (set "ARG_FROM_SOURCE=1" & shift & goto :parse_args)
if /i "%~1"=="-SourceDir"  (set "ARG_SOURCE_DIR=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="-Extras"     (set "ARG_EXTRAS=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="-UvPath"     (set "ARG_UV_PATH=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="-Help"       goto :show_help
shift
goto :parse_args

:show_help
echo Octop Installer for Windows
echo.
echo Usage: install.bat [OPTIONS]
echo   -Version ^<VER^>     Install specific version
echo   -FromSource        Install from source
echo   -SourceDir ^<DIR^>   Local source directory
echo   -Extras ^<EXTRAS^>  Extra components (e.g. desktop); browser/playwright always installed
echo   -UvPath ^<PATH^>     Pre-installed uv.exe
echo.
echo   Note: if a system Chrome/Chromium is installed (common on GUI systems like
echo         Windows / macOS), the bundled Playwright Chromium download is skipped.
exit /b 0

:done_args
echo [octop] Installing Octop into %OCTOP_HOME%

call :ensure_uv
if errorlevel 1 exit /b 1

if exist "%OCTOP_VENV%" (
    echo [octop] Existing environment found, upgrading...
) else (
    echo [octop] Creating Python %PYTHON_VERSION% environment...
)

uv venv "%OCTOP_VENV%" --python %PYTHON_VERSION% --quiet --clear
if errorlevel 1 (echo [octop] ERROR: Failed to create venv & exit /b 1)

set "VENV_PYTHON=%OCTOP_VENV%\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (echo [octop] ERROR: venv python missing & exit /b 1)

for /f "delims=" %%v in ('"%VENV_PYTHON%" --version 2^>^&1') do set "PY_VERSION=%%v"
echo [octop] Python environment ready (%PY_VERSION%)

set "EXTRAS_SUFFIX=[browser]"
if defined ARG_EXTRAS set "EXTRAS_SUFFIX=[browser,%ARG_EXTRAS%]"
set "VENV_OCTOP=%OCTOP_VENV%\Scripts\octop.exe"

if "%ARG_FROM_SOURCE%"=="1" goto :install_from_source
goto :install_from_pypi

:install_from_source
if defined ARG_SOURCE_DIR goto :install_from_local
goto :install_from_git

:install_from_local
for %%I in ("%ARG_SOURCE_DIR%") do set "ARG_SOURCE_DIR=%%~fI"
echo [octop] Installing from local source: %ARG_SOURCE_DIR%
call :prepare_console "%ARG_SOURCE_DIR%"
uv pip install "%ARG_SOURCE_DIR%%EXTRAS_SUFFIX%" --python "%VENV_PYTHON%"
if errorlevel 1 (echo [octop] ERROR: install failed & exit /b 1)
goto :install_verify

:install_from_git
where git >nul 2>&1
if errorlevel 1 (echo [octop] ERROR: git required & exit /b 1)
set "CLONE_DIR=%TEMP%\octop-install-%RANDOM%"
git clone --depth 1 %OCTOP_REPO% "%CLONE_DIR%"
if errorlevel 1 exit /b 1
call :prepare_console "%CLONE_DIR%"
uv pip install "%CLONE_DIR%%EXTRAS_SUFFIX%" --python "%VENV_PYTHON%"
set "_E=%errorlevel%"
if exist "%CLONE_DIR%" rd /s /q "%CLONE_DIR%"
if %_E% neq 0 exit /b 1
goto :install_verify

:install_from_pypi
set "_PACKAGE=octop"
if defined ARG_VERSION set "_PACKAGE=octop==%ARG_VERSION%"
echo [octop] Installing %_PACKAGE%%EXTRAS_SUFFIX% from PyPI...
uv pip install "%_PACKAGE%%EXTRAS_SUFFIX%" --python "%VENV_PYTHON%"
if errorlevel 1 (echo [octop] ERROR: install failed & exit /b 1)

:install_verify
call :verify_install
if errorlevel 1 exit /b 1
if not exist "%VENV_OCTOP%" (echo [octop] ERROR: octop CLI not found & exit /b 1)
echo [octop] Octop installed successfully

if "%CONSOLE_AVAILABLE%"=="0" (
    "%VENV_PYTHON%" -c "import importlib.resources, octop; p=importlib.resources.files('octop')/'dashboard'/'index.html'; print('yes' if p.is_file() else 'no')" > "%TEMP%\_octop_ui.tmp" 2>&1
    set /p _UI=<"%TEMP%\_octop_ui.tmp"
    del "%TEMP%\_octop_ui.tmp" >nul 2>&1
    if "!_UI!"=="yes" set "CONSOLE_AVAILABLE=1"
)

call :detect_chrome
if defined OCTOP_SYSTEM_CHROME (
    echo [octop] Found system Chrome/Chromium: %OCTOP_SYSTEM_CHROME%
    echo [octop] Using system browser; skipping Playwright Chromium download.
    echo [octop] To use bundled Chromium instead, run: "%VENV_PYTHON%" -m playwright install chromium
    goto :after_browser
)
echo [octop] Installing Playwright Chromium browser...
"%VENV_PYTHON%" -m playwright install chromium
if errorlevel 1 (
    echo [octop] WARNING: Playwright install failed. Run later: "%VENV_PYTHON%" -m playwright install chromium
)
:after_browser

if not exist "%OCTOP_BIN%" mkdir "%OCTOP_BIN%"

echo @echo off > "%OCTOP_BIN%\octop.cmd"
echo set "OCTOP_HOME=%%OCTOP_HOME%%" >> "%OCTOP_BIN%\octop.cmd"
echo if "%%OCTOP_HOME%%"=="" set "OCTOP_HOME=%%USERPROFILE%%\.octop" >> "%OCTOP_BIN%\octop.cmd"
echo "%%OCTOP_HOME%%\venv\Scripts\octop.exe" %%* >> "%OCTOP_BIN%\octop.cmd"

set "OCTOP_BIN_FOR_PS=%OCTOP_BIN%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$bin=$env:OCTOP_BIN_FOR_PS; $cur=[Environment]::GetEnvironmentVariable('Path','User'); if(-not $cur){$cur=''}; $parts=$cur.Split(';')|?{$_}; $ok=$false; foreach($p in $parts){if($p.TrimEnd('\') -ieq $bin.TrimEnd('\')){$ok=$true}}; if(-not $ok){$new=if($cur){$cur.TrimEnd(';')+';'+$bin}else{$bin}; [Environment]::SetEnvironmentVariable('Path',$new,'User'); Write-Host '[octop] Added to User PATH'} else {Write-Host '[octop] Already in User PATH'}"
set "OCTOP_BIN_FOR_PS="
echo %PATH% | findstr /i /c:"%OCTOP_BIN%" >nul || set "PATH=%OCTOP_BIN%;%PATH%"

echo.
echo Octop installed successfully!
echo   Location: %OCTOP_HOME%
echo   Python:   %PY_VERSION%
echo.
echo If 'octop' is not found in this session, run:
echo   set PATH=%OCTOP_BIN%;%%PATH%%
echo Or open a new terminal ^(saved to User PATH^).
echo.
echo Then run:
echo   octop init
echo   octop run
echo   octop service start
echo   http://127.0.0.1:8088
exit /b 0

::detect_chrome
set "OCTOP_SYSTEM_CHROME="
REM Prefer harness-browser's own detector (same path used at runtime)
"%VENV_PYTHON%" -c "from harness_browser.cdp.launcher import find_chrome; p=find_chrome(); print(p or '', end='')" > "%TEMP%\_octop_chrome.tmp" 2>nul
if not errorlevel 1 (
    set /p _CHROME=<"%TEMP%\_octop_chrome.tmp"
)
del "%TEMP%\_octop_chrome.tmp" >nul 2>&1
if defined _CHROME (
    set "OCTOP_SYSTEM_CHROME=%_CHROME%"
    goto :detect_chrome_done
)
REM Fallback: common commands on PATH
for %%c in (chrome google-chrome google-chrome-stable chromium chromium-browser) do (
    where %%c >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%p in ('where %%c') do (set "OCTOP_SYSTEM_CHROME=%%p" & goto :detect_chrome_done)
    )
)
REM Fallback: well-known GUI install paths
for %%p in (
    "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
    "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
    "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
    "%ProgramFiles%\Chromium\Application\chrome.exe"
) do (
    if exist %%p (set "OCTOP_SYSTEM_CHROME=%%~p" & goto :detect_chrome_done)
)
:detect_chrome_done
exit /b 0

:ensure_uv
if defined ARG_UV_PATH (
    if not exist "%ARG_UV_PATH%" (echo [octop] ERROR: uv not found & exit /b 1)
    for %%I in ("%ARG_UV_PATH%") do set "PATH=%%~dpI;!PATH!"
    goto :ensure_uv_done
)
where uv >nul 2>&1
if not errorlevel 1 goto :ensure_uv_done
for %%c in ("%USERPROFILE%\.local\bin\uv.exe" "%LOCALAPPDATA%\uv\uv.exe") do (
    if exist %%c (set "PATH=%%~dpc;!PATH!" & goto :ensure_uv_done)
)
echo [octop] Installing uv...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 -TimeoutSec 15 | iex" 2>nul
if not errorlevel 1 goto :ensure_uv_refresh
echo [octop] astral.sh failed, trying GitHub...
call :download_uv_github
if errorlevel 1 exit /b 1
goto :ensure_uv_done

:ensure_uv_refresh
for %%p in ("%USERPROFILE%\.local\bin" "%LOCALAPPDATA%\uv") do (
    if exist %%p echo "!PATH!" | findstr /i /c:"%%~p" >nul || set "PATH=%%~p;!PATH!"
)
where uv >nul 2>&1 || (echo [octop] ERROR: uv install failed & exit /b 1)
:ensure_uv_done
exit /b 0

:download_uv_github
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" (set "_A=aarch64") else (set "_A=x86_64")
set "_Z=%TEMP%\uv-%RANDOM%.zip"
set "_D=%LOCALAPPDATA%\uv"
curl -L -o "!_Z!" "https://github.com/astral-sh/uv/releases/latest/download/uv-!_A!-pc-windows-msvc.zip" 2>nul
if errorlevel 1 powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/astral-sh/uv/releases/latest/download/uv-!_A!-pc-windows-msvc.zip' -OutFile '!_Z!' -UseBasicParsing"
if not exist "!_D!" mkdir "!_D!"
powershell -NoProfile -Command "Expand-Archive -Force '!_Z!' '!_D!'"
del "!_Z!" >nul 2>&1
set "PATH=!_D!;!PATH!"
exit /b 0

:prepare_console
set "_RD=%~1"
set "_DEST=%_RD%\src\octop\dashboard"
if exist "%_DEST%\index.html" (set "CONSOLE_AVAILABLE=1" & exit /b 0)
if not exist "%_RD%\dashboard\package.json" exit /b 0
where npm >nul 2>&1 || exit /b 0
echo [octop] Building dashboard...
pushd "%_RD%\dashboard"
npm ci && npm run build
popd
if exist "%_DEST%\index.html" set "CONSOLE_AVAILABLE=1"
exit /b 0

:verify_install
echo [octop] Verifying installation...
"%VENV_PYTHON%" -c "from octop.infra.agents.manager import AgentManager" >nul 2>&1
if errorlevel 1 (echo [octop] ERROR: install verification failed & exit /b 1)
echo [octop] Install verification passed
exit /b 0
