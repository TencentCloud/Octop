#!/bin/bash
# Wenyan Server 一键部署脚本
# 在你的云服务器上运行此脚本即可完成 wenyan server 部署
#
# Usage:
#   curl -fsSL <script_url> | bash
#   # 或
#   bash setup_server.sh

set -e

echo "╔══════════════════════════════════════════════════════╗"
echo "║   Wenyan Server 一键部署                              ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PORT=${WENYAN_PORT:-7788}
LOG_FILE="/var/log/wenyan-server.log"

# Step 1: Check Node.js
echo -e "${YELLOW}[1/4] 检查 Node.js...${NC}"
if command -v node &>/dev/null; then
    NODE_VER=$(node --version)
    echo -e "  ${GREEN}✅ Node.js $NODE_VER 已安装${NC}"
else
    echo "  ⏳ 安装 Node.js..."
    if command -v apt-get &>/dev/null; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
        apt-get install -y nodejs
    elif command -v yum &>/dev/null; then
        curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
        yum install -y nodejs
    else
        echo -e "  ${RED}❌ 无法自动安装 Node.js，请手动安装${NC}"
        exit 1
    fi
    echo -e "  ${GREEN}✅ Node.js $(node --version) 安装完成${NC}"
fi

# Step 2: Install wenyan-cli
echo -e "${YELLOW}[2/4] 安装 wenyan-cli...${NC}"
if command -v wenyan &>/dev/null; then
    WENYAN_VER=$(wenyan --version 2>/dev/null || echo "unknown")
    echo -e "  ${GREEN}✅ wenyan-cli $WENYAN_VER 已安装${NC}"
else
    npm install -g @wenyan-md/cli
    echo -e "  ${GREEN}✅ wenyan-cli 安装完成${NC}"
fi

# Step 3: Check env vars
echo -e "${YELLOW}[3/4] 检查环境变量...${NC}"
if [ -z "$WECHAT_APP_ID" ]; then
    echo -e "  ${RED}❌ WECHAT_APP_ID 未设置${NC}"
    echo "     请设置: export WECHAT_APP_ID='your_app_id'"
    MISSING_ENV=true
fi
if [ -z "$WECHAT_APP_SECRET" ]; then
    echo -e "  ${RED}❌ WECHAT_APP_SECRET 未设置${NC}"
    echo "     请设置: export WECHAT_APP_SECRET='your_app_secret'"
    MISSING_ENV=true
fi
if [ "$MISSING_ENV" = true ]; then
    echo ""
    echo "  设置好环境变量后重新运行此脚本。"
    echo "  建议写入 /etc/environment 或 ~/.bashrc 中持久化。"
    exit 1
fi
echo -e "  ${GREEN}✅ WECHAT_APP_ID: ${WECHAT_APP_ID:0:4}...${NC}"
echo -e "  ${GREEN}✅ WECHAT_APP_SECRET: ***set***${NC}"

# Step 4: Start server
echo -e "${YELLOW}[4/4] 启动 wenyan server (port $PORT)...${NC}"

# Kill existing
pkill -f "wenyan serve" 2>/dev/null || true
sleep 1

# Start
nohup wenyan serve --port "$PORT" >> "$LOG_FILE" 2>&1 &
disown
sleep 2

# Verify
if pgrep -f "wenyan serve" > /dev/null; then
    PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || echo "unknown")
    echo -e "  ${GREEN}✅ Server 启动成功${NC}"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  📡 Server URL: http://${PUBLIC_IP}:${PORT}"
    echo "  📋 日志文件:   ${LOG_FILE}"
    echo ""
    echo "  接下来请完成以下操作:"
    echo ""
    echo "  1. 将此 IP 加入微信 API 白名单: ${PUBLIC_IP}"
    echo "     https://developers.weixin.qq.com/console/product/mp"
    echo ""
    echo "  2. 在本地设置环境变量:"
    echo "     export WENYAN_SERVER=\"http://${PUBLIC_IP}:${PORT}\""
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
    echo -e "  ${RED}❌ Server 启动失败，请检查日志: ${LOG_FILE}${NC}"
    tail -20 "$LOG_FILE" 2>/dev/null
    exit 1
fi
