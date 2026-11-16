#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor Quick Scan
# ==============================================================================
# Purpose: Fast triage to identify which components need deep analysis
# Duration: ~3 seconds
# Checks: CPU queue, Memory swap, Disk I/O wait, Network drops
# Output: Structured text (parseable by AI)
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OS=$(uname -s 2>/dev/null || echo "Unknown")
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u)
SECONDS=0

# 统计采集: 记录各组件状态
_STAT_CPU="skipped"
_STAT_MEM="skipped"
_STAT_DISK="skipped"
_STAT_NET="skipped"

echo "=== CVM QUICK HEALTH CHECK ==="
echo "Platform: $OS"
echo "Timestamp: $TIMESTAMP"
echo ""

# ==============================================================================
# Check 1: CPU Queue Saturation
# ==============================================================================
echo "--- CPU CHECK ---"
case "$OS" in
  Linux)
    CPU_CORES=$(nproc 2>/dev/null || echo "1")
    RUN_QUEUE=$(vmstat 1 2 2>/dev/null | tail -1 | awk '{print $1}' || echo "0")
    echo "CPU Cores: $CPU_CORES"
    echo "Run Queue: $RUN_QUEUE"

    # PSI (内核 4.20+): 最科学的 CPU 压力指标
    PSI_CPU=""
    if [ -f /proc/pressure/cpu ]; then
      PSI_CPU=$(awk '/^some/ {for(i=1;i<=NF;i++) if($i~/avg10/) {split($i,a,"="); print a[2]}}' /proc/pressure/cpu 2>/dev/null)
      echo "PSI cpu.some avg10: ${PSI_CPU:-N/A}%"
    fi

    # 判定: 传统指标 + PSI 交叉，取更严重的
    _rq_level="ok"
    [ "$RUN_QUEUE" -gt "$((CPU_CORES * 2))" ] && _rq_level="critical"
    [ "$RUN_QUEUE" -gt "$CPU_CORES" ] && [ "$_rq_level" = "ok" ] && _rq_level="warning"

    _psi_level="ok"
    if [ -n "$PSI_CPU" ]; then
      _psi_level=$(awk -v p="$PSI_CPU" 'BEGIN {
        if (p >= 50) print "critical";
        else if (p >= 15) print "warning";
        else print "ok";
      }')
    fi

    _STAT_CPU="ok"
    for _lv in "$_rq_level" "$_psi_level"; do
      case "$_lv" in
        critical) _STAT_CPU="critical" ;;
        warning) [ "$_STAT_CPU" != "critical" ] && _STAT_CPU="warning" ;;
      esac
    done

    case "$_STAT_CPU" in
      critical) echo "Status: CRITICAL"; echo "Reason: Run queue=$RUN_QUEUE PSI=${PSI_CPU:-N/A}%" ;;
      warning)  echo "Status: WARNING";  echo "Reason: Run queue=$RUN_QUEUE PSI=${PSI_CPU:-N/A}%" ;;
      *)        echo "Status: OK" ;;
    esac
    ;;
  Darwin)
    CPU_CORES=$(sysctl -n hw.ncpu 2>/dev/null || echo "1")
    # macOS load average 包含等 I/O 的线程，用浮点比较更精确
    LOAD_1M=$(sysctl -n vm.loadavg 2>/dev/null | awk '{print $2}' || echo "0")
    echo "CPU Cores: $CPU_CORES"
    echo "Load Avg (1m): $LOAD_1M"
    
    STATUS=$(awk -v load="$LOAD_1M" -v cores="$CPU_CORES" 'BEGIN {
      if (load > cores * 2) print "CRITICAL";
      else if (load > cores * 1.5) print "WARNING";
      else print "OK";
    }')
    echo "Status: $STATUS"
    _STAT_CPU=$(echo "$STATUS" | tr '[:upper:]' '[:lower:]')

    if [ "$STATUS" = "CRITICAL" ]; then
      echo "Reason: Load ($LOAD_1M) > 2x cores ($CPU_CORES)"
    elif [ "$STATUS" = "WARNING" ]; then
      echo "Reason: Load ($LOAD_1M) > 1.5x cores ($CPU_CORES)"
    fi
    ;;
  *)
    echo "Status: SKIP"
    echo "Reason: OS '$OS' not supported"
    ;;
esac
echo ""

