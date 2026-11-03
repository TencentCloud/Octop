#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor Patrol — 定期轻量化巡检
# ==============================================================================
# 功能: 执行 quick_scan.sh，解析输出，存储结构化 JSONL 到本地
# 存储: ~/.lightclaw/stats/cvm-doctor.jsonl (与 log_stats.sh 统一)
# 用法:
#   bash scripts/patrol.sh --up [秒数]     # 一键启动 守护+Dashboard
#   bash scripts/patrol.sh --down          # 一键停止全部
#   bash scripts/patrol.sh                 # 执行一次巡检
#   bash scripts/patrol.sh --daemon 300    # 守护模式，每 300 秒
#   bash scripts/patrol.sh --status        # 查看状态
#   bash scripts/patrol.sh --stop          # 停止守护进程
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATS_DIR="${HOME}/.lightclaw/stats"
PATROL_DIR="${HOME}/.lightclaw/patrol"
HISTORY_FILE="${STATS_DIR}/cvm-doctor.jsonl"
PID_FILE="${PATROL_DIR}/patrol.pid"
LOG_FILE="${PATROL_DIR}/patrol.log"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# 确保目录存在
mkdir -p "$STATS_DIR" "$PATROL_DIR"

# ── 辅助函数 ──────────────────────────────────────────

log_msg() {
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] $*" >> "$LOG_FILE"
}

