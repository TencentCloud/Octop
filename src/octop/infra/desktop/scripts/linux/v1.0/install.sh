#!/bin/bash
#
# Octop virtual desktop installer for headless Linux servers.
# Adapted from agent-bridge scripts/desktop/v1.0 (TigerVNC + openbox stack).
#
# Usage:
#   sudo bash install.sh [--geometry 1920x1080]
#
# Output (last line):
#   {"installed": true}
#   {"installed": false, "error": "..."}

if [ -z "${BASH_VERSION:-}" ]; then exec /bin/bash "$0" "$@"; fi
set -uo pipefail

SCRIPT_VERSION="v1.0"
INSTALL_ROOT="/opt/octop-desktop"
CONF_DIR="/etc/octop-desktop"
DISPLAY_NUM=":99"
GEOMETRY="${GEOMETRY:-1920x1080}"
WALLPAPER_URL="${WALLPAPER_URL:-https://finnie-1258344699.cos.ap-guangzhou.myqcloud.com/wallpaper/1.png}"
VNC_PORT=5900
OCTOP_HOME="${OCTOP_HOME:-$HOME/.octop}"
DESKTOP_STATE_DIR="${OCTOP_HOME}/desktop"
DESKTOP_ENV="${DESKTOP_STATE_DIR}/desktop.env"

SVC_XVNC="octop-desktop-xvnc"
SVC_OPENBOX="octop-desktop-openbox"
SVC_SESSION="octop-desktop-session"

START_OPENBOX_SH="${INSTALL_ROOT}/start-openbox.sh"
START_SESSION_SH="${INSTALL_ROOT}/start-session.sh"
OPENBOX_XML="${INSTALL_ROOT}/openbox.xml"
TRUST_ICONS_HELPER="${INSTALL_ROOT}/trust-desktop-icons.sh"
APPLY_WALLPAPER_SH="${INSTALL_ROOT}/apply-wallpaper.sh"

DESKTOP_DIR="/root/Desktop"
AUTOSTART_DIR="/root/.config/autostart"
WALLPAPER_FILE="/usr/share/backgrounds/octop-desktop-wallpaper.svg"
WALLPAPER_PNG="/usr/share/backgrounds/octop-desktop-wallpaper.png"
XFCONF_DESKTOP_XML="/root/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml"

fail() {
    local msg="$1"
    msg=$(echo "$msg" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ')
    echo "{\"installed\": false, \"error\": \"${msg}\"}"
    exit 1
}

detect_distro() {
    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        case "${ID:-}${ID_LIKE:-}" in
            *debian*|*ubuntu*) echo debian ;;
            *rhel*|*centos*|*fedora*|*tencentos*|*tencent*) echo rhel ;;
            *) echo unknown ;;
        esac
    elif command -v apt-get >/dev/null 2>&1; then
        echo debian
    elif command -v yum >/dev/null 2>&1 || command -v dnf >/dev/null 2>&1; then
        echo rhel
    else
        echo unknown
    fi
}

detect_xvnc_bin() {
    local p
    for p in /usr/bin/Xvnc /usr/libexec/Xvnc /usr/bin/Xtigervnc /usr/libexec/Xtigervnc; do
        [ -x "$p" ] && { echo "$p"; return 0; }
    done
    command -v Xvnc >/dev/null 2>&1 && { echo Xvnc; return 0; }
    command -v Xtigervnc >/dev/null 2>&1 && { echo Xtigervnc; return 0; }
    return 1
}

detect_vncpasswd_bin() {
    local p
    for p in /usr/bin/vncpasswd /usr/libexec/vnc/vncpasswd /usr/lib/tigervnc/vncpasswd; do
        [ -x "$p" ] && { echo "$p"; return 0; }
    done
    command -v vncpasswd >/dev/null 2>&1 && { echo vncpasswd; return 0; }
    return 1
}

