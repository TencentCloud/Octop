# =============================================================================
# Install a patched Octop wheel over an existing Octop install (Windows).
#
# Run from the unzipped bundle folder:
#   powershell -ExecutionPolicy Bypass -File .\install-patched.ps1
#
# Options:
#   -Wheel <path>   Wheel to install (default: newest octop-*.whl next to this script)
#   -NoBackup       Skip the data backup (not recommended)
#   -Yes            Answer "yes" to every prompt
#
# What it does:
#   1. Finds the existing install at %OCTOP_HOME% (default ~\.octop).
#   2. Stops any running Octop from that install (asks first).
#   3. Copies ~\.octop (minus venv / caches) to ~\.octop-backup-<timestamp>.
#   4. Installs the wheel into ~\.octop\venv with uv; your database, agents,
#      providers and config.json are kept. The schema migrates on next start.
# =============================================================================
param(
    [string]$Wheel = "",
    [switch]$NoBackup,
    [switch]$Yes
)
$ErrorActionPreference = "Stop"

$OctopHome  = if ($env:OCTOP_HOME) { $env:OCTOP_HOME } else { Join-Path $HOME ".octop" }
$Venv       = Join-Path $OctopHome "venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$VenvOctop  = Join-Path $Venv "Scripts\octop.exe"
$OfficialInstaller = "https://finnie-1258344699.cos.ap-guangzhou.myqcloud.com/octop/install.ps1"

function Write-Info { param([string]$Message) Write-Host "[octop-patch] " -ForegroundColor Green -NoNewline; Write-Host $Message }
function Write-Warn { param([string]$Message) Write-Host "[octop-patch] " -ForegroundColor Yellow -NoNewline; Write-Host $Message }
function Stop-WithError { param([string]$Message) Write-Host "[octop-patch] ERROR: $Message" -ForegroundColor Red; exit 1 }

function Confirm-Step {
    param([string]$Question)
    if ($Yes) { return $true }
    $answer = Read-Host "$Question [y/N]"
    return $answer -match '^(y|yes)$'
}

function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($candidate in @(
        (Join-Path $HOME ".local\bin\uv.exe"),
        (Join-Path $HOME ".cargo\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "uv\uv.exe")
    )) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

# -- 1. Wheel ----------------------------------------------------------------
if (-not $Wheel) {
    $found = Get-ChildItem -Path $PSScriptRoot -Filter "octop-*.whl" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($found) { $Wheel = $found.FullName }
}
if (-not $Wheel -or -not (Test-Path $Wheel)) {
    Stop-WithError "No octop-*.whl found next to this script. Pass -Wheel <path>."
}
$Wheel = (Resolve-Path $Wheel).Path
Write-Info "Wheel: $Wheel"

# -- 2. Existing install -----------------------------------------------------
if (-not (Test-Path $VenvPython)) {
    Write-Warn "No Octop install found at $Venv."
    Write-Warn "If you use the Octop desktop app, answer N: this script only patches the command-line install."
    if (-not (Confirm-Step "Run the official Octop installer first, then apply this patch?")) {
        Stop-WithError "Aborted. Nothing was changed."
    }
    $installer = Join-Path $env:TEMP "octop-install-$([System.IO.Path]::GetRandomFileName()).ps1"
    Invoke-WebRequest -Uri $OfficialInstaller -OutFile $installer -UseBasicParsing
    # Child process: the official installer may call `exit`, which would end this script too.
    & powershell -NoProfile -ExecutionPolicy Bypass -File $installer
    Remove-Item $installer -ErrorAction SilentlyContinue
    if (-not (Test-Path $VenvPython)) { Stop-WithError "Official installer did not create $Venv." }
}

# -- 3. uv -------------------------------------------------------------------
$Uv = Find-Uv
if (-not $Uv) {
    Write-Warn "uv (the Python package manager Octop's installer uses) was not found."
    if (-not (Confirm-Step "Install uv from astral.sh now?")) { Stop-WithError "uv is required. Aborted." }
    & powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $Uv = Find-Uv
    if (-not $Uv) { Stop-WithError "uv still not found after install. Open a new terminal and re-run." }
}
Write-Info "uv: $Uv"

$before = (& $VenvOctop --version 2>$null | Out-String).Trim()
if ($before) { Write-Info "Current: $before" }

# -- 4. Stop Octop -----------------------------------------------------------
$running = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith($Venv, [System.StringComparison]::OrdinalIgnoreCase) }
if ($running) {
    Write-Warn "Octop is still running (PID $($running.Id -join ', ')). Files in use cannot be replaced."
    if (-not (Confirm-Step "Stop these processes now?")) { Stop-WithError "Close Octop and re-run. Nothing was changed." }
    $running | Stop-Process -Force
    Start-Sleep -Seconds 2
}

# -- 5. Backup ---------------------------------------------------------------
if (-not $NoBackup) {
    $stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
    $backup = Join-Path (Split-Path $OctopHome -Parent) ".octop-backup-$stamp"
    Write-Info "Backing up $OctopHome -> $backup (skipping venv, bin, logs, model/browser caches)..."
    robocopy $OctopHome $backup /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP `
        /XD (Join-Path $OctopHome "venv") (Join-Path $OctopHome "bin") (Join-Path $OctopHome "logs") `
            (Join-Path $OctopHome "embedding_models") (Join-Path $OctopHome "browser-profiles") | Out-Null
    # robocopy: exit codes below 8 mean success.
    if ($LASTEXITCODE -ge 8) { Stop-WithError "Backup failed (robocopy exit $LASTEXITCODE). Nothing was installed." }
    Write-Info "Backup done: $backup"
}

# -- 6. Install --------------------------------------------------------------
Write-Info "Installing patched Octop into $Venv ..."
& $Uv pip install $Wheel --python $VenvPython --reinstall-package octop
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Install failed. Your data is untouched; the old version is still installed unless uv reported otherwise."
    if ($before) { Write-Warn "To force the previous version back: `"$Uv`" pip install `"octop==$(($before -split '\s+')[-1])`" --python `"$VenvPython`"" }
    exit 1
}

$after = (& $VenvOctop --version 2>$null | Out-String).Trim()
Write-Info "Installed: $after"

Write-Info "Done. Start Octop with:  octop run    (then open http://127.0.0.1:8088)"
if (-not $NoBackup) { Write-Info "If anything goes wrong, your previous data is in: $backup" }