# 保留最近 N 天的数据 (默认 7 天)，旧数据归档到 .old.gz 备份
# 策略: 按 ts 字段(ISO8601) 过滤，超过保留期的旧记录写入压缩备份后删除
rotate_history() {
    local retention_days="${PATROL_RETENTION_DAYS:-7}"
    [ ! -f "$HISTORY_FILE" ] && return 0

    # 计算截止时间戳 (UTC)
    local cutoff
    if [ "$(uname)" = "Darwin" ]; then
        cutoff=$(date -u -v-"${retention_days}"d +"%Y-%m-%dT%H:%M:%SZ")
    else
        cutoff=$(date -u -d "${retention_days} days ago" +"%Y-%m-%dT%H:%M:%SZ")
    fi

    # 只在有旧数据时才执行，避免不必要的 IO
    local old_count
    old_count=$(awk -v cut="$cutoff" '
        { if (match($0, /"ts":"[^"]*"/)) {
            ts = substr($0, RSTART+6, RLENGTH-7);
            if (ts < cut) count++
        } }
        END { print count+0 }
    ' "$HISTORY_FILE")

    if [ "$old_count" -eq 0 ]; then
        return 0
    fi

    local tmp_new="${HISTORY_FILE}.new.$$"
    local tmp_old="${HISTORY_FILE}.old.$$"

    awk -v cut="$cutoff" -v new="$tmp_new" -v old="$tmp_old" '
        {
            if (match($0, /"ts":"[^"]*"/)) {
                ts = substr($0, RSTART+6, RLENGTH-7);
                if (ts >= cut) print > new; else print > old;
            }
        }
    ' "$HISTORY_FILE"

    # 归档旧数据 (追加到 gz 备份)
    if [ -s "$tmp_old" ]; then
        gzip -c "$tmp_old" >> "${STATS_DIR}/cvm-doctor.old.jsonl.gz" 2>/dev/null || true
    fi

    # 替换主文件
    mv "$tmp_new" "$HISTORY_FILE" 2>/dev/null
    rm -f "$tmp_old"

    log_msg "清理完成: 归档 ${old_count} 条旧记录 (保留最近 ${retention_days} 天)"
}

# 解析 quick_scan.sh 的输出，提取各组件状态
parse_quick_scan() {
    local output="$1"
    local cpu_status="skipped" mem_status="skipped" disk_status="skipped" net_status="skipped"
    local cpu_detail="" mem_detail="" disk_detail="" net_detail=""

    # 提取 CPU
    local in_cpu=false in_mem=false in_disk=false in_net=false
    while IFS= read -r line; do
        case "$line" in
            "--- CPU CHECK ---")    in_cpu=true;  in_mem=false; in_disk=false; in_net=false ;;
            "--- MEMORY CHECK ---") in_cpu=false; in_mem=true;  in_disk=false; in_net=false ;;
            "--- DISK CHECK ---")   in_cpu=false; in_mem=false; in_disk=true;  in_net=false ;;
            "--- NETWORK CHECK ---") in_cpu=false; in_mem=false; in_disk=false; in_net=true ;;
            "=== QUICK CHECK COMPLETE ===") break ;;
        esac

        if [[ "$line" == Status:* ]]; then
            local status
            status=$(echo "$line" | sed 's/Status: //' | tr '[:upper:]' '[:lower:]')
            if $in_cpu; then cpu_status="$status"; fi
            if $in_mem; then mem_status="$status"; fi
            if $in_disk; then disk_status="$status"; fi
            if $in_net; then net_status="$status"; fi
        fi

        if [[ "$line" == Reason:* ]]; then
            local reason
            reason=$(echo "$line" | sed 's/Reason: //')
            if $in_cpu; then cpu_detail="$reason"; fi
            if $in_mem; then mem_detail="$reason"; fi
            if $in_disk; then disk_detail="$reason"; fi
            if $in_net; then net_detail="$reason"; fi
        fi

        # 提取数值指标
        if $in_cpu && [[ "$line" == "CPU Cores:"* ]]; then
            cpu_detail="cores=$(echo "$line" | awk '{print $NF}') $cpu_detail"
        fi
        if $in_cpu && [[ "$line" == "Run Queue:"* ]]; then
            cpu_detail="queue=$(echo "$line" | awk '{print $NF}') $cpu_detail"
        fi
        if $in_mem && [[ "$line" == "Swap Used:"* ]]; then
            mem_detail="swap=$(echo "$line" | awk '{print $NF}') $mem_detail"
        fi
        if $in_disk && [[ "$line" == "I/O Wait:"* ]]; then
            disk_detail="iowait=$(echo "$line" | awk '{print $NF}') $disk_detail"
        fi
        if $in_net && [[ "$line" == "Total Drops:"* ]]; then
            net_detail="drops=$(echo "$line" | awk '{print $NF}') $net_detail"
        fi
    done <<< "$output"

    # 计算总体严重级别和问题数
    local issues=0 severity="ok"
    for s in "$cpu_status" "$mem_status" "$disk_status" "$net_status"; do
        case "$s" in
            critical) issues=$((issues+1)); severity="critical" ;;
            warning)  issues=$((issues+1)); [ "$severity" != "critical" ] && severity="warning" ;;
        esac
    done

    # 获取主机信息
    local hostname_val
    hostname_val=$(hostname 2>/dev/null || echo "unknown")
    local os_type
    os_type=$(uname -s 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo "unknown")
    local uptime_val
    if [ "$os_type" = "darwin" ]; then
        uptime_val=$(uptime | awk '{print $3,$4}' | sed 's/,//')
    else
        uptime_val=$(uptime -p 2>/dev/null || uptime | awk '{print $3,$4}' | sed 's/,//')
    fi

    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u)
    local ts_local
    ts_local=$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date)

    # 清理 detail 字段（去除前后空格）
    cpu_detail=$(echo "$cpu_detail" | sed 's/^ *//;s/ *$//')
    mem_detail=$(echo "$mem_detail" | sed 's/^ *//;s/ *$//')
    disk_detail=$(echo "$disk_detail" | sed 's/^ *//;s/ *$//')
    net_detail=$(echo "$net_detail" | sed 's/^ *//;s/ *$//')

    # 输出 JSON 记录 (与 log_stats.sh 统一 schema，增加 detail)
    printf '{"ts":"%s","ts_local":"%s","mode":"quick","scenario":"health_check","hostname":"%s","os":"%s","uptime":"%s","duration_s":%d,"components":{"cpu":{"status":"%s","detail":"%s"},"memory":{"status":"%s","detail":"%s"},"disk":{"status":"%s","detail":"%s"},"network":{"status":"%s","detail":"%s"}},"issues_found":%d,"severity":"%s","trigger":"patrol"}\n' \
        "$ts" "$ts_local" "$hostname_val" "$os_type" "$uptime_val" \
        "$SECONDS" \
        "$cpu_status" "$cpu_detail" \
        "$mem_status" "$mem_detail" \
        "$disk_status" "$disk_detail" \
        "$net_status" "$net_detail" \
        "$issues" "$severity"
}

