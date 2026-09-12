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

# ---------------------------------------------------------------------------
# 管理员密码：生成 / 校验 / 凭据回落保存。
#
# 背景（issue #502）：src/octop/infra/users/password.py 的弱密码黑名单包含
# "octop123"，而 FPK 旧版把初始密码写死为 Octop123，导致 octop init 在首次
# 启动时报 "password is too common" 直接退出、应用永远起不来。这里的函数
# 让安装向导接管密码设置：用户自定义（先本地校验，杜绝无效密码进入 init）
# 或自动生成随机强密码，并回落保存到数据目录，保证用户不丢密码。
# ---------------------------------------------------------------------------

# 向导字段值清洗：去掉会破坏 .env / JSON / shell 的字符。
# 与各回调脚本内历史 sanitize() 等价，但额外去除反斜杠（JSON 注入面）。
octop_sanitize_value() {
    printf '%s' "$1" | tr -d '\n\r"'"'"'\\'
}

# 生成随机密码：首字符为字母、末字符为数字，全部取自无易混淆字符的字母数字表。
# 长度默认 16（至少 8）。依赖 /dev/urandom（飞牛与容器内均可用）。
octop_generate_password() {
    local letters='abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ'
    local digits='23456789'
    local all="${letters}${digits}"
    local n="${1:-16}" out="" i b
    case "$n" in ''|*[!0-9]*) n=16 ;; esac
    [ "$n" -lt 8 ] && n=8
    b="$(od -An -N1 -tu1 /dev/urandom 2>/dev/null | tr -d '[:space:]')"
    [ -n "$b" ] || b=7
    out="${letters:$((b % ${#letters})):1}"
    for ((i = 1; i < n - 1; i++)); do
        b="$(od -An -N1 -tu1 /dev/urandom 2>/dev/null | tr -d '[:space:]')"
        [ -n "$b" ] || b=$((RANDOM % 255))
        out+="${all:$((b % ${#all})):1}"
    done
    b="$(od -An -N1 -tu1 /dev/urandom 2>/dev/null | tr -d '[:space:]')"
    [ -n "$b" ] || b=3
    out+="${digits:$((b % ${#digits})):1}"
    printf '%s' "$out"
}

# 校验密码是否满足应用侧策略（src/octop/infra/users/password.py）：
# ≥8 位、同时含字母和数字、不在常见弱密码黑名单内。
# 黑名单须与 password.py 的 _COMMON_PASSWORDS 保持一致（有单测对拍）。
# 校验失败时向 stderr 输出中文原因，返回非零。
octop_validate_password() {
    local pw="$1" reason=""
    if [ -z "$pw" ]; then
        reason="密码为空"
    elif [ "${#pw}" -lt 8 ]; then
        reason="密码长度至少 8 位"
    elif [ "${#pw}" -gt 64 ]; then
        reason="密码长度不能超过 64 位"
    elif ! printf '%s' "$pw" | grep -q '[A-Za-z]'; then
        reason="密码必须同时包含字母和数字"
    elif ! printf '%s' "$pw" | grep -q '[0-9]'; then
        reason="密码必须同时包含字母和数字"
    elif printf '%s' "$pw" | tr 'A-Z' 'a-z' | grep -qx \
        -e 'password' -e 'password1' -e 'password12' -e 'password123' \
        -e '12345678' -e '123456789' -e 'qwerty123' -e 'admin123' \
        -e 'welcome1' -e 'letmein1' -e 'changeme1' -e 'octop123' \
        -e 'abc12345' -e 'iloveyou1'
    then
        reason="密码过于常见（password is too common），请换一个更复杂的密码"
    fi
    if [ -n "$reason" ]; then
        echo "$reason" >&2
        return 1
    fi
    return 0
}

# 从 .env 文件读取 KEY=VALUE 的值（容忍引号与行尾空白）。
octop_env_get() {
    local file="$1" key="$2" line
    [ -f "$file" ] || return 0
    line="$(grep -E "^${key}=" "$file" 2>/dev/null | tail -n 1)"
    line="${line#*=}"
    line="${line%\"}"; line="${line#\"}"
    printf '%s' "$line"
}

# 原地更新 .env 中的单个 KEY（保留其余行）；不存在则创建。
# 纯 bash 实现：密码可能包含 | & / 等 sed 特殊字符，不能用 sed 替换。
octop_env_set() {
    local file="$1" key="$2" value="$3" tmp line
    if [ -f "$file" ]; then
        tmp="${file}.tmp.$$"
        : > "$tmp"
        while IFS= read -r line || [ -n "$line" ]; do
            case "$line" in
                "${key}="*) ;;
                *) printf '%s\n' "$line" >> "$tmp" ;;
            esac
        done < "$file"
        printf '%s=%s\n' "$key" "$value" >> "$tmp"
        mv -f "$tmp" "$file"
    else
        printf '%s=%s\n' "$key" "$value" > "$file"
    fi
    chmod 600 "$file" 2>/dev/null || true
}

# 管理员凭据回落保存（数据目录 octop-login.txt，永久保留、只随密码修改刷新）。
# 这是「用户不丢密码」的最后防线：设置窗口显示 + 本文件备份，双通道。
# 调用方需保证 data_dir 已存在；文件属主交给 fix_ownership_and_perms 统一修正。
octop_write_login_file() {
    local data_dir="$1" username="$2" password="$3" port="${4:-8089}" file
    [ -n "$data_dir" ] && [ -d "$data_dir" ] || return 0
    file="${data_dir}/octop-login.txt"
    cat > "$file" << EOF
==========================================================
 Octop 管理员登录信息（请妥善保管，勿泄露给他人）
==========================================================
访问地址：http://<飞牛IP>:${port}
管理员账号：${username}
管理员密码：${password}

说明：
- 本文件是管理员密码的备份副本，每次通过应用「设置」修改密码后会自动更新。
- 也可以随时在飞牛应用中心 → Octop → 「设置」窗口中直接查看当前密码。
- 建议登录后在 Web 控制台「头像菜单 → 修改密码」中更换为自己的密码。
EOF
    chmod 600 "$file" 2>/dev/null || true
}

# 用当前用户名/密码渲染应用「设置」窗口表单（wizard/config）。
# 模板文件内含 <octop-current-username> / <octop-current-password> 占位符，
# 每次安装/改密后整体重渲染，让用户打开设置窗口即可看到当前密码（免翻文件）。
# wizard_dir 为已安装包的向导目录（/var/apps/<app>/wizard），template 为
# 包内载荷自带的模板文件路径。任一文件缺失则静默跳过（不影响安装）。
octop_render_config_wizard() {
    local template="$1" wizard_dir="$2" username="$3" password="$4" target tmp content
    [ -f "$template" ] || return 0
    [ -d "$wizard_dir" ] || return 0
    target="${wizard_dir}/config"
    content="$(cat "$template" 2>/dev/null)" || return 0
    content="${content//<octop-current-username>/${username}}"
    content="${content//<octop-current-password>/${password}}"
    tmp="${target}.tmp.$$"
    if printf '%s\n' "$content" > "$tmp" 2>/dev/null; then
        mv -f "$tmp" "$target" 2>/dev/null || rm -f "$tmp"
    fi
    return 0
}