install_packages() {
    local family="$1"
    if [ "$family" = debian ]; then
        DEBIAN_FRONTEND=noninteractive apt-get update -qq || fail "apt-get update failed"
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
            tigervnc-standalone-server tigervnc-tools x11-xserver-utils x11-utils openbox \
            dbus dbus-x11 xdotool xauth imagemagick \
            xfce4-panel xfce4-terminal xfce4-settings xfdesktop4 thunar mousepad \
            fcitx5 fcitx5-chinese-addons fcitx5-frontend-gtk3 \
            fonts-wqy-zenhei locales xclip xsel autocutsel xdg-utils libglib2.0-bin wget curl \
            || fail "apt install failed"
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
            chromium \
            || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
                firefox-esr \
                || true
    elif [ "$family" = rhel ]; then
        local pkg=dnf
        command -v dnf >/dev/null 2>&1 || pkg=yum
        $pkg install -y tigervnc-server openbox dbus dbus-x11 xdotool xorg-x11-xauth \
            xfce4-panel xfce4-terminal xfce4-settings xfdesktop thunar mousepad \
            fcitx fcitx-pinyin fcitx-gtk3 \
            google-noto-cjk-fonts ImageMagick xclip xsel xdg-utils \
            || fail "yum/dnf install failed"
        $pkg install -y chromium firefox 2>/dev/null || true
    else
        fail "unsupported distro"
    fi
}

configure_locale_and_fonts() {
    if command -v localedef >/dev/null 2>&1; then
        localedef -i zh_CN -c -f UTF-8 -A /usr/share/locale/locale.alias zh_CN.UTF-8 2>/dev/null || true
    fi
    if [ -f /etc/default/locale ]; then
        grep -q 'LANG=zh_CN.UTF-8' /etc/default/locale 2>/dev/null || cat >> /etc/default/locale << 'LOCALE_EOF'
LANG=zh_CN.UTF-8
LC_ALL=zh_CN.UTF-8
LANGUAGE=zh_CN:zh
LOCALE_EOF
    fi
    fc-cache -f 2>/dev/null || true
}

detect_browser_bin() {
    for p in /usr/bin/chromium /usr/bin/chromium-browser /usr/bin/google-chrome-stable /usr/bin/firefox-esr /usr/bin/firefox; do
        [ -x "$p" ] && { echo "$p"; return 0; }
    done
    return 1
}

write_xfconf_desktop_defaults() {
    local wallpaper="$WALLPAPER_PNG"
    [ -f "$wallpaper" ] || wallpaper="$WALLPAPER_FILE"
    mkdir -p "$(dirname "$XFCONF_DESKTOP_XML")"
    cat > "$XFCONF_DESKTOP_XML" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-desktop" version="1.0">
  <property name="backdrop" type="empty">
    <property name="screen0" type="empty">
      <property name="monitorVNC-0" type="empty">
        <property name="workspace0" type="empty">
          <property name="last-image" type="string" value="${wallpaper}"/>
          <property name="image-style" type="int" value="5"/>
          <property name="color-style" type="int" value="0"/>
        </property>
        <property name="workspace1" type="empty">
          <property name="last-image" type="string" value="${wallpaper}"/>
          <property name="image-style" type="int" value="5"/>
          <property name="color-style" type="int" value="0"/>
        </property>
      </property>
    </property>
  </property>
  <property name="desktop-icons" type="empty">
    <property name="file-icons" type="empty">
      <property name="show-trash" type="bool" value="true"/>
      <property name="show-home" type="bool" value="true"/>
      <property name="show-filesystem" type="bool" value="true"/>
    </property>
  </property>
</channel>
EOF
    chmod 0644 "$XFCONF_DESKTOP_XML"
}

download_wallpaper() {
    mkdir -p /usr/share/backgrounds
    local url ok=false
    for url in \
        "${WALLPAPER_URL}" \
        "https://finnie-1258344699.cos.ap-guangzhou.myqcloud.com/wallpaper/1.png"; do
        [ -n "$url" ] || continue
        if command -v wget >/dev/null 2>&1; then
            wget --timeout=20 --tries=2 -qO "$WALLPAPER_PNG" "$url" 2>/dev/null \
                && [ -s "$WALLPAPER_PNG" ] && { ok=true; break; }
        fi
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL --connect-timeout 20 --max-time 60 "$url" -o "$WALLPAPER_PNG" 2>/dev/null \
                && [ -s "$WALLPAPER_PNG" ] && { ok=true; break; }
        fi
    done
    if [ "$ok" = false ]; then
        cat > "$WALLPAPER_FILE" << 'WALL_EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"><rect width="100%" height="100%" fill="#1a1a2e"/></svg>
WALL_EOF
        if command -v convert >/dev/null 2>&1; then
            convert "$WALLPAPER_FILE" -resize 1920x1080! "$WALLPAPER_PNG" 2>/dev/null || ok=false
        fi
    fi
    [ -s "$WALLPAPER_PNG" ] && chmod 0644 "$WALLPAPER_PNG"
}