# 执行一次巡检
run_patrol() {
    SECONDS=0
    local quick_scan="${SCRIPT_DIR}/quick_scan.sh"

    if [ ! -f "$quick_scan" ]; then
        printf "${RED}[ERR]${NC} quick_scan.sh 不存在: %s\n" "$quick_scan" >&2
        return 1
    fi

    # 执行 quick_scan (设置 trigger=patrol 避免 log_stats.sh 重复写入)
    local output
    output=$(CVM_DOCTOR_TRIGGER=patrol bash "$quick_scan" 2>&1)
    local exit_code=$?

    if [ $exit_code -ne 0 ] && [ -z "$output" ]; then
        printf "${RED}[ERR]${NC} quick_scan.sh 执行失败 (exit=%d)\n" "$exit_code" >&2
        return 1
    fi

    # 解析并存储
    local record
    record=$(parse_quick_scan "$output")

    echo "$record" >> "$HISTORY_FILE"
    log_msg "巡检完成: $(echo "$record" | grep -o '"severity":"[^"]*"')"

    # 每次巡检后执行轮转清理 (只有存在旧数据时才实际操作)
    rotate_history

    # 同时清理日志文件 (保留最近 1000 行)
    if [ -f "$LOG_FILE" ] && [ "$(wc -l < "$LOG_FILE" | tr -d ' ')" -gt 2000 ]; then
        tail -1000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
    fi

    # 简要输出
    local severity
    severity=$(echo "$record" | grep -o '"severity":"[^"]*"' | cut -d'"' -f4)
    local issues
    issues=$(echo "$record" | grep -o '"issues_found":[0-9]*' | cut -d: -f2)

    case "$severity" in
        ok)       printf "${GREEN}✅ 巡检正常${NC} — 无异常 (%ds)\n" "$SECONDS" ;;
        warning)  printf "${YELLOW}⚠️  发现告警${NC} — %d 个组件异常 (%ds)\n" "$issues" "$SECONDS" ;;
        critical) printf "${RED}❌ 发现严重问题${NC} — %d 个组件异常 (%ds)\n" "$issues" "$SECONDS" ;;
    esac
}

# ── 守护模式 ──────────────────────────────────────────

start_daemon() {
    local interval=$1

    # 检查是否已有守护进程
    if [ -f "$PID_FILE" ]; then
        local old_pid
        old_pid=$(cat "$PID_FILE")
        if kill -0 "$old_pid" 2>/dev/null; then
            printf "${YELLOW}[WARN]${NC} 守护进程已在运行 (PID=%s)\n" "$old_pid"
            printf "       停止命令: bash %s/patrol.sh --stop\n" "$SCRIPT_DIR"
            return 1
        fi
    fi

    printf "${CYAN}🚀 启动巡检守护进程${NC}\n"
    printf "   间隔:    %d 秒\n" "$interval"
    printf "   数据:    %s\n" "$HISTORY_FILE"
    printf "   日志:    %s\n" "$LOG_FILE"
    printf "   PID文件: %s\n" "$PID_FILE"
    echo ""

    # 后台启动
    (
        echo $$ > "$PID_FILE"
        log_msg "守护进程启动 (PID=$$, interval=${interval}s)"

        trap 'log_msg "守护进程收到停止信号"; rm -f "$PID_FILE"; exit 0' SIGTERM SIGINT

        while true; do
            run_patrol >> "$LOG_FILE" 2>&1
            sleep "$interval"
        done
    ) &

    local daemon_pid=$!
    echo "$daemon_pid" > "$PID_FILE"

    printf "${GREEN}✅ 守护进程已启动${NC} (PID=%d)\n" "$daemon_pid"
    printf "   停止命令: bash scripts/patrol.sh --stop\n"
    printf "   状态查看: bash scripts/patrol.sh --status\n"
}

stop_daemon() {
    if [ ! -f "$PID_FILE" ]; then
        printf "${YELLOW}[WARN]${NC} 没有运行中的守护进程\n"
        return 0
    fi

    local pid
    pid=$(cat "$PID_FILE")

    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid"
        rm -f "$PID_FILE"
        log_msg "守护进程已停止 (PID=$pid)"
        printf "${GREEN}✅ 守护进程已停止${NC} (PID=%d)\n" "$pid"
    else
        rm -f "$PID_FILE"
        printf "${YELLOW}[WARN]${NC} 守护进程 PID=%d 已不存在，已清理 PID 文件\n" "$pid"
    fi
}

show_status() {
    printf "${BOLD}${CYAN}CVM Doctor Patrol 状态${NC}\n"
    printf "────────────────────────────────────\n"

    # 守护进程状态
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            printf "  守护进程: ${GREEN}运行中${NC} (PID=%d)\n" "$pid"
        else
            printf "  守护进程: ${RED}已停止${NC} (陈旧的 PID 文件)\n"
        fi
    else
        printf "  守护进程: ${DIM}未运行${NC}\n"
    fi

    # 数据文件状态
    if [ -f "$HISTORY_FILE" ]; then
        local total_records
        total_records=$(wc -l < "$HISTORY_FILE" | tr -d ' ')
        local file_size
        file_size=$(du -h "$HISTORY_FILE" | awk '{print $1}')
        local last_ts
        last_ts=$(tail -1 "$HISTORY_FILE" | grep -o '"ts_local":"[^"]*"' | cut -d'"' -f4)
        local last_severity
        last_severity=$(tail -1 "$HISTORY_FILE" | grep -o '"severity":"[^"]*"' | cut -d'"' -f4)

        printf "  数据文件: %s\n" "$HISTORY_FILE"
        printf "  总记录数: ${BOLD}%s${NC}\n" "$total_records"
        printf "  文件大小: %s\n" "$file_size"
        printf "  最后巡检: %s\n" "$last_ts"
        printf "  最后状态: "
        case "$last_severity" in
            ok)       printf "${GREEN}正常${NC}\n" ;;
            warning)  printf "${YELLOW}告警${NC}\n" ;;
            critical) printf "${RED}严重${NC}\n" ;;
            *)        printf "${DIM}未知${NC}\n" ;;
        esac
    else
        printf "  数据文件: ${DIM}暂无数据${NC}\n"
    fi

    echo ""
    printf "  Dashboard: file://%s/docs/patrol-dashboard.html\n" "$(cd "$SCRIPT_DIR/.." && pwd)"
}