# ==============================================================================
# Check 2: Memory Swap Saturation
# ==============================================================================
echo "--- MEMORY CHECK ---"
case "$OS" in
  Linux)
    # 三信号: swap + available% + PSI memory，取最严重的
    SWAP_USED=$(free -m 2>/dev/null | awk '/Swap:/ {print $3}' || echo "0")
    SWAP_TOTAL=$(free -m 2>/dev/null | awk '/Swap:/ {print $2}' || echo "0")
    MEM_TOTAL=$(free -m 2>/dev/null | awk '/Mem:/ {print $2}' || echo "1")
    MEM_AVAIL=$(free -m 2>/dev/null | awk '/Mem:/ {print $7}' || echo "0")
    [ -z "$MEM_AVAIL" ] || [ "$MEM_AVAIL" = "0" ] && MEM_AVAIL=$(free -m 2>/dev/null | awk '/Mem:/ {print $4}' || echo "0")
    AVAIL_PCT=$(awk -v a="$MEM_AVAIL" -v t="$MEM_TOTAL" 'BEGIN { if(t>0) printf "%.0f", a/t*100; else print 100 }')

    echo "Memory Total: ${MEM_TOTAL}MB  Available: ${MEM_AVAIL}MB (${AVAIL_PCT}%)"
    if [ "$SWAP_TOTAL" -gt 0 ]; then
      echo "Swap: ${SWAP_USED}MB / ${SWAP_TOTAL}MB"
    else
      echo "Swap: not configured"
    fi

    # PSI memory (内核 4.20+)
    PSI_MEM=""
    if [ -f /proc/pressure/memory ]; then
      PSI_MEM=$(awk '/^some/ {for(i=1;i<=NF;i++) if($i~/avg10/) {split($i,a,"="); print a[2]}}' /proc/pressure/memory 2>/dev/null)
      echo "PSI memory.some avg10: ${PSI_MEM:-N/A}%"
    fi

    # cgroup 内存限制检测 (容器环境)
    _cgroup_pct=""
    if [ -f /sys/fs/cgroup/memory.max ] && [ -f /sys/fs/cgroup/memory.current ]; then
      _cg_max=$(cat /sys/fs/cgroup/memory.max 2>/dev/null)
      _cg_cur=$(cat /sys/fs/cgroup/memory.current 2>/dev/null)
      if [ "$_cg_max" != "max" ] && [ -n "$_cg_max" ] && [ "$_cg_max" -gt 0 ] 2>/dev/null; then
        _cgroup_pct=$(awk -v c="$_cg_cur" -v m="$_cg_max" 'BEGIN { printf "%.0f", c/m*100 }')
        echo "Cgroup memory: ${_cgroup_pct}% of limit"
      fi
    fi

    # 判定: swap + avail + PSI + cgroup，取最严重的
    _swap_level="ok"
    if [ "$SWAP_TOTAL" -gt 0 ]; then
      [ "$SWAP_USED" -ge 1000 ] && _swap_level="critical"
      [ "$SWAP_USED" -ge 100 ] && [ "$_swap_level" = "ok" ] && _swap_level="warning"
    fi

    _avail_level="ok"
    [ "$AVAIL_PCT" -le 5 ] && _avail_level="critical"
    [ "$AVAIL_PCT" -le 15 ] && [ "$_avail_level" = "ok" ] && _avail_level="warning"

    _psi_level="ok"
    if [ -n "$PSI_MEM" ]; then
      _psi_level=$(awk -v p="$PSI_MEM" 'BEGIN {
        if (p >= 40) print "critical";
        else if (p >= 10) print "warning";
        else print "ok";
      }')
    fi

    _cg_level="ok"
    if [ -n "$_cgroup_pct" ]; then
      [ "$_cgroup_pct" -ge 95 ] && _cg_level="critical"
      [ "$_cgroup_pct" -ge 85 ] && [ "$_cg_level" = "ok" ] && _cg_level="warning"
    fi

    _STAT_MEM="ok"
    for _lv in "$_swap_level" "$_avail_level" "$_psi_level" "$_cg_level"; do
      case "$_lv" in
        critical) _STAT_MEM="critical" ;;
        warning) [ "$_STAT_MEM" != "critical" ] && _STAT_MEM="warning" ;;
      esac
    done

    case "$_STAT_MEM" in
      critical) echo "Status: CRITICAL"; echo "Reason: Avail=${AVAIL_PCT}% Swap=${SWAP_USED}MB PSI=${PSI_MEM:-N/A}% Cgroup=${_cgroup_pct:-N/A}%" ;;
      warning)  echo "Status: WARNING";  echo "Reason: Avail=${AVAIL_PCT}% Swap=${SWAP_USED}MB PSI=${PSI_MEM:-N/A}% Cgroup=${_cgroup_pct:-N/A}%" ;;
      *)        echo "Status: OK" ;;
    esac
    ;;
  Darwin)
    # macOS 使用内存压力等级 (kern.memorystatus_level) 作为主判据
    # 范围 0~100，值越高越健康。macOS swap 大不代表内存紧张（压缩内存机制）
    MEM_LEVEL=$(sysctl -n kern.memorystatus_level 2>/dev/null || echo "50")

    # swap 仅作参考
    SWAP_USED_RAW=$(sysctl vm.swapusage 2>/dev/null | grep -oE 'used = [0-9.]+[MG]?' | grep -oE '[0-9.]+[MG]?' || echo "0M")
    if [[ "$SWAP_USED_RAW" =~ ([0-9.]+)G ]]; then
      SWAP_USED=$(echo "${BASH_REMATCH[1]} * 1024" | bc 2>/dev/null | awk '{print int($1)}' || echo "0")
    else
      SWAP_USED=$(echo "$SWAP_USED_RAW" | sed 's/M//' | awk '{print int($1)}' || echo "0")
    fi

    echo "Memory Pressure Level: $MEM_LEVEL (0=worst, 100=best)"
    echo "Swap Used: ${SWAP_USED}MB (macOS compressed memory, not necessarily pressure)"

    if [ "$MEM_LEVEL" -le 10 ]; then
      echo "Status: CRITICAL"
      echo "Reason: Memory pressure level $MEM_LEVEL <= 10 (severe)"
      _STAT_MEM="critical"
    elif [ "$MEM_LEVEL" -le 30 ]; then
      echo "Status: WARNING"
      echo "Reason: Memory pressure level $MEM_LEVEL <= 30 (elevated)"
      _STAT_MEM="warning"
    else
      echo "Status: OK"
      _STAT_MEM="ok"
    fi
    ;;
  *)
    echo "Status: SKIP"
    echo "Reason: OS '$OS' not supported"
    ;;
