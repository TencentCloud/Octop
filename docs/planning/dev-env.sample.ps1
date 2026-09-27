# Octop 开发环境一键脚本
#   . .\dev-env.ps1        （点号加载到当前会话）
# 或：pwsh -NoExit -File .\dev-env.ps1
#
# 解决本机实测的 4 个坑：
#   1) 本仓库 Makefile 需要 Unix shell  → 加 Git 的 usr/bin 到 PATH
#   2) 中文 Windows locale 是 GBK      → PYTHONUTF8=1（否则 tests/unit/db 18 个失败）
#   3) git 不读 Windows 系统代理        → github.com HTTPS 被阻断时用 SSH/proxy
#   4) Git autocrlf=true               → 已设为 false（仓库级，见 §6.2）

$ErrorActionPreference = 'Continue'

# --- 1) PATH ---
#   关键：必须从注册表重建 PATH。否则在"安装完工具但宿主进程未重启"的场景里
#   看不到新装的 git / make（进程环境块是启动时的快照）。
$gitCmd    = 'C:\Program Files\Git\cmd'          # git.exe 本体
$gitUsrBin = 'C:\Program Files\Git\usr\bin'      # sh / pwd / chmod —— make 需要它当 SHELL
$pgBin     = 'D:\nancc\tools\pgsql\pgsql\bin'    # psql / pg_dump / pg_restore

$machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$userPath    = [Environment]::GetEnvironmentVariable('Path', 'User')
$prepend     = @($gitCmd, $gitUsrBin, $pgBin) | Where-Object { Test-Path $_ }
$env:Path    = (@($prepend) + @($machinePath, $userPath) | Where-Object { $_ }) -join ';'

# --- 2) Python UTF-8 模式（关键：中文 Windows 必须）---
$env:PYTHONUTF8 = '1'
$env:UV_LINK_MODE = 'copy'

# --- 3) PostgreSQL 测试 DSN（Docker 容器 octop-pg）---
$env:OCTOP_TEST_DATABASE_URL = 'postgresql://octop:octop_dev_pw@127.0.0.1:5432/octop'

# --- 4) 自检 ---
Write-Host '=== Octop 开发环境 ===' -ForegroundColor Cyan
foreach ($c in 'git', 'make', 'uv', 'node', 'psql', 'pg_dump') {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    $mark = if ($cmd) { '[OK]  ' } else { '[MISS]' }
    $color = if ($cmd) { 'Green' } else { 'Red' }
    Write-Host ("  {0} {1,-8} {2}" -f $mark, $c, $(if ($cmd) { $cmd.Source } else { '未安装' })) -ForegroundColor $color
}
Write-Host ("  PYTHONUTF8 = {0}" -f $env:PYTHONUTF8)
Write-Host ("  TEST DSN   = {0}" -f $env:OCTOP_TEST_DATABASE_URL)

$repo = 'D:\nancc\octop\Octop-develop'
if (Test-Path $repo) {
    Push-Location $repo
    $br = git branch --show-current 2>$null
    $dirty = (git status --porcelain 2>$null | Measure-Object).Count
    Write-Host ("  repo       = {0}  branch={1}  dirty={2}" -f $repo, $br, $dirty) -ForegroundColor $(if ($dirty -eq 0) { 'Green' } else { 'Yellow' })
    Pop-Location
}

# PG 连通性
if (Get-Command pg_isready -ErrorAction SilentlyContinue) {
    $r = pg_isready -h 127.0.0.1 -p 5432 -U octop -d octop 2>&1
    Write-Host ("  PG 5432    = {0}" -f $r) -ForegroundColor $(if ($LASTEXITCODE -eq 0) { 'Green' } else { 'Red' })
}

Write-Host ''
Write-Host '常用命令：' -ForegroundColor Cyan
Write-Host '  cd D:\nancc\octop\Octop-develop'
Write-Host '  make all                      # 全量门禁（约 7-8 分钟）'
Write-Host '  uv run pytest tests/unit/db -q'
Write-Host '  uv run pytest -m postgresql -q  # 需 DSN，本脚本已设'
Write-Host '  docker start octop-pg         # PG 容器（--restart unless-stopped 会自动起）'
