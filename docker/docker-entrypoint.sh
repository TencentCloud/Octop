#!/usr/bin/env bash
# =============================================================================
# Octop 容器入口脚本
#
# 环境变量:
#   HOME                      — 必须为 /data，使 ~/.octop 映射到数据卷
#   OCTOP_DEFAULT_PASSWORD    — 首次管理员密码（默认: octop）
#   OCTOP_ADMIN_USERNAME      — 首次管理员用户名（默认: admin）
#   OCTOP_ADMIN_DISPLAY_NAME  — 可选显示名
#   OCTOP_PORT                — 服务端口（默认: 8088）
# =============================================================================
set -euo pipefail

export HOME="${HOME:-/data}"
OCTOP_HOME="${HOME}/.octop"
DB_FILE="${OCTOP_HOME}/octop.db"
CREDENTIAL_FILE="${OCTOP_HOME}/credential.txt"
DEFAULT_PASSWORD="${OCTOP_DEFAULT_PASSWORD:-octop}"
ADMIN_USERNAME="${OCTOP_ADMIN_USERNAME:-admin}"
ADMIN_DISPLAY_NAME="${OCTOP_ADMIN_DISPLAY_NAME:-Admin}"
PORT="${OCTOP_PORT:-8088}"

mkdir -p "$OCTOP_HOME"

# 运行时修复: harness-agent MRO 顺序问题（与 Dockerfile 补丁配合，覆盖已运行旧镜像的场景）
# 上游修复发布后可移除此段
_patch_mro() {
    local server_py
    server_py="$(find /app/.venv/lib -path '*/harness_agent/acp/server.py' -print -quit 2>/dev/null || true)"
    if [ -n "$server_py" ] && [ -f "$server_py" ] && grep -q 'class _Agent(Agent, HarnessACPAgent):' "$server_py"; then
        sed -i 's/class _Agent(Agent, HarnessACPAgent):/class _Agent(HarnessACPAgent, Agent):/' "$server_py"
        echo "[entrypoint] Patched harness_agent MRO order in: $server_py"
    fi
}
_patch_mro

if [ ! -f "$DB_FILE" ]; then
    echo "[entrypoint] 首次启动，正在初始化 Octop..."

    octop init \
        --yes \
        --admin-username "$ADMIN_USERNAME" \
        --admin-password "$DEFAULT_PASSWORD" \
        ${ADMIN_DISPLAY_NAME:+--admin-display-name "$ADMIN_DISPLAY_NAME"}

    cat > "$CREDENTIAL_FILE" << EOF
Octop Login Credential
======================
Username: $ADMIN_USERNAME
Password: $DEFAULT_PASSWORD

Please change this password after first login!
  - Via Web: Settings → User → Password
  - Via CLI: docker exec -it <container> octop user passwd --username $ADMIN_USERNAME
EOF
    chmod 600 "$CREDENTIAL_FILE"
    echo "[entrypoint] 凭据已保存至: $CREDENTIAL_FILE"
fi

if [ $# -eq 0 ]; then
    echo "[entrypoint] 正在启动 Octop，端口 $PORT..."
    exec octop run --host 0.0.0.0 --port "$PORT"
fi

if [ "$1" = "octop" ]; then
    echo "[entrypoint] 执行命令: $*"
    exec "$@"
fi

echo "[entrypoint] 执行命令: $*"
exec "$@"
