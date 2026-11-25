#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor Stats Analyzer
# ==============================================================================
# 分析 cvm-doctor-stats.jsonl 诊断统计日志
#
# 用法:
#   ./scripts/analyze_stats.sh                  # 分析全量数据
#   ./scripts/analyze_stats.sh --today          # 仅今天
#   ./scripts/analyze_stats.sh --last 7d        # 最近 7 天
#   ./scripts/analyze_stats.sh --last 30d       # 最近 30 天
#   ./scripts/analyze_stats.sh --file /path/x   # 指定文件
#   ./scripts/analyze_stats.sh --json           # 输出原始 JSON（供程序消费）
# ==============================================================================

set -euo pipefail

# ── 配置 ──────────────────────────────────────────────
STATS_FILE="${HOME}/.lightclaw/stats/cvm-doctor.jsonl"

# ── 颜色 ─────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ── 依赖检查 ──────────────────────────────────────────
if ! command -v jq &>/dev/null; then
    printf "${RED}[ERR]${NC} 需要 jq，请先安装: brew install jq / apt install jq\n" >&2
    exit 1
fi

# ── 参数解析 ──────────────────────────────────────────
TIME_FILTER=""
JSON_OUTPUT=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --today)
            TIME_FILTER=$(date -u +"%Y-%m-%d")
            shift ;;
        --last)
            shift
            DAYS="${1%d}"  # 去掉 d 后缀
            if [[ "$(uname)" == "Darwin" ]]; then
                TIME_FILTER=$(date -u -v-${DAYS}d +"%Y-%m-%dT%H:%M:%SZ")
            else
                TIME_FILTER=$(date -u -d "${DAYS} days ago" +"%Y-%m-%dT%H:%M:%SZ")
            fi
            shift ;;
        --file)
            shift; STATS_FILE="$1"; shift ;;
        --json)
            JSON_OUTPUT=true; shift ;;
        *)
            printf "${RED}[ERR]${NC} 未知参数: $1\n" >&2; exit 1 ;;
    esac
done

# ── 检查文件 ──────────────────────────────────────────
if [ ! -f "$STATS_FILE" ]; then
    printf "${RED}[ERR]${NC} 统计文件不存在: $STATS_FILE\n" >&2
    printf "${DIM}提示: 运行一次诊断后会自动生成${NC}\n" >&2
    exit 1
fi

TOTAL_LINES=$(wc -l < "$STATS_FILE" | tr -d ' ')
if [ "$TOTAL_LINES" -eq 0 ]; then
    printf "${RED}[ERR]${NC} 统计文件为空\n" >&2
    exit 1
fi

# ── 构建 jq 过滤器 ───────────────────────────────────
if [ -n "$TIME_FILTER" ]; then
    # 如果是日期前缀（--today），用 startswith；如果是时间戳（--last），用 >=
    if [[ "$TIME_FILTER" == *T* ]]; then
        JQ_FILTER="select(.ts >= \"$TIME_FILTER\")"
    else
        JQ_FILTER="select(.ts | startswith(\"$TIME_FILTER\"))"
    fi
else
    JQ_FILTER="."
fi

# 将过滤后的数据收集到数组
FILTERED=$(jq -s "[.[] | $JQ_FILTER]" "$STATS_FILE")
COUNT=$(echo "$FILTERED" | jq 'length')

if [ "$COUNT" -eq 0 ]; then
    printf "${YELLOW}[WARN]${NC} 指定时间范围内没有数据\n"
    exit 0
fi

# ── JSON 输出模式 ─────────────────────────────────────
if $JSON_OUTPUT; then
    echo "$FILTERED" | jq '{
        total: length,
        by_mode: (group_by(.mode) | map({key: .[0].mode, value: length}) | from_entries),
        by_severity: (group_by(.severity) | map({key: .[0].severity, value: length}) | from_entries),
        by_trigger: (group_by(.trigger) | map({key: .[0].trigger, value: length}) | from_entries),
        by_os: (group_by(.os) | map({key: .[0].os, value: length}) | from_entries),
        issues_found: [.[] | select(.issues_found > 0)] | length,
        issue_rate_pct: (([.[] | select(.issues_found > 0)] | length) * 100 / length),
        avg_duration_s: ([.[] | .duration_s] | add / length | . * 10 | round / 10),
        component_issues: (
            [.[] | .components | to_entries[] |
             .value as $v | (if ($v | type) == "object" then $v.status else $v end) as $st |
             select($st != "ok" and $st != "skipped")]
            | group_by(.key) | map({key: .[0].key, value: length}) | from_entries
        ),
        top_scenarios: (
            group_by(.scenario) | map({scenario: .[0].scenario, count: length})
            | sort_by(-.count) | .[0:5]
        ),
        time_range: {
            earliest: (sort_by(.ts) | first.ts),
            latest: (sort_by(.ts) | last.ts)
        }
    }'
    exit 0