configure_desktop_environment() {
    local browser_bin browser_name browser_icon
    browser_bin=$(detect_browser_bin || true)
    browser_name="Browser"
    browser_icon="web-browser"
    case "$browser_bin" in
        *chromium*) browser_name="Chromium"; browser_icon="chromium" ;;
        *firefox*) browser_name="Firefox"; browser_icon="firefox" ;;
        *chrome*) browser_name="Chrome"; browser_icon="google-chrome" ;;
    esac

    mkdir -p "$DESKTOP_DIR" "$AUTOSTART_DIR" /root/.config /usr/share/backgrounds

    download_wallpaper
    write_xfconf_desktop_defaults

    if [ -n "$browser_bin" ]; then
        cat > "${INSTALL_ROOT}/octop-browser.desktop" << BROWSER_EOF
[Desktop Entry]
Type=Application
Name=${browser_name}
GenericName=Web Browser
Exec=${browser_bin} --no-sandbox --disable-dev-shm-usage --no-first-run --no-default-browser-check %U
Icon=${browser_icon}
Terminal=false
Categories=Network;WebBrowser;
MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
StartupNotify=true
BROWSER_EOF
        chmod 0644 "${INSTALL_ROOT}/octop-browser.desktop"
        ln -sf "${INSTALL_ROOT}/octop-browser.desktop" "${DESKTOP_DIR}/browser.desktop"
    fi

    if command -v xfce4-terminal >/dev/null 2>&1; then
        cat > "${DESKTOP_DIR}/terminal.desktop" << 'TERM_EOF'
[Desktop Entry]
Type=Application
Name=Terminal
Exec=xfce4-terminal
Icon=utilities-terminal
Terminal=false
TERM_EOF
        chmod 0755 "${DESKTOP_DIR}/terminal.desktop"
    fi

    if command -v thunar >/dev/null 2>&1; then
        cat > "${DESKTOP_DIR}/files.desktop" << 'FILES_EOF'
[Desktop Entry]
Type=Application
Name=File Manager
Exec=thunar
Icon=system-file-manager
Terminal=false
FILES_EOF
        chmod 0755 "${DESKTOP_DIR}/files.desktop"
    fi

    if command -v mousepad >/dev/null 2>&1; then
        cat > "${DESKTOP_DIR}/editor.desktop" << 'EDIT_EOF'
[Desktop Entry]
Type=Application
Name=Text Editor
Exec=mousepad
Icon=accessories-text-editor
Terminal=false
EDIT_EOF
        chmod 0755 "${DESKTOP_DIR}/editor.desktop"
    fi

    if [ -f "${INSTALL_ROOT}/octop-browser.desktop" ]; then
        cat > /root/.config/mimeapps.list << 'MIME_EOF'
[Default Applications]
x-scheme-handler/http=octop-browser.desktop
x-scheme-handler/https=octop-browser.desktop
text/html=octop-browser.desktop
MIME_EOF
    fi

    [ -f /etc/xdg/autostart/xfce-polkit.desktop ] && \
        printf '[Desktop Entry]\nType=Application\nName=XFCE PolicyKit Agent (disabled)\nHidden=true\n' \
            > "${AUTOSTART_DIR}/xfce-polkit.desktop"

    cat > "$TRUST_ICONS_HELPER" << 'TRUST_EOF'
