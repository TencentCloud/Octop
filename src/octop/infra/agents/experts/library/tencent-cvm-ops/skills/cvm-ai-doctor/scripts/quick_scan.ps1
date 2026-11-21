# ==============================================================================
# CVM Doctor Quick Scan (Windows PowerShell)
# ==============================================================================
# Purpose: Fast triage to identify which components need deep analysis
# Duration: ~5 seconds
# Checks: CPU queue, Memory available, Disk queue, Network drops (rate)
# Output: Structured text (parseable by AI)
# ==============================================================================

$ErrorActionPreference = "SilentlyContinue"

$OS = "Windows"
$TIMESTAMP = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

Write-Output "=== CVM QUICK HEALTH CHECK ==="
Write-Output "Platform: $OS"
Write-Output "Timestamp: $TIMESTAMP"
Write-Output ""

# ==============================================================================
# Check 1: CPU Queue Saturation
# ==============================================================================
# Processor Queue Length 是瞬时值，正常波动大，阈值需宽松
Write-Output "--- CPU CHECK ---"

$CPU_CORES = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors
$RUN_QUEUE = (Get-Counter '\System\Processor Queue Length' -ErrorAction SilentlyContinue).CounterSamples[0].CookedValue

if ($null -eq $CPU_CORES) { $CPU_CORES = 1 }
if ($null -eq $RUN_QUEUE) { $RUN_QUEUE = 0 }

Write-Output "CPU Cores: $CPU_CORES"
Write-Output "Run Queue: $RUN_QUEUE"

if ($RUN_QUEUE -gt ($CPU_CORES * 4)) {
    Write-Output "Status: CRITICAL"
    Write-Output "Reason: Run queue ($RUN_QUEUE) > 4x cores ($CPU_CORES)"
    $_STAT_CPU = "critical"
} elseif ($RUN_QUEUE -gt ($CPU_CORES * 2)) {
    Write-Output "Status: WARNING"
    Write-Output "Reason: Run queue ($RUN_QUEUE) > 2x cores ($CPU_CORES)"
    $_STAT_CPU = "warning"
} else {
    Write-Output "Status: OK"
    $_STAT_CPU = "ok"
}
Write-Output ""

# ==============================================================================
# Check 2: Memory Available (not page file — page file usage is normal on Windows)
# ==============================================================================
Write-Output "--- MEMORY CHECK ---"

$osInfo = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
if ($null -ne $osInfo) {
    $TOTAL_MB = [Math]::Round($osInfo.TotalVisibleMemorySize / 1024)
    $FREE_MB = [Math]::Round($osInfo.FreePhysicalMemory / 1024)
    $USED_PCT = [Math]::Round(($TOTAL_MB - $FREE_MB) / $TOTAL_MB * 100, 1)
    $AVAIL_PCT = [Math]::Round($FREE_MB / $TOTAL_MB * 100, 1)
} else {
    $TOTAL_MB = 0; $FREE_MB = 0; $USED_PCT = 0; $AVAIL_PCT = 100
}

# Page file 仅作参考
$PageFile = Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue
$PAGE_USED = if ($null -ne $PageFile) { [Math]::Round($PageFile.CurrentUsage) } else { 0 }

Write-Output "Total Memory: ${TOTAL_MB}MB"
Write-Output "Available: ${FREE_MB}MB ($AVAIL_PCT%)"
Write-Output "Used: $USED_PCT%"
Write-Output "Page File Used: ${PAGE_USED}MB (reference only)"

if ($AVAIL_PCT -le 5) {
    Write-Output "Status: CRITICAL"
    Write-Output "Reason: Available memory $AVAIL_PCT% <= 5%"
    $_STAT_MEM = "critical"
} elseif ($AVAIL_PCT -le 15) {
    Write-Output "Status: WARNING"
    Write-Output "Reason: Available memory $AVAIL_PCT% <= 15%"
    $_STAT_MEM = "warning"
} else {
    Write-Output "Status: OK"
    $_STAT_MEM = "ok"
}
Write-Output ""

# ==============================================================================
# Check 3: Disk I/O Queue Length
# ==============================================================================
# Avg. Disk Queue Length 是队列深度，不是百分比
# Microsoft 推荐: < 2 正常, 2-5 关注, > 5 瓶颈
Write-Output "--- DISK CHECK ---"

$DiskQueue = (Get-Counter '\PhysicalDisk(_Total)\Avg. Disk Queue Length' -ErrorAction SilentlyContinue).CounterSamples[0].CookedValue

if ($null -eq $DiskQueue) { $DiskQueue = 0 }
$DiskQueue = [Math]::Round($DiskQueue, 2)