# ── 一键启停 ──────────────────────────────────────────

SERVER_PID_FILE="${PATROL_DIR}/server.pid"
SERVER_PORT="${PATROL_PORT:-8765}"

start_all() {
    local interval="${1:-300}"

    # 1. 启动巡检守护进程
    start_daemon "$interval"
    echo ""

    # 2. 启动 Dashboard Server
    local server_script="${SCRIPT_DIR}/patrol_server.py"
    if [ ! -f "$server_script" ]; then
        printf "${YELLOW}[WARN]${NC} 未找到 patrol_server.py，跳过 Dashboard 启动\n"
        return 0
    fi

    # 检查端口占用
    if lsof -ti ":$SERVER_PORT" >/dev/null 2>&1; then
        local existing_pid
        existing_pid=$(lsof -ti ":$SERVER_PORT" | head -1)
        printf "${YELLOW}[WARN]${NC} 端口 %s 已被 PID=%s 占用，跳过 Server 启动\n" "$SERVER_PORT" "$existing_pid"
        echo "$existing_pid" > "$SERVER_PID_FILE"
    else
        nohup python3 "$server_script" --port "$SERVER_PORT" > "${PATROL_DIR}/server.log" 2>&1 &
        local server_pid=$!
        echo "$server_pid" > "$SERVER_PID_FILE"
        sleep 1
        printf "${GREEN}✅ Dashboard Server 已启动${NC} (PID=%d)\n" "$server_pid"
    fi

    echo ""
    printf "${BOLD}${CYAN}🌐 Dashboard: http://localhost:%s/docs/patrol-dashboard.html${NC}\n" "$SERVER_PORT"
    echo ""
    printf "  停止全部: bash scripts/patrol.sh --down\n"
}

stop_all() {
    # 1. 停止守护进程
    stop_daemon

    # 2. 停止 Server
    if [ -f "$SERVER_PID_FILE" ]; then
        local sp
        sp=$(cat "$SERVER_PID_FILE")
        if kill -0 "$sp" 2>/dev/null; then
            kill "$sp" 2>/dev/null
            printf "${GREEN}✅ Dashboard Server 已停止${NC} (PID=%d)\n" "$sp"
        fi
        rm -f "$SERVER_PID_FILE"
    fi
}

# ── 主逻辑 ────────────────────────────────────────────

case "${1:-}" in
    --daemon)
        interval="${2:-300}"
        start_daemon "$interval"
        ;;
    --up)
        # 一键启动: 守护进程 + Dashboard Server
        interval="${2:-300}"
        start_all "$interval"
        ;;
    --down)
        stop_all
        ;;
    --stop)
        stop_daemon
        ;;
    --status)
        show_status
        ;;
    --rotate)
        rotate_history
        echo "清理完成"
        ;;
    --help|-h)
        echo "CVM Doctor Patrol — 定期轻量化巡检"
        echo ""
        echo "一键启停 (推荐):"
        echo "  bash scripts/patrol.sh --up [秒数]     # 启动守护进程 + Dashboard"
        echo "  bash scripts/patrol.sh --down          # 停止全部"
        echo ""
        echo "分项命令:"
        echo "  bash scripts/patrol.sh                 # 执行一次巡检"
        echo "  bash scripts/patrol.sh --daemon 300    # 仅启动守护模式"
        echo "  bash scripts/patrol.sh --stop          # 停止守护进程"
        echo "  bash scripts/patrol.sh --status        # 查看状态"
        echo "  bash scripts/patrol.sh --rotate        # 手动清理 (保留 7 天)"
        echo ""
        echo "数据存储: ~/.lightclaw/stats/cvm-doctor.jsonl (与 stats 统一)"
        echo "保留策略: 最近 7 天 (PATROL_RETENTION_DAYS 环境变量可调)"
        echo "Dashboard: http://localhost:8765/docs/patrol-dashboard.html"
        ;;
    *)
        run_patrol
        ;;
esac
