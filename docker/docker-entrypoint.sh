#!/usr/bin/env bash
# =============================================================================
# Octop 容器入口脚本
#
# 环境变量:
#   HOME                      — 必须为 /data，使 ~/.octop 映射到数据卷
#   OCTOP_DEFAULT_PASSWORD    — 首次管理员密码（须 ≥8 位且含字母和数字；
#                               不设置则自动生成随机密码，凭据写入
#                               /data/.octop/credential.txt）
#   OCTOP_ADMIN_USERNAME      — 首次管理员用户名（默认: admin）
#   OCTOP_ADMIN_DISPLAY_NAME  — 可选显示名
#   OCTOP_PORT                — 服务端口（默认: 8088）
#
# 密码兜底（修复 issue #502）：应用侧密码策略带常见弱密码黑名单（含
# Octop123），旧版默认密码会让 octop init 报 "password is too common"
# 退出、容器反复重启。现在：未设置密码时自动生成随机强密码；指定的
# 密码被策略拒绝时也自动改用随机密码重试，保证容器一定能完成首次初始化。
# =============================================================================
set -euo pipefail

export HOME="${HOME:-/data}"
OCTOP_HOME="${HOME}/.octop"
DB_FILE="${OCTOP_HOME}/octop.db"
CREDENTIAL_FILE="${OCTOP_HOME}/credential.txt"
ADMIN_USERNAME="${OCTOP_ADMIN_USERNAME:-admin}"
ADMIN_DISPLAY_NAME="${OCTOP_ADMIN_DISPLAY_NAME:-Admin}"
PORT="${OCTOP_PORT:-8088}"

# 生成随机密码（首字符字母、末字符数字，避开易混淆字符）。
octop_random_password() {
    local letters='abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ'
    local digits='23456789'
    local all="${letters}${digits}" n=16 out="" i b
    b="$(od -An -N1 -tu1 /dev/urandom 2>/dev/null | tr -d '[:space:]')"
    out="${letters:$((b % ${#letters})):1}"
    for ((i = 1; i < n - 1; i++)); do
        b="$(od -An -N1 -tu1 /dev/urandom 2>/dev/null | tr -d '[:space:]')"
        out+="${all:$((b % ${#all})):1}"
    done
    b="$(od -An -N1 -tu1 /dev/urandom 2>/dev/null | tr -d '[:space:]')"
    out+="${digits:$((b % ${#digits})):1}"
    printf '%s' "$out"
}

DEFAULT_PASSWORD="${OCTOP_DEFAULT_PASSWORD:-}"

if [ ! -f "$DB_FILE" ]; then
    echo "[entrypoint] 首次启动，正在初始化 Octop..."

    if [ -z "$DEFAULT_PASSWORD" ]; then
        DEFAULT_PASSWORD="$(octop_random_password)"
        echo "[entrypoint] 未设置 OCTOP_DEFAULT_PASSWORD，已自动生成随机密码。"
    fi

    if ! octop init \
        --yes \
        --admin-username "$ADMIN_USERNAME" \
        --admin-password "$DEFAULT_PASSWORD" \
        ${ADMIN_DISPLAY_NAME:+--admin-display-name "$ADMIN_DISPLAY_NAME"}; then
        echo "[entrypoint] 指定的初始密码未通过应用密码策略（过弱或过于常见），改用随机密码重试 ..."
        DEFAULT_PASSWORD="$(octop_random_password)"
        octop init \
            --yes \
            --admin-username "$ADMIN_USERNAME" \
            --admin-password "$DEFAULT_PASSWORD" \
            ${ADMIN_DISPLAY_NAME:+--admin-display-name "$ADMIN_DISPLAY_NAME"}
    fi

    cat > "$CREDENTIAL_FILE" << EOF
Octop Login Credential
======================
URL:      http://<host>:${PORT}
Username: ${ADMIN_USERNAME}
Password: ${DEFAULT_PASSWORD}

Please change this password after first login!
  - Via Web: avatar menu → Change password
  - Via CLI: docker exec -it <container> octop user passwd --username $ADMIN_USERNAME

This file is rewritten whenever the initial password is (re)generated here.
If you changed the password inside the Web console, that password wins.
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