#!/bin/sh
command -v gio >/dev/null 2>&1 || exit 0
for f in /root/Desktop/*.desktop; do
    [ -f "$f" ] || continue
    chmod +x "$f" 2>/dev/null || true
    gio set "$f" metadata::trusted true 2>/dev/null || true
done
command -v xfdesktop >/dev/null 2>&1 && xfdesktop --reload >/dev/null 2>&1 || true
TRUST_EOF
    chmod +x "$TRUST_ICONS_HELPER"

    cat > "${AUTOSTART_DIR}/octop-trust-icons.desktop" << TRUST_AUTO_EOF
[Desktop Entry]
Type=Application
Name=Trust Desktop Launchers
Exec=sh -c "sleep 3 && ${TRUST_ICONS_HELPER}"
TRUST_AUTO_EOF

    if command -v fcitx5 >/dev/null 2>&1; then
        mkdir -p /root/.config/fcitx5/conf
        cat > /root/.config/fcitx5/profile << 'FCITX_PROFILE'
[Groups/0]
Name=Default
Default Layout=us
DefaultIM=pinyin

[Groups/0/Items/0]
Name=keyboard-us
Layout=

[Groups/0/Items/1]
Name=pinyin
Layout=

[GroupOrder]
0=Default
FCITX_PROFILE
        cat > "${AUTOSTART_DIR}/fcitx5.desktop" << 'FCITX_AUTO_EOF'
[Desktop Entry]
Type=Application
Name=Fcitx5
Exec=fcitx5 -d
FCITX_AUTO_EOF
    fi
}

write_runtime_scripts() {
    mkdir -p "$INSTALL_ROOT" "$CONF_DIR" "$DESKTOP_STATE_DIR"

    cat > "$OPENBOX_XML" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?><openbox_config><desktops><number>1</number></desktops></openbox_config>
EOF

    cat > "$START_SESSION_SH" << SCRIPT_EOF
#!/bin/bash
export DISPLAY=${DISPLAY_NUM} HOME=/root
export LANG=zh_CN.UTF-8 LC_ALL=zh_CN.UTF-8
export XDG_RUNTIME_DIR=/tmp/runtime-octop-desktop
mkdir -p "\$XDG_RUNTIME_DIR"; chmod 700 "\$XDG_RUNTIME_DIR"
for i in \$(seq 1 100); do xdpyinfo -display ${DISPLAY_NUM} >/dev/null 2>&1 && break; sleep 0.3; done
eval "\$(dbus-launch --sh-syntax)"
cat > /tmp/octop-desktop-dbus-env << ENVEOF
export DBUS_SESSION_BUS_ADDRESS="\$DBUS_SESSION_BUS_ADDRESS"
export DBUS_SESSION_BUS_PID="\$DBUS_SESSION_BUS_PID"
ENVEOF
chmod 644 /tmp/octop-desktop-dbus-env
wait "\$DBUS_SESSION_BUS_PID" 2>/dev/null || sleep infinity
SCRIPT_EOF
    chmod +x "$START_SESSION_SH"

    cat > "$APPLY_WALLPAPER_SH" << 'APPLY_EOF'
#!/bin/bash
set -euo pipefail
export DISPLAY="${DISPLAY:-:99}"
export HOME="${HOME:-/root}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/root/.config}"
[ -f /tmp/octop-desktop-dbus-env ] && source /tmp/octop-desktop-dbus-env || true

WALLPAPER="/usr/share/backgrounds/octop-desktop-wallpaper.png"
[ -f "$WALLPAPER" ] || WALLPAPER="/usr/share/backgrounds/octop-desktop-wallpaper.svg"
[ -f "$WALLPAPER" ] || exit 0
command -v xfconf-query >/dev/null 2>&1 || exit 0

pick_monitor() {
    local m
    m=$(xrandr 2>/dev/null | awk '/ connected/{print $1; exit}')
    [ -n "$m" ] && { echo "$m"; return; }
    echo "VNC-0"
}

apply_to_monitor() {
    local mon="$1" ws
    for ws in 0 1 2 3; do
        xfconf-query -c xfce4-desktop \
            -p "/backdrop/screen0/monitor${mon}/workspace${ws}/last-image" \
            --create -t string -s "$WALLPAPER" 2>/dev/null || true
        xfconf-query -c xfce4-desktop \
            -p "/backdrop/screen0/monitor${mon}/workspace${ws}/image-style" \
            --create -t int -s 5 2>/dev/null || true
        xfconf-query -c xfce4-desktop \
            -p "/backdrop/screen0/monitor${mon}/workspace${ws}/color-style" \
            --create -t int -s 0 2>/dev/null || true
    done
}

MON=$(pick_monitor)
for i in $(seq 1 30); do
    xfconf-query -c xfce4-desktop -p /backdrop --create -t empty 2>/dev/null && break
    sleep 0.5
done
apply_to_monitor "$MON"
[ "$MON" != "VNC-0" ] && apply_to_monitor "VNC-0"
xfdesktop --display="$DISPLAY" --reload 2>/dev/null || true
APPLY_EOF
    chmod +x "$APPLY_WALLPAPER_SH"

    cat > "$START_OPENBOX_SH" << 'SCRIPT_EOF'
#!/bin/bash
export DISPLAY=:99 HOME=/root XDG_RUNTIME_DIR=/tmp/runtime-octop-desktop
export XDG_CONFIG_HOME=/root/.config XDG_DATA_HOME=/root/.local/share XDG_CURRENT_DESKTOP="XFCE"
export LANG=zh_CN.UTF-8 LC_ALL=zh_CN.UTF-8 LANGUAGE=zh_CN:zh
mkdir -p "$XDG_RUNTIME_DIR" "$HOME/Desktop"; chmod 700 "$XDG_RUNTIME_DIR"
for i in $(seq 1 100); do xdpyinfo -display :99 >/dev/null 2>&1 && break; sleep 0.3; done
for i in $(seq 1 50); do
    [ -f /tmp/octop-desktop-dbus-env ] && { source /tmp/octop-desktop-dbus-env; [ -n "$DBUS_SESSION_BUS_ADDRESS" ] && break; }
    sleep 0.3
done
xset -display :99 s off s noblank s 0 0 2>/dev/null || true
xset -display :99 dpms 0 0 0 2>/dev/null || true
xset -display :99 -dpms 2>/dev/null || true
xfsettingsd --display=:99 --replace &>/dev/null &
command -v xfdesktop >/dev/null 2>&1 && xfdesktop --display=:99 &>/dev/null &
sleep 1
xfce4-panel --display=:99 &>/dev/null &
command -v fcitx5 >/dev/null 2>&1 && fcitx5 -d &>/dev/null &
(
    for i in $(seq 1 40); do
        pgrep -f "xfdesktop --display=:99" >/dev/null 2>&1 && break
        sleep 0.5
    done
    [ -x /opt/octop-desktop/apply-wallpaper.sh ] && /opt/octop-desktop/apply-wallpaper.sh
    if command -v xfconf-query >/dev/null 2>&1; then
        xfconf-query -c xfce4-desktop -p /desktop-icons/file-icons/show-trash --create -t bool -s true 2>/dev/null || true
        xfconf-query -c xfce4-desktop -p /desktop-icons/file-icons/show-home --create -t bool -s true 2>/dev/null || true
        xfconf-query -c xfce4-desktop -p /desktop-icons/file-icons/show-filesystem --create -t bool -s true 2>/dev/null || true
        xfconf-query -c xfce4-screensaver -p /screensaver/enabled --create -t bool -s false 2>/dev/null || true
        xfconf-query -c xfce4-screensaver -p /lock/enabled --create -t bool -s false 2>/dev/null || true
        xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/dpms-enabled --create -t bool -s false 2>/dev/null || true
        xset -display :99 s off s noblank s 0 0 2>/dev/null || true
        xset -display :99 -dpms 2>/dev/null || true
    fi
    [ -x /opt/octop-desktop/trust-desktop-icons.sh ] && /opt/octop-desktop/trust-desktop-icons.sh
) &>/dev/null &
exec openbox --config-file /opt/octop-desktop/openbox.xml
SCRIPT_EOF
    chmod +x "$START_OPENBOX_SH"
}

write_systemd_units() {
    local xvnc_bin="$1"
    local vnc_password="${VNC_PASSWORD:-octop-desktop}"
    local vncpasswd_cmd
    vncpasswd_cmd=$(detect_vncpasswd_bin) || fail "vncpasswd not found"

    echo "$vnc_password" > "${CONF_DIR}/vnc_password"
    chmod 600 "${CONF_DIR}/vnc_password"
    printf '%s' "$vnc_password" | "$vncpasswd_cmd" -f > "${CONF_DIR}/rfbauth"
    chmod 600 "${CONF_DIR}/rfbauth"
    echo "$SCRIPT_VERSION" > "${CONF_DIR}/version"

    cat > "/etc/systemd/system/${SVC_XVNC}.service" << UNIT_EOF
[Unit]
Description=Octop virtual desktop - Xvnc
After=network.target

[Service]
Type=simple
ExecStartPre=-/bin/rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
ExecStart=${xvnc_bin} :99 -depth 24 -geometry ${GEOMETRY} -rfbport ${VNC_PORT} -localhost yes -AlwaysShared -maxclients 256 -SecurityTypes VncAuth -rfbauth ${CONF_DIR}/rfbauth
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT_EOF

    cat > "/etc/systemd/system/${SVC_SESSION}.service" << UNIT_EOF
[Unit]
Description=Octop virtual desktop - D-Bus session
After=${SVC_XVNC}.service
Wants=${SVC_XVNC}.service

[Service]
Type=simple
ExecStart=${START_SESSION_SH}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT_EOF

    cat > "/etc/systemd/system/${SVC_OPENBOX}.service" << UNIT_EOF
[Unit]
Description=Octop virtual desktop - Openbox
After=${SVC_XVNC}.service ${SVC_SESSION}.service
Wants=${SVC_XVNC}.service

[Service]
Type=simple
ExecStart=${START_OPENBOX_SH}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT_EOF
}

write_desktop_env() {
    mkdir -p "$DESKTOP_STATE_DIR"
    cat > "$DESKTOP_ENV" << EOF
export DISPLAY=${DISPLAY_NUM}
export OCTOP_DESKTOP_DISPLAY=${DISPLAY_NUM}
export OCTOP_DESKTOP_GEOMETRY=${GEOMETRY}
EOF
    chmod 644 "$DESKTOP_ENV"
}

start_services() {
    if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
        systemctl daemon-reload
        systemctl enable "$SVC_XVNC" "$SVC_SESSION" "$SVC_OPENBOX"
        systemctl restart "$SVC_XVNC" "$SVC_SESSION" "$SVC_OPENBOX"
        sleep 2
        systemctl is-active --quiet "$SVC_XVNC" || fail "octop-desktop-xvnc not active"
        sleep 4
        DISPLAY="${DISPLAY_NUM}" HOME=/root "${APPLY_WALLPAPER_SH}" 2>/dev/null || true
        return
    fi

    # Fallback for containers / environments without systemd.
    mkdir -p "${DESKTOP_STATE_DIR}/pids"
    pkill -f "Xtigervnc :99" 2>/dev/null || true
    pkill -f "Xvnc :99" 2>/dev/null || true
    pkill -f "xfce4-panel" 2>/dev/null || true
    pkill -f "xfdesktop" 2>/dev/null || true
    pkill -f "openbox --config-file ${OPENBOX_XML}" 2>/dev/null || true
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

    local xvnc_bin
    xvnc_bin=$(detect_xvnc_bin) || fail "Xvnc not found"
    local vnc_password="${VNC_PASSWORD:-octop-desktop}"
    local vncpasswd_cmd
    vncpasswd_cmd=$(detect_vncpasswd_bin) || fail "vncpasswd not found"
    printf '%s' "$vnc_password" | "$vncpasswd_cmd" -f > "${CONF_DIR}/rfbauth"
    chmod 600 "${CONF_DIR}/rfbauth"

  nohup "$xvnc_bin" :99 -depth 24 -geometry "${GEOMETRY}" -rfbport "${VNC_PORT}" \
        -localhost yes -AlwaysShared -maxclients 256 -SecurityTypes VncAuth -rfbauth "${CONF_DIR}/rfbauth" \
        > "${DESKTOP_STATE_DIR}/xvnc.log" 2>&1 &
    echo $! > "${DESKTOP_STATE_DIR}/pids/xvnc.pid"
    sleep 1

    nohup "$START_SESSION_SH" > "${DESKTOP_STATE_DIR}/session.log" 2>&1 &
    echo $! > "${DESKTOP_STATE_DIR}/pids/session.pid"
    sleep 1

    nohup "$START_OPENBOX_SH" > "${DESKTOP_STATE_DIR}/openbox.log" 2>&1 &
    echo $! > "${DESKTOP_STATE_DIR}/pids/openbox.pid"
    sleep 1

    DISPLAY="${DISPLAY_NUM}" xdpyinfo -display "${DISPLAY_NUM}" >/dev/null 2>&1 \
        || fail "virtual desktop failed to start (no systemd)"

    sleep 4
    DISPLAY="${DISPLAY_NUM}" HOME=/root "${APPLY_WALLPAPER_SH}" 2>/dev/null || true
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --geometry) GEOMETRY="$2"; shift 2 ;;
            --password) VNC_PASSWORD="$2"; shift 2 ;;
            --wallpaper-url) WALLPAPER_URL="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
}

main() {
    parse_args "$@"
    [ "$(id -u)" = "0" ] || fail "must run as root"
    local family xvnc_bin
    family=$(detect_distro)
    [ "$family" != unknown ] || fail "unsupported distro"

    install_packages "$family"
    configure_locale_and_fonts
    write_runtime_scripts
    configure_desktop_environment
    resize_script="$(cd "$(dirname "$0")" && pwd)/resize.sh"
    [ -f "$resize_script" ] && chmod +x "$resize_script"
    xvnc_bin=$(detect_xvnc_bin) || fail "Xvnc not found"
    write_systemd_units "$xvnc_bin"
    write_desktop_env
    start_services

    echo "{\"installed\": true, \"version\": \"${SCRIPT_VERSION}\", \"display\": \"${DISPLAY_NUM}\"}"
}

main "$@"