Write-Output "Disk Queue Length: $DiskQueue"

if ($DiskQueue -ge 5) {
    Write-Output "Status: CRITICAL"
    Write-Output "Reason: Disk queue $DiskQueue >= 5 (severe I/O bottleneck)"
    $_STAT_DISK = "critical"
} elseif ($DiskQueue -ge 2) {
    Write-Output "Status: WARNING"
    Write-Output "Reason: Disk queue $DiskQueue >= 2 (elevated I/O)"
    $_STAT_DISK = "warning"
} else {
    Write-Output "Status: OK"
    $_STAT_DISK = "ok"
}
Write-Output ""

# ==============================================================================
# Check 4: Network Packet Drops (2-second delta, same as Linux/macOS)
# ==============================================================================
Write-Output "--- NETWORK CHECK ---"

$adapters = Get-NetAdapterStatistics -ErrorAction SilentlyContinue

if ($null -ne $adapters) {
    $RX1 = ($adapters | Measure-Object ReceivedDiscardedPackets -Sum -ErrorAction SilentlyContinue).Sum
    $TX1 = ($adapters | Measure-Object OutboundDiscardedPackets -Sum -ErrorAction SilentlyContinue).Sum
    if ($null -eq $RX1) { $RX1 = 0 }
    if ($null -eq $TX1) { $TX1 = 0 }

    Start-Sleep -Seconds 2

    $adapters2 = Get-NetAdapterStatistics -ErrorAction SilentlyContinue
    $RX2 = ($adapters2 | Measure-Object ReceivedDiscardedPackets -Sum -ErrorAction SilentlyContinue).Sum
    $TX2 = ($adapters2 | Measure-Object OutboundDiscardedPackets -Sum -ErrorAction SilentlyContinue).Sum
    if ($null -eq $RX2) { $RX2 = 0 }
    if ($null -eq $TX2) { $TX2 = 0 }

    $RX_DROPS = [Math]::Floor(($RX2 - $RX1) / 2)
    $TX_DROPS = [Math]::Floor(($TX2 - $TX1) / 2)
} else {
    $RX_DROPS = 0
    $TX_DROPS = 0
}

$TOTAL_DROPS = $RX_DROPS + $TX_DROPS

Write-Output "RX Drops: $RX_DROPS/s"
Write-Output "TX Drops: $TX_DROPS/s"
Write-Output "Total Drops: $TOTAL_DROPS/s"

if ($TOTAL_DROPS -ge 50) {
    Write-Output "Status: CRITICAL"
    Write-Output "Reason: Drop rate >= 50/s (active packet loss)"
    $_STAT_NET = "critical"
} elseif ($TOTAL_DROPS -ge 5) {
    Write-Output "Status: WARNING"
    Write-Output "Reason: Drop rate >= 5/s"
    $_STAT_NET = "warning"
} else {
    Write-Output "Status: OK"
    $_STAT_NET = "ok"
}

Write-Output ""
Write-Output "=== QUICK CHECK COMPLETE ==="

# ==============================================================================
# Stats Logging — write JSONL record to match analyze_stats.sh format
# ==============================================================================
$StatsFile = "$env:USERPROFILE\.lightclaw\stats\cvm-doctor.jsonl"
$StatsDir  = Split-Path $StatsFile -Parent
if (-not (Test-Path $StatsDir)) { New-Item -ItemType Directory -Path $StatsDir -Force | Out-Null }

$issues = 0
$severity = "ok"
foreach ($s in @($_STAT_CPU, $_STAT_MEM, $_STAT_DISK, $_STAT_NET)) {
    if ($s -eq "critical") { $issues++; $severity = "critical" }
    elseif ($s -eq "warning") { $issues++; if ($severity -ne "critical") { $severity = "warning" } }
}

$Duration = [Math]::Round(((Get-Date) - (Get-Date $TIMESTAMP)).TotalSeconds, 1)
$Hostname = $env:COMPUTERNAME
$record = "{""ts"":""$TIMESTAMP"",""ts_local"":""$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"",""mode"":""quick"",""scenario"":""health_check"",""hostname"":""$Hostname"",""os"":""windows"",""duration_s"":$Duration,""components"":{""cpu"":{""status"":""$_STAT_CPU"",""detail"":""""},""memory"":{""status"":""$_STAT_MEM"",""detail"":""""},""disk"":{""status"":""$_STAT_DISK"",""detail"":""""},""network"":{""status"":""$_STAT_NET"",""detail"":""""}},""issues_found"":$issues,""severity"":""$severity"",""trigger"":""user""}"
Add-Content -Path $StatsFile -Value $record -Encoding UTF8