esac
echo ""

# ==============================================================================
# Check 3: Disk I/O Wait
# ==============================================================================
echo "--- DISK CHECK ---"
case "$OS" in
  Linux)
    if command -v iostat &> /dev/null; then
      IO_WAIT=$(iostat -x 1 2 2>/dev/null | tail -n +4 | awk 'NF && !/^$/ {sum+=$4; count++} END {if(count>0) printf "%.1f", sum/count; else print "0"}')
      echo "I/O Wait: ${IO_WAIT}%"
    else
      IO_WAIT=$(vmstat 1 2 2>/dev/null | tail -1 | awk '{print $16}' || echo "0")
      echo "I/O Wait: ${IO_WAIT}% (vmstat wa)"
    fi

    # PSI io (内核 4.20+)
    PSI_IO=""
    if [ -f /proc/pressure/io ]; then
      PSI_IO=$(awk '/^some/ {for(i=1;i<=NF;i++) if($i~/avg10/) {split($i,a,"="); print a[2]}}' /proc/pressure/io 2>/dev/null)
      echo "PSI io.some avg10: ${PSI_IO:-N/A}%"
    fi

    # 判定: iowait + PSI，取更严重的
    _io_level=$(awk -v iowait="$IO_WAIT" 'BEGIN {
      if (iowait >= 30) print "critical";
      else if (iowait >= 10) print "warning";
      else print "ok";
    }')

    _psi_level="ok"
    if [ -n "$PSI_IO" ]; then
      _psi_level=$(awk -v p="$PSI_IO" 'BEGIN {
        if (p >= 40) print "critical";
        else if (p >= 10) print "warning";
        else print "ok";
      }')
    fi

    _STAT_DISK="ok"
    for _lv in "$_io_level" "$_psi_level"; do
      case "$_lv" in
        critical) _STAT_DISK="critical" ;;
        warning) [ "$_STAT_DISK" != "critical" ] && _STAT_DISK="warning" ;;
      esac
    done

    case "$_STAT_DISK" in
      critical) echo "Status: CRITICAL"; echo "Reason: iowait=${IO_WAIT}% PSI=${PSI_IO:-N/A}%" ;;
      warning)  echo "Status: WARNING";  echo "Reason: iowait=${IO_WAIT}% PSI=${PSI_IO:-N/A}%" ;;
      *)        echo "Status: OK" ;;
    esac
    ;;
  Darwin)
    # macOS iostat 列: KB/t tps MB/s us sy id (没有 iowait 列)
    # 用 idle% 反推: 如果 idle 低但 user 也不高，说明 I/O 密集
    # 取第二次采样 (排除首次累计值)
    IOSTAT_LINE=$(iostat -c 2 -w 1 disk0 2>/dev/null | tail -1)
    CPU_USER=$(echo "$IOSTAT_LINE" | awk '{print $4+0}')
    CPU_SYS=$(echo "$IOSTAT_LINE" | awk '{print $5+0}')
    CPU_IDLE=$(echo "$IOSTAT_LINE" | awk '{print $6+0}')
    # I/O bound 估算: 100 - user - sys - idle ≈ iowait (macOS 没有独立 wa 列)
    # 更实用的方式: 看 idle 是否异常低
    IO_BUSY=$(awk -v idle="$CPU_IDLE" 'BEGIN { printf "%.1f", 100 - idle }')
    echo "CPU User: ${CPU_USER}%  Sys: ${CPU_SYS}%  Idle: ${CPU_IDLE}%"
    echo "Disk I/O Busy (100-idle): ${IO_BUSY}%"
    
    STATUS=$(awk -v idle="$CPU_IDLE" 'BEGIN {
      if (idle <= 10) print "CRITICAL";
      else if (idle <= 30) print "WARNING";
      else print "OK";
    }')
    echo "Status: $STATUS"
    _STAT_DISK=$(echo "$STATUS" | tr '[:upper:]' '[:lower:]')
    
    if [ "$STATUS" = "CRITICAL" ]; then
      echo "Reason: CPU idle <= 10% (system heavily loaded, likely I/O bound)"
    elif [ "$STATUS" = "WARNING" ]; then
      echo "Reason: CPU idle <= 30% (elevated system load)"
    fi
    ;;
  *)
    echo "Status: SKIP"
    echo "Reason: OS '$OS' not supported"
    ;;