fi

# ── 可视化输出 ────────────────────────────────────────

# 辅助: 百分比条
bar() {
    local pct=$1 width=20
    local filled=$(( pct * width / 100 ))
    local empty=$(( width - filled ))
    printf "["
    printf "%0.s█" $(seq 1 $filled 2>/dev/null) || true
    printf "%0.s░" $(seq 1 $empty 2>/dev/null) || true
    printf "] %d%%" "$pct"
}

# 辅助: severity 颜色
sev_color() {
    case "$1" in
        critical) printf "$RED" ;;
        warning)  printf "$YELLOW" ;;
        ok)       printf "$GREEN" ;;
        *)        printf "$NC" ;;
    esac
}

echo ""
printf "${BOLD}${CYAN}═══════════════════════════════════════════════════════${NC}\n"
printf "${BOLD}${CYAN}  CVM Doctor 诊断统计报告${NC}\n"
printf "${BOLD}${CYAN}═══════════════════════════════════════════════════════${NC}\n"

# ── 1. 总览 ──────────────────────────────────────────
EARLIEST=$(echo "$FILTERED" | jq -r 'sort_by(.ts) | first.ts')
LATEST=$(echo "$FILTERED" | jq -r 'sort_by(.ts) | last.ts')
ISSUES=$(echo "$FILTERED" | jq '[.[] | select(.issues_found > 0)] | length')
AVG_DUR=$(echo "$FILTERED" | jq '[.[] | .duration_s] | add / length | . * 10 | round / 10')

echo ""
printf "${BOLD}  📊 总览${NC}\n"
printf "  ─────────────────────────────────\n"
printf "  总诊断次数:    ${BOLD}%s${NC}\n" "$COUNT"
printf "  发现问题次数:  ${BOLD}%s${NC}" "$ISSUES"
if [ "$COUNT" -gt 0 ]; then
    RATE=$(echo "$FILTERED" | jq '([.[] | select(.issues_found > 0)] | length) * 100 / length | round')
    printf "  (问题率 %s%%)" "$RATE"
fi
echo ""
printf "  平均耗时:      ${BOLD}%s s${NC}\n" "$AVG_DUR"
printf "  时间范围:      %s\n" "$EARLIEST"
printf "                 ~ %s\n" "$LATEST"

# ── 2. 按模式分布 ────────────────────────────────────
echo ""
printf "${BOLD}  🔍 诊断模式${NC}\n"
printf "  ─────────────────────────────────\n"
echo "$FILTERED" | jq -r '
    group_by(.mode) | map({mode: .[0].mode, count: length})
    | sort_by(-.count)[] | "\(.mode) \(.count)"
' | while read mode cnt; do
    pct=$(( cnt * 100 / COUNT ))
    printf "  %-14s %4d  %s\n" "$mode" "$cnt" "$(bar $pct)"
done

# ── 3. 严重级别分布 ──────────────────────────────────
echo ""
printf "${BOLD}  🚦 严重级别${NC}\n"
printf "  ─────────────────────────────────\n"
for sev in ok warning critical; do
    cnt=$(echo "$FILTERED" | jq "[.[] | select(.severity == \"$sev\")] | length")
    pct=$(( cnt * 100 / COUNT ))
    color=$(sev_color "$sev")
    printf "  ${color}%-14s${NC} %4d  %s\n" "$sev" "$cnt" "$(bar $pct)"
done

