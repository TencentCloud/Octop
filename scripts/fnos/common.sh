#!/bin/bash
#
# Octop FnOS 打包共享函数库。
# 仓库唯一来源：scripts/fnos/common.sh
# 打包时由 scripts/build-fpk.sh 注入到包内 cmd/common.sh；
# fnos/docker/ 与 fnos/native/ 的 cmd 脚本及 app/bin 脚本统一 source 本文件，
# 避免 find_python312 / fix_ownership_and_perms / free_octop_ports 重复维护。
#
set -u

# ---------------------------------------------------------------------------
# 释放 Octop 端口（8088=Docker 版，8089=本地版）并清理本应用残留进程。
# 仅清理：(1) 占用 Octop 端口的进程；(2) 本安装目录（TRIM_APPDEST）下的
# octop 服务进程。不使用宽泛的 `pgrep -f octop`，避免误杀其它用户/其它
# 安装路径下的同名进程。
# ---------------------------------------------------------------------------
free_octop_ports() {
    local port pid pids pat appdir
    for port in 8088 8089; do
        pids="$(ss -ltnp 2>/dev/null | grep -E "[:.]${port}([[:space:]]|$)" | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u)" || true
        if [ -z "$pids" ] && command -v fuser >/dev/null 2>&1; then
            pids="$(fuser "${port}/tcp" 2>/dev/null | tr -cs '[:digit:]' ' ')" || true
        fi
        if [ -z "$pids" ] && command -v lsof >/dev/null 2>&1; then
            pids="$(lsof -ti tcp:"$port" 2>/dev/null)" || true
        fi
        for pid in $pids; do
            [ -n "$pid" ] || continue
            if kill -TERM "$pid" 2>/dev/null; then
                echo "[octop] 已发送 TERM 给占用 ${port} 的进程 ${pid}" > "${TRIM_TEMP_LOGFILE:-/dev/null}" 2>/dev/null || true
            fi
        done
        sleep 1
        for pid in $pids; do
            [ -n "$pid" ] || continue
            if kill -0 "$pid" 2>/dev/null; then
                kill -KILL "$pid" 2>/dev/null || true
                echo "[octop] 已强制 KILL 占用 ${port} 的进程 ${pid}" > "${TRIM_TEMP_LOGFILE:-/dev/null}" 2>/dev/null || true
            fi
        done
    done

    # 兜底：只按本安装目录精确匹配，防止误杀其它实例。
    appdir="${TRIM_APPDEST:-/var/apps/octop-native}"
    for pat in "$appdir/bin/octop" "$appdir/app/bin/octop"; do
        pids="$(pgrep -f -- "$pat" 2>/dev/null | tr '\n' ' ')" || true
        [ -z "$pids" ] && continue
        echo "[octop] 发现本应用残留服务进程（$pat）: $pids，准备清理" > "${TRIM_TEMP_LOGFILE:-/dev/null}" 2>&1 || true
        for pid in $pids; do
            kill -TERM "$pid" 2>/dev/null || true
        done
        sleep 1
        for pid in $pids; do
            if kill -0 "$pid" 2>/dev/null; then
                kill -KILL "$pid" 2>/dev/null || true
                echo "[octop] 已强制 KILL 残留服务进程 ${pid}" > "${TRIM_TEMP_LOGFILE:-/dev/null}" 2>&1 || true
            fi
        done
    done
}

# ---------------------------------------------------------------------------
# 修正数据目录与 .env 的属主/权限。
# install_callback/config_callback 以 root 写 .env，若不 chown 给运行用户，
# 服务（octop-native）启动时 `. "$PKGVAR/.env"` 会 Permission denied。
# 若目录曾带 ACL，单纯 chmod 会把 mask 压成 ---，需 setfacl -b 清除。
# ---------------------------------------------------------------------------
fix_ownership_and_perms() {
    local pkgvar="$1" envfile="$2"
    local octop_user="octop-native"
    id "$octop_user" >/dev/null 2>&1 || {
        echo "[octop] 警告：${octop_user} 账户不存在，跳过数据目录 chown（服务将回退以 root 运行）" > "${TRIM_TEMP_LOGFILE:-/dev/null}" 2>&1 || true
        return 0
    }

    # 1) 应用数据目录与 .env 改属主为运行用户
    chown -R "$octop_user:$octop_user" "$pkgvar" 2>/dev/null || true
    chmod 700 "$pkgvar" 2>/dev/null || true
    [ -f "$envfile" ] && chmod 600 "$envfile" 2>/dev/null || true

    # 2) 清除 ACL，避免 chmod 把 mask 压成 --- 导致仍读不到
    if command -v setfacl >/dev/null 2>&1; then
        setfacl -b "$pkgvar" 2>/dev/null || true
        [ -f "$envfile" ] && setfacl -b "$envfile" 2>/dev/null || true
    fi

    # 3) 共享数据目录（@appshare）：确保属主正确且可进入
    if [ -n "${TRIM_DATA_SHARE_PATHS:-}" ]; then
        local ds="${TRIM_DATA_SHARE_PATHS%%:*}"
        chown -R "$octop_user:$octop_user" "$ds" 2>/dev/null || true
        local share_root="$ds"
        while [ "$share_root" != "/" ] && [ "$(basename "$(dirname "$share_root")")" != "@appshare" ]; do
            share_root="$(dirname "$share_root")"
        done
        chown "$octop_user:$octop_user" "$share_root" 2>/dev/null || true
        chmod 755 "$share_root" 2>/dev/null || true
        if command -v setfacl >/dev/null 2>&1; then
            setfacl -b "$share_root" 2>/dev/null || true
            setfacl -b "$ds" 2>/dev/null || true
        fi
    fi

    echo "[octop] 已修正数据目录/.env 属主与权限（${octop_user}:${octop_user}）" > "${TRIM_TEMP_LOGFILE:-/dev/null}" 2>&1 || true
}

# ---------------------------------------------------------------------------
# 查找飞牛系统上的 Python 3.12（应用商店提供）。
# ---------------------------------------------------------------------------
find_python312() {
    local cand py
    for cand in \
        /var/apps/python312/target/bin/python3.12 \
        /usr/local/bin/python3.12 \
        /var/apps/python3.12/bin/python3.12 \
        python3.12
    do
        if command -v "$cand" >/dev/null 2>&1; then
            py="$(command -v "$cand")"
            if "$py" -c 'import sys; assert sys.version_info[:2] == (3,12)' >/dev/null 2>&1; then
                printf '%s' "$py"
                return 0
            fi
        fi
    done
    return 1
}