esac
echo ""

# ==============================================================================
# Check 4: Network Packet Drops (2-second delta — avoids false positives from
# cumulative counters on long-running servers)
# ==============================================================================
echo "--- NETWORK CHECK ---"
case "$OS" in
  Linux)
    if command -v ip &> /dev/null; then
      RX1=$(ip -s link 2>/dev/null | grep -A1 "RX:" | awk 'NR%3==2 {sum+=$4} END {print sum+0}')
      TX1=$(ip -s link 2>/dev/null | grep -A1 "TX:" | awk 'NR%3==2 {sum+=$4} END {print sum+0}')
      sleep 2
      RX2=$(ip -s link 2>/dev/null | grep -A1 "RX:" | awk 'NR%3==2 {sum+=$4} END {print sum+0}')
      TX2=$(ip -s link 2>/dev/null | grep -A1 "TX:" | awk 'NR%3==2 {sum+=$4} END {print sum+0}')
      RX_DROPS=$(( (RX2 - RX1) / 2 ))
      TX_DROPS=$(( (TX2 - TX1) / 2 ))
    else
      RX_DROPS=0
      TX_DROPS=0
    fi
    TOTAL_DROPS=$((RX_DROPS + TX_DROPS))
    echo "RX Drops: ${RX_DROPS}/s"
    echo "TX Drops: ${TX_DROPS}/s"
    echo "Total Drops: ${TOTAL_DROPS}/s"

    if [ "$TOTAL_DROPS" -ge 50 ]; then
      echo "Status: CRITICAL"
      echo "Reason: Drop rate >= 50/s (active packet loss)"
      _STAT_NET="critical"
    elif [ "$TOTAL_DROPS" -ge 5 ]; then
      echo "Status: WARNING"
      echo "Reason: Drop rate >= 5/s"
      _STAT_NET="warning"
    else
      echo "Status: OK"
      _STAT_NET="ok"
    fi
    ;;
  Darwin)
    # Link# rows come in two forms:
    #   NF=10  (no MAC): Name Mtu Network <Link#N> Ipkts Ierrs Ibytes Opkts Oerrs Obytes Coll
    #   NF=11 (with MAC): Name Mtu Network <Link#N> MAC   Ipkts Ierrs Ibytes Opkts Oerrs Obytes Coll
    # Skip non-Link# rows (IP address duplicates) to avoid double-counting.
    RX1=$(netstat -i -b 2>/dev/null | awk '/Link#/ { if(NF==10) rx+=$5; else if(NF==11) rx+=$6 } END {print rx+0}')
    TX1=$(netstat -i -b 2>/dev/null | awk '/Link#/ { if(NF==10) tx+=$8; else if(NF==11) tx+=$9 } END {print tx+0}')
    sleep 2
    RX2=$(netstat -i -b 2>/dev/null | awk '/Link#/ { if(NF==10) rx+=$5; else if(NF==11) rx+=$6 } END {print rx+0}')
    TX2=$(netstat -i -b 2>/dev/null | awk '/Link#/ { if(NF==10) tx+=$8; else if(NF==11) tx+=$9 } END {print tx+0}')
    RX_DROPS=$(( (RX2 - RX1) / 2 ))
    TX_DROPS=$(( (TX2 - TX1) / 2 ))
    TOTAL_DROPS=$((RX_DROPS + TX_DROPS))
    echo "RX Drops: ${RX_DROPS}/s"
    echo "TX Drops: ${TX_DROPS}/s"
    echo "Total Drops: ${TOTAL_DROPS}/s"

    if [ "$TOTAL_DROPS" -ge 50 ]; then
      echo "Status: CRITICAL"
      echo "Reason: Drop rate >= 50/s (active packet loss)"
      _STAT_NET="critical"
    elif [ "$TOTAL_DROPS" -ge 5 ]; then
      echo "Status: WARNING"
      echo "Reason: Drop rate >= 5/s"
      _STAT_NET="warning"
    else
      echo "Status: OK"
      _STAT_NET="ok"
    fi
    ;;
  *)
    echo "Status: SKIP"
    echo "Reason: OS '$OS' not supported"
    ;;