# ── 4. 组件异常分布 ──────────────────────────────────
echo ""
printf "${BOLD}  🔧 组件异常统计${NC}${DIM} (排除 ok 和 skipped)${NC}\n"
printf "  ─────────────────────────────────\n"
COMP_DATA=$(echo "$FILTERED" | jq -r '
    [.[] | .components | to_entries[] |
     .value as $v | (if ($v | type) == "object" then $v.status else $v end) as $st |
     select($st != "ok" and $st != "skipped") | {key, value: $st}]
    | group_by(.key) | map({component: .[0].key, total: length,
        warning: [.[] | select(.value == "warning")] | length,
        critical: [.[] | select(.value == "critical")] | length})
    | sort_by(-.total)[] | "\(.component) \(.total) \(.warning) \(.critical)"
')

if [ -z "$COMP_DATA" ]; then
    printf "  ${GREEN}✔ 所有诊断中没有组件异常${NC}\n"
else
    printf "  ${DIM}%-14s %6s %8s %8s${NC}\n" "组件" "异常数" "warning" "critical"
    echo "$COMP_DATA" | while read comp total warn crit; do
        printf "  %-14s %6d  ${YELLOW}%5d W${NC}  ${RED}%5d C${NC}\n" "$comp" "$total" "$warn" "$crit"
    done
fi

# ── 5. 触发方式 ──────────────────────────────────────
echo ""
printf "${BOLD}  ⚡ 触发方式${NC}\n"
printf "  ─────────────────────────────────\n"
echo "$FILTERED" | jq -r '
    group_by(.trigger) | map({trigger: .[0].trigger, count: length})
    | sort_by(-.count)[] | "\(.trigger) \(.count)"
' | while read trig cnt; do
    pct=$(( cnt * 100 / COUNT ))
    printf "  %-14s %4d  %s\n" "$trig" "$cnt" "$(bar $pct)"
done

# ── 6. Top 场景 ──────────────────────────────────────
echo ""
printf "${BOLD}  📋 Top 场景${NC}\n"
printf "  ─────────────────────────────────\n"
echo "$FILTERED" | jq -r '
    group_by(.scenario) | map({scenario: .[0].scenario, count: length})
    | sort_by(-.count) | .[0:10][] | "\(.scenario) \(.count)"
' | while read scenario cnt; do
    pct=$(( cnt * 100 / COUNT ))
    printf "  %-24s %4d  %s\n" "$scenario" "$cnt" "$(bar $pct)"
done

# ── 7. 每日趋势（最近 7 天有数据的日期）────────────
echo ""
printf "${BOLD}  📈 每日趋势${NC}${DIM} (近 7 天有数据)${NC}\n"
printf "  ─────────────────────────────────\n"
echo "$FILTERED" | jq -r '
    [.[] | .date = (.ts | split("T")[0])]
    | group_by(.date) | map({
        date: .[0].date,
        total: length,
        issues: [.[] | select(.issues_found > 0)] | length
    }) | sort_by(.date) | .[-7:][]
    | "\(.date) \(.total) \(.issues)"
' | while read date total issues; do
    ok_cnt=$(( total - issues ))
    printf "  %s  诊断 %3d  " "$date" "$total"
    printf "${GREEN}✔ %d${NC}  " "$ok_cnt"
    if [ "$issues" -gt 0 ]; then
        printf "${RED}✘ %d${NC}" "$issues"
    else
        printf "✘ 0"
    fi
    echo ""
done

# ── 8. OS 分布 ───────────────────────────────────────
OS_COUNT=$(echo "$FILTERED" | jq '[.[] | .os] | unique | length')
if [ "$OS_COUNT" -gt 1 ]; then
    echo ""
    printf "${BOLD}  💻 OS 分布${NC}\n"
    printf "  ─────────────────────────────────\n"
    echo "$FILTERED" | jq -r '
        group_by(.os) | map({os: .[0].os, count: length})
        | sort_by(-.count)[] | "\(.os) \(.count)"
    ' | while read os cnt; do
        pct=$(( cnt * 100 / COUNT ))
        printf "  %-14s %4d  %s\n" "$os" "$cnt" "$(bar $pct)"
    done
fi

echo ""
printf "${BOLD}${CYAN}═══════════════════════════════════════════════════════${NC}\n"
printf "${DIM}  数据来源: %s (%s 条记录)${NC}\n" "$STATS_FILE" "$COUNT"
printf "${BOLD}${CYAN}═══════════════════════════════════════════════════════${NC}\n"
echo ""
