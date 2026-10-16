# =============================================================================
# Build a shareable Octop bundle from this checkout (Windows).
#
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File scripts\share\make-share-bundle.ps1
#
# Options:
#   -UvPath <path>    uv.exe to use (default: uv on PATH or the usual install dirs)
#   -SkipFrontend     Reuse an existing src\octop\dashboard build
#
# Output: dist\octop-patched-<version>-<yyyyMMdd>.zip containing
#   octop-<version>-py3-none-any.whl   (backend + built dashboard)
#   install-patched.ps1 / README.txt   (for the person installing it, on Windows)
# =============================================================================
param(
    [string]$UvPath = "",
    [switch]$SkipFrontend
)
$ErrorActionPreference = "Stop"

$RepoRoot   = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ShareDir   = $PSScriptRoot
$OutDir     = Join-Path $RepoRoot "dist"
$StageDir   = Join-Path $OutDir "octop-share"
$Dashboard  = Join-Path $RepoRoot "dashboard"
$IndexHtml  = Join-Path $RepoRoot "src\octop\dashboard\index.html"

function Write-Info { param([string]$Message) Write-Host "[share-bundle] " -ForegroundColor Green -NoNewline; Write-Host $Message }
function Stop-WithError { param([string]$Message) Write-Host "[share-bundle] ERROR: $Message" -ForegroundColor Red; exit 1 }

if ($UvPath) {
    if (-not (Test-Path $UvPath)) { Stop-WithError "uv not found at $UvPath" }
    $Uv = (Resolve-Path $UvPath).Path
} else {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    $Uv = if ($cmd) { $cmd.Source } else {
        @((Join-Path $HOME ".local\bin\uv.exe"), (Join-Path $env:LOCALAPPDATA "uv\uv.exe")) |
            Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $Uv) { Stop-WithError "uv not found. Install it (https://docs.astral.sh/uv/) or pass -UvPath." }
}
Write-Info "uv: $Uv"

# The wheel ships the built dashboard from src\octop\dashboard, so build it first.
if (-not $SkipFrontend) {
    Write-Info "Building dashboard (npm ci + npm run build)..."
    Push-Location $Dashboard
    try {
        npm ci --no-audit
        if ($LASTEXITCODE -ne 0) { Stop-WithError "npm ci failed" }
        npm run build
        if ($LASTEXITCODE -ne 0) { Stop-WithError "dashboard build failed" }
    } finally {
        Pop-Location
    }
}
if (-not (Test-Path $IndexHtml)) { Stop-WithError "Missing $IndexHtml - build the dashboard first." }

Write-Info "Building wheel..."
if (Test-Path $StageDir) { Remove-Item $StageDir -Recurse -Force }
New-Item -ItemType Directory -Path $StageDir -Force | Out-Null
Push-Location $RepoRoot
try {
    & $Uv build --wheel --out-dir $StageDir
    if ($LASTEXITCODE -ne 0) { Stop-WithError "uv build failed" }
} finally {
    Pop-Location
}
$wheel = Get-ChildItem $StageDir -Filter "octop-*.whl" | Select-Object -First 1
if (-not $wheel) { Stop-WithError "No wheel produced." }

# Fail early if the dashboard did not make it into the wheel.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($wheel.FullName)
try {
    $hasDashboard = $zip.Entries | Where-Object { $_.FullName -eq "octop/dashboard/index.html" }
} finally {
    $zip.Dispose()
}
if (-not $hasDashboard) { Stop-WithError "Wheel has no octop/dashboard/index.html." }

Copy-Item (Join-Path $ShareDir "install-patched.ps1") $StageDir
Copy-Item (Join-Path $ShareDir "README.txt") $StageDir

$version = ($wheel.Name -split '-')[1]
$bundle  = Join-Path $OutDir "octop-patched-$version-$(Get-Date -Format yyyyMMdd).zip"
if (Test-Path $bundle) { Remove-Item $bundle -Force }
Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $bundle

Write-Info "Bundle ready: $bundle"
Get-ChildItem $StageDir | ForEach-Object { Write-Info "  $($_.Name)  ($([math]::Round($_.Length / 1KB)) KB)" }