esac

echo ""
echo "=== QUICK CHECK COMPLETE ==="

# 自动记录诊断统计 (patrol 模式下由 patrol.sh 写入带 detail 的记录，此处跳过)
if [ -f "$SCRIPT_DIR/log_stats.sh" ] && [ "${CVM_DOCTOR_TRIGGER:-user}" != "patrol" ]; then
  bash "$SCRIPT_DIR/log_stats.sh" quick health_check "$(echo "$OS" | tr '[:upper:]' '[:lower:]')" "$SECONDS" "$_STAT_CPU" "$_STAT_MEM" "$_STAT_DISK" "$_STAT_NET" "${CVM_DOCTOR_TRIGGER:-user}" 2>/dev/null
fi

# 自动拉起 patrol 守护 (如果未运行，且不是 patrol 自身调用)
_PATROL_PID="${HOME}/.lightclaw/patrol/patrol.pid"
_PATROL_DIR="${HOME}/.lightclaw/patrol"
_SERVER_PORT=8765
if [ -f "$SCRIPT_DIR/patrol.sh" ] && [ "${CVM_DOCTOR_TRIGGER:-user}" != "patrol" ]; then
  _running=false
  [ -f "$_PATROL_PID" ] && kill -0 "$(cat "$_PATROL_PID" 2>/dev/null)" 2>/dev/null && _running=true

  if ! $_running; then
    mkdir -p "$_PATROL_DIR"
    # 直接启动守护循环 (不调 --up 避免递归)
    (
      trap 'rm -f "$_PATROL_PID"; exit 0' SIGTERM SIGINT
      while true; do
        CVM_DOCTOR_TRIGGER=patrol bash "$SCRIPT_DIR/patrol.sh" 2>/dev/null
        sleep 300
      done
    ) &>/dev/null &
    _daemon_pid=$!
    echo "$_daemon_pid" > "$_PATROL_PID"

    # 启动 Dashboard Server (如果端口空闲)
    if [ -f "$SCRIPT_DIR/patrol_server.py" ] && ! lsof -ti ":$_SERVER_PORT" >/dev/null 2>&1; then
      nohup python3 "$SCRIPT_DIR/patrol_server.py" --port "$_SERVER_PORT" > "$_PATROL_DIR/server.log" 2>&1 &
      echo $! > "$_PATROL_DIR/server.pid"
    fi

    echo ""
    echo "📡 巡检守护已自动启动 — 看板: http://localhost:$_SERVER_PORT/docs/patrol-dashboard.html"
  fi
fi
