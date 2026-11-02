#!/usr/bin/env bash
# ==============================================================================
# CVM Doctor Patrol — 启动 Dashboard 本地服务
# ==============================================================================
# 功能: 启动一个简单的 HTTP 服务器，方便 Dashboard 加载本地 JSONL 数据
# 用法:
#   bash scripts/serve_dashboard.sh          # 启动服务并打开浏览器
#   bash scripts/serve_dashboard.sh --port 9090  # 指定端口
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PORT="${2:-8765}"

# 颜色
CYAN='\033[0;36m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m'

# 解析参数
for arg in "$@"; do
    case "$arg" in
        --port) shift; PORT="$1"; shift ;;
    esac
done

echo ""
printf "${BOLD}${CYAN}CVM Doctor Patrol Dashboard${NC}\n"
printf "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
echo ""
printf "  URL:  ${GREEN}http://localhost:${PORT}/docs/patrol-dashboard.html${NC}\n"
printf "  数据: ~/.lightclaw/stats/cvm-doctor.jsonl\n"
echo ""
printf "  ${BOLD}按 Ctrl+C 停止服务${NC}\n"
echo ""

# 打开浏览器 (macOS / Linux)
if [ "$(uname -s)" = "Darwin" ]; then
    (sleep 1 && open "http://localhost:${PORT}/docs/patrol-dashboard.html") &
elif command -v xdg-open &>/dev/null; then
    (sleep 1 && xdg-open "http://localhost:${PORT}/docs/patrol-dashboard.html") &
fi

# 启动 HTTP 服务
cd "$PROJECT_DIR"
if command -v python3 &>/dev/null; then
    python3 -m http.server "$PORT"
elif command -v python &>/dev/null; then
    python -m http.server "$PORT"
else
    echo "[ERR] 未找到 Python，无法启动 HTTP 服务"
    echo "      请安装 Python 或手动打开: file://${PROJECT_DIR}/docs/patrol-dashboard.html"
    exit 1
fi
