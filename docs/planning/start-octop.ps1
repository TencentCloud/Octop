# Octop 本地部署 / 启动脚本
#
#   .\start-octop.ps1              # 直接启动（需已 build 过前端）
#   .\start-octop.ps1 -Build       # 先重新构建前端再启动
#
# 前端产物落在 src/octop/dashboard/（构建产物，不要手改），由 octop run 直接托管。

param(
    [switch]$Build,
    [int]$Port = 8088,
    [string]$HostAddr = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
. D:\nancc\octop\dev-env.ps1 | Out-Null

$repo = 'D:\nancc\octop\Octop-develop'
Set-Location $repo

if ($Build) {
    Write-Host '[build] dashboard/ -> src/octop/dashboard/ ...' -ForegroundColor Cyan
    Push-Location dashboard
    npx tsc -b
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'tsc -b failed' }
    npm run build
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw 'vite build failed' }
    Pop-Location
    Write-Host '[build] done' -ForegroundColor Green
}

# 部署前自检：迁移版本 + 项目表
Write-Host '[check] control plane ...' -ForegroundColor Cyan
$env:OCTOP_HOME = Join-Path $env:USERPROFILE '.octop'
uv run python D:\nancc\octop\_tools\check_local_deploy.py

Write-Host ("[run] http://{0}:{1}" -f $HostAddr, $Port) -ForegroundColor Cyan
uv run octop run --host $HostAddr --port $Port
