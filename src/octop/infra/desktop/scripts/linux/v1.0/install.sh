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
set -euo pipefail

SCRIPT_VERSION="v1.0"
# Python interpreter the desktop deps are installed into (the Octop venv), used to
# pick matching pythonX.Y-dev headers. Falls back to system `python3`.
TARGET_PYTHON="python3"
INSTALL_ROOT="/opt/octop-desktop"
CONF_DIR="/etc/octop-desktop"
DISPLAY_NUM=":99"
GEOMETRY="${GEOMETRY:-1920x1080}"
# Absolute pixel size for xfdesktop icons (not scaled with GTK window scaling).
DESKTOP_ICON_SIZE="${DESKTOP_ICON_SIZE:-48}"
WALLPAPER_URL="${WALLPAPER_URL:-}"
VNC_PORT=5900
VNC_DPI="${VNC_DPI:-96}"
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
APPLY_ICONS_SH="${INSTALL_ROOT}/apply-icon-size.sh"

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

# TigerVNC 1.8 (EL7): `-localhost` is a boolean flag (no value).
# Modern TigerVNC: requires `-localhost yes|no`.
detect_xvnc_localhost_args() {
    local bin="$1"
    local help
    help="$("$bin" -help 2>&1 || true)"
    if echo "$help" | grep -qE 'localhost[[:space:]]+-[[:space:]]+Only allow'; then
        echo "-localhost"
    else
        echo "-localhost yes"
    fi
}

# Minor version (X.Y) of the Python interpreter desktop deps build against.
# Must match the venv Python (e.g. 3.12), not the system default `python3`,
# otherwise the wrong -dev headers are installed and evdev fails with
# "Python.h: No such file or directory".
detect_python_minor() {
    local py="${1:-python3}"
    "$py" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true
}

install_python_build_deps() {
    local family="$1"
    local target_py="${TARGET_PYTHON:-python3}"
    if [ "$family" = debian ]; then
        DEBIAN_FRONTEND=noninteractive apt-get update -qq || fail "apt-get update failed"
        local py_dev="python3-dev"
        local py_minor
        py_minor=$(detect_python_minor "$target_py")
        if [ -n "$py_minor" ] && apt-cache show "python${py_minor}-dev" >/dev/null 2>&1; then
            py_dev="python${py_minor}-dev"
        fi
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
            build-essential "$py_dev" \
            || fail "apt install failed (python build deps): $py_dev"
    elif [ "$family" = rhel ]; then
        local pkg=dnf
        command -v dnf >/dev/null 2>&1 || pkg=yum
        $pkg install -y gcc python3-devel \
            || fail "yum/dnf install failed (python build deps)"
    else
        fail "unsupported distro"
    fi
}

install_packages() {
    local family="$1"
    install_python_build_deps "$family"
    if [ "$family" = debian ]; then
        DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
            tigervnc-standalone-server tigervnc-tools x11-xserver-utils x11-utils openbox \
            dbus dbus-x11 xdotool xauth imagemagick librsvg2-bin \
            xfce4-panel xfce4-terminal xfce4-settings xfdesktop4 thunar mousepad \
            xfce4-appfinder \
            adwaita-icon-theme hicolor-icon-theme librsvg2-common \
            fcitx5 fcitx5-chinese-addons fcitx5-frontend-gtk3 \
            fonts-wqy-zenhei locales xclip xsel autocutsel xdg-utils libglib2.0-bin wget curl \
            || fail "apt install failed"
        # Adwaita ships SVG icons; without the gdk-pixbuf SVG loader they render as tiny stubs.
        if command -v gdk-pixbuf-query-loaders >/dev/null 2>&1; then
            gdk-pixbuf-query-loaders --update-cache >/dev/null 2>&1 || true
        fi
        if command -v gtk-update-icon-cache >/dev/null 2>&1; then
            gtk-update-icon-cache -f /usr/share/icons/Adwaita >/dev/null 2>&1 || true
            gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
        fi
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
            adwaita-icon-theme hicolor-icon-theme librsvg2 \
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
    mkdir -p /root/.config/xfce4/xfconf/xfce-perchannel-xml
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
    <property name="style" type="int" value="2"/>
    <property name="icon-size" type="int" value="${DESKTOP_ICON_SIZE}"/>
    <property name="file-icons" type="empty">
      <property name="show-trash" type="bool" value="true"/>
      <property name="show-home" type="bool" value="true"/>
      <property name="show-filesystem" type="bool" value="true"/>
    </property>
  </property>
</channel>
EOF
    chmod 0644 "$XFCONF_DESKTOP_XML"

    # Static xsettings so icon theme/DPI apply even before xfconf-query works.
    cat > /root/.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml << EOF
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xsettings" version="1.0">
  <property name="Net" type="empty">
    <property name="ThemeName" type="string" value="Adwaita"/>
    <property name="IconThemeName" type="string" value="Adwaita"/>
  </property>
  <property name="Xft" type="empty">
    <property name="DPI" type="int" value="${VNC_DPI}"/>
  </property>
  <property name="Gdk" type="empty">
    <property name="WindowScalingFactor" type="int" value="1"/>
  </property>
</channel>
EOF
    chmod 0644 /root/.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml
}

# Prefer real theme PNGs/SVGs rendered to PNG. Never invent letter tiles.
materialize_launcher_icons() {
    local icon_dir="${INSTALL_ROOT}/icons"
    local size="${DESKTOP_ICON_SIZE}"
    mkdir -p "$icon_dir"

    _render_icon() {
        local name="$1" dest="$2" src=""
        for src in \
            "/usr/share/icons/hicolor/${size}x${size}/apps/${name}.png" \
            "/usr/share/icons/hicolor/48x48/apps/${name}.png" \
            "/usr/share/icons/hicolor/64x64/apps/${name}.png" \
            "/usr/share/icons/Adwaita/${size}x${size}/apps/${name}.png" \
            "/usr/share/icons/Adwaita/48x48/apps/${name}.png" \
            "/usr/share/icons/Adwaita/scalable/apps/${name}.svg" \
            "/usr/share/icons/Adwaita/scalable/places/${name}.svg" \
            "/usr/share/icons/Adwaita/scalable/devices/${name}.svg" \
            "/usr/share/icons/hicolor/scalable/apps/${name}.svg" \
            "/usr/share/pixmaps/${name}.png"; do
            [ -f "$src" ] || continue
            if [[ "$src" == *.svg ]]; then
                if command -v rsvg-convert >/dev/null 2>&1; then
                    rsvg-convert -w "$size" -h "$size" -o "$dest" "$src" 2>/dev/null \
                        && [ -s "$dest" ] && return 0
                fi
                if command -v convert >/dev/null 2>&1; then
                    convert -background none -resize "${size}x${size}" "$src" "$dest" 2>/dev/null \
                        && [ -s "$dest" ] && return 0
                fi
            else
                if command -v convert >/dev/null 2>&1; then
                    convert "$src" -resize "${size}x${size}" "$dest" 2>/dev/null \
                        && [ -s "$dest" ] && return 0
                fi
                cp -f "$src" "$dest" 2>/dev/null && [ -s "$dest" ] && return 0
            fi
        done
        return 1
    }

    _render_icon utilities-terminal "${icon_dir}/terminal.png" || true
    _render_icon org.xfce.terminal "${icon_dir}/terminal.png" || true
    _render_icon system-file-manager "${icon_dir}/files.png" || true
    _render_icon org.xfce.thunar "${icon_dir}/files.png" || true
    _render_icon accessories-text-editor "${icon_dir}/editor.png" || true
    _render_icon org.xfce.mousepad "${icon_dir}/editor.png" || true
    _render_icon web-browser "${icon_dir}/browser.png" || true
    _render_icon chromium "${icon_dir}/chromium.png" || true
    _render_icon firefox "${icon_dir}/firefox.png" || true
    _render_icon google-chrome "${icon_dir}/chrome.png" || true
}

_icon_or_theme() {
    local png="$1" theme_name="$2"
    if [ -s "$png" ]; then
        echo "$png"
    else
        echo "$theme_name"
    fi
}

install_start_menu_logo() {
    # Copy the Octop PWA logo shipped next to this install.sh into the system
    # install root. Uninstall removes /opt/octop-desktop; reinstall restores it.
    mkdir -p "${INSTALL_ROOT}/icons"
    local bundled_logo script_dir
    script_dir="$(cd "$(dirname "$0")" && pwd)"
    bundled_logo="${script_dir}/start-menu.png"
    if [ ! -f "$bundled_logo" ] || [ ! -s "$bundled_logo" ]; then
        echo "start-menu logo missing next to install.sh (${bundled_logo})" >&2
        return 1
    fi
    if command -v convert >/dev/null 2>&1; then
        convert "$bundled_logo" -resize 48x48 \
            "${INSTALL_ROOT}/icons/start-menu.png" 2>/dev/null \
            || cp -f "$bundled_logo" "${INSTALL_ROOT}/icons/start-menu.png"
    else
        cp -f "$bundled_logo" "${INSTALL_ROOT}/icons/start-menu.png"
    fi
    chmod 0644 "${INSTALL_ROOT}/icons/start-menu.png"
    mkdir -p /usr/share/icons/hicolor/48x48/apps
    cp -f "${INSTALL_ROOT}/icons/start-menu.png" \
        /usr/share/icons/hicolor/48x48/apps/octop-start-menu.png
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
    fi
    echo "installed start-menu logo -> ${INSTALL_ROOT}/icons/start-menu.png"
}

write_default_panel_layout() {
    # Seed a bottom panel. Use an appfinder *launcher* as the start button —
    # applicationsmenu/whiskermenu often fail to load on minimal headless installs.
    # ensure-panel.sh re-applies this layout on every session start (xfce can
    # rewrite XML on exit and drop a broken plugin-1 slot).
    mkdir -p "$INSTALL_ROOT/icons" /root/.config/xfce4/panel/launcher-1 \
        /root/.config/xfce4/xfconf/xfce-perchannel-xml

    install_start_menu_logo || true

    cat > "$INSTALL_ROOT/ensure-panel.sh" << 'ENSURE_PANEL_EOF'
#!/bin/bash
# Rewrite the Octop default panel (appfinder launcher + tasklist + clock).
#
# XFCE keeps panel state in xfconfd's memory. Overwriting xfce4-panel.xml while
# xfconfd is alive is ignored; killing the panel gracefully can also flush a
# broken in-memory layout back to disk (which is why the start button vanishes
# after a service restart). Always: SIGKILL panel → kill xfconfd → write files
# → clear cache → start panel.
set -euo pipefail
export HOME=/root
export XDG_CONFIG_HOME=/root/.config
export XDG_DATA_HOME=/root/.local/share
export DISPLAY="${DISPLAY:-:99}"
NO_START=false
if [ "${1:-}" = "--no-start" ]; then
    NO_START=true
fi

mkdir -p /root/.config/xfce4/panel/launcher-1 \
    /root/.config/xfce4/xfconf/xfce-perchannel-xml \
    /opt/octop-desktop/panel

write_panel_files() {
    local start_icon="/opt/octop-desktop/icons/start-menu.png"
    if [ ! -s "$start_icon" ]; then
        if [ -e /usr/share/icons/hicolor/48x48/apps/octop-start-menu.png ]; then
            start_icon="/usr/share/icons/hicolor/48x48/apps/octop-start-menu.png"
        else
            start_icon="system-search"
        fi
    fi

    cat > /root/.config/xfce4/panel/launcher-1/appfinder.desktop << LAUNCHER_EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Applications
Name[zh_CN]=应用程序
Comment=Open the application finder
Comment[zh_CN]=打开应用程序菜单
Exec=xfce4-appfinder
Icon=${start_icon}
Terminal=false
Categories=Utility;X-XFCE;X-Xfce-Toplevel;
StartupNotify=true
LAUNCHER_EOF
    chmod 0644 /root/.config/xfce4/panel/launcher-1/appfinder.desktop

    # Canonical copy under /opt survives user config wipes / bad xfconf flushes.
    cat > /opt/octop-desktop/panel/xfce4-panel.xml << 'PANEL_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfce4-panel" version="1.0">
  <property name="configver" type="int" value="2"/>
  <property name="panels" type="array">
    <value type="int" value="1"/>
    <property name="panel-1" type="empty">
      <property name="position" type="string" value="p=8;x=0;y=0"/>
      <property name="length" type="uint" value="100"/>
      <property name="position-locked" type="bool" value="true"/>
      <property name="size" type="uint" value="36"/>
      <property name="plugin-ids" type="array">
        <value type="int" value="1"/>
        <value type="int" value="2"/>
        <value type="int" value="3"/>
        <value type="int" value="4"/>
        <value type="int" value="5"/>
      </property>
    </property>
  </property>
  <property name="plugins" type="empty">
    <property name="plugin-1" type="string" value="launcher">
      <property name="items" type="array">
        <value type="string" value="appfinder.desktop"/>
      </property>
    </property>
    <property name="plugin-2" type="string" value="tasklist"/>
    <property name="plugin-3" type="string" value="separator">
      <property name="expand" type="bool" value="true"/>
      <property name="style" type="uint" value="0"/>
    </property>
    <property name="plugin-4" type="string" value="systray"/>
    <property name="plugin-5" type="string" value="clock"/>
  </property>
</channel>
PANEL_EOF
    cp -f /opt/octop-desktop/panel/xfce4-panel.xml \
        /root/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml
    chmod 0644 /root/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml \
        /opt/octop-desktop/panel/xfce4-panel.xml
}

if [ "$NO_START" = true ]; then
    write_panel_files
    echo "ensure-panel seeded"
    exit 0
fi

# 1) Hard-kill panel so it cannot flush a broken layout back to xfconf.
pkill -9 -x xfce4-panel >/dev/null 2>&1 || true
sleep 0.2
# 2) Drop in-memory xfconf channel so the next start reloads from our XML.
pkill -x xfconfd >/dev/null 2>&1 || true
sleep 0.2
# 3) Write canonical files while xfconfd is down.
write_panel_files
rm -rf /root/.cache/xfce4/xfconf 2>/dev/null || true
# 4) If xfsettingsd already respawned xfconfd, kill again after the write.
pkill -x xfconfd >/dev/null 2>&1 || true
sleep 0.2
# Re-copy in case a racing xfconfd rewrote the channel file from an empty bus.
cp -f /opt/octop-desktop/panel/xfce4-panel.xml \
    /root/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml
rm -rf /root/.cache/xfce4/xfconf 2>/dev/null || true

if [ -f /tmp/octop-desktop-dbus-env ]; then
    # shellcheck disable=SC1091
    source /tmp/octop-desktop-dbus-env || true
fi

if command -v xfce4-panel >/dev/null 2>&1; then
    nohup xfce4-panel --display="$DISPLAY" >/dev/null 2>&1 &
    sleep 1
    if ! pgrep -x xfce4-panel >/dev/null 2>&1; then
        nohup xfce4-panel --display="$DISPLAY" >/dev/null 2>&1 &
        sleep 1
    fi
fi
echo "ensure-panel ok"
ENSURE_PANEL_EOF
    chmod +x "$INSTALL_ROOT/ensure-panel.sh"
    # Seed files only during install (DISPLAY may not be up yet).
    /bin/bash "$INSTALL_ROOT/ensure-panel.sh" --no-start >/dev/null 2>&1 || true
}

download_wallpaper() {
    # Install the Octop wallpaper shipped next to this script (packaged in the
    # wheel under infra/desktop/scripts/linux/v1.0/wallpaper.png).
    mkdir -p /usr/share/backgrounds "${INSTALL_ROOT}"
    local ok=false
    local bundled script_dir
    script_dir="$(cd "$(dirname "$0")" && pwd)"
    bundled="${script_dir}/wallpaper.png"

    if [ -f "$bundled" ] && [ -s "$bundled" ]; then
        # Keep a canonical copy under /opt; xfdesktop reads from /usr/share.
        cp -f "$bundled" "${INSTALL_ROOT}/wallpaper.png"
        # Shrink to 1080p when possible, but never center-crop — branding sits
        # in the lower-right corner of the shipped asset.
        if command -v convert >/dev/null 2>&1; then
            convert "$bundled" -resize '1920x1080>' \
                "$WALLPAPER_PNG" 2>/dev/null \
                && [ -s "$WALLPAPER_PNG" ] && ok=true
        fi
        if [ "$ok" = false ]; then
            cp -f "$bundled" "$WALLPAPER_PNG" 2>/dev/null \
                && [ -s "$WALLPAPER_PNG" ] && ok=true
        fi
        if [ "$ok" = true ]; then
            echo "installed bundled wallpaper -> $WALLPAPER_PNG"
        fi
    else
        echo "bundled wallpaper missing next to install.sh (${bundled})" >&2
    fi

    # Optional override only when the packaged asset is unavailable.
    if [ "$ok" = false ] && [ -n "${WALLPAPER_URL:-}" ]; then
        if command -v wget >/dev/null 2>&1; then
            wget --timeout=20 --tries=2 -qO "$WALLPAPER_PNG" "$WALLPAPER_URL" 2>/dev/null \
                && [ -s "$WALLPAPER_PNG" ] && ok=true
        fi
        if [ "$ok" = false ] && command -v curl >/dev/null 2>&1; then
            curl -fsSL --connect-timeout 20 --max-time 60 "$WALLPAPER_URL" -o "$WALLPAPER_PNG" 2>/dev/null \
                && [ -s "$WALLPAPER_PNG" ] && ok=true
        fi
    fi

    if [ "$ok" = false ]; then
        cat > "$WALLPAPER_FILE" << 'WALL_EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"><rect width="100%" height="100%" fill="#000000"/></svg>
WALL_EOF
        if command -v convert >/dev/null 2>&1; then
            convert "$WALLPAPER_FILE" -resize 1920x1080! "$WALLPAPER_PNG" 2>/dev/null || true
        fi
        echo "wallpaper fallback: solid black" >&2
    fi
    [ -s "$WALLPAPER_PNG" ] && chmod 0644 "$WALLPAPER_PNG" || true
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

    # Drop stale icon layout / cache / bad generated letter-tile icons from earlier installs.
    rm -rf /root/.config/xfce4/desktop /root/.cache/xfce4/xfdesktop 2>/dev/null || true
    rm -rf "${INSTALL_ROOT}/icons" 2>/dev/null || true

    download_wallpaper
    write_xfconf_desktop_defaults
    materialize_launcher_icons

    if [ -n "$browser_bin" ]; then
        local browser_icon_path
        browser_icon_path="$(_icon_or_theme "${INSTALL_ROOT}/icons/browser.png" "$browser_icon")"
        case "$browser_bin" in
            *chromium*) browser_icon_path="$(_icon_or_theme "${INSTALL_ROOT}/icons/chromium.png" chromium)" ;;
            *firefox*) browser_icon_path="$(_icon_or_theme "${INSTALL_ROOT}/icons/firefox.png" firefox)" ;;
            *chrome*) browser_icon_path="$(_icon_or_theme "${INSTALL_ROOT}/icons/chrome.png" google-chrome)" ;;
        esac
        cat > "${INSTALL_ROOT}/octop-browser.desktop" << BROWSER_EOF
[Desktop Entry]
Type=Application
Name=${browser_name}
GenericName=Web Browser
Exec=${browser_bin} --no-sandbox --disable-dev-shm-usage --no-first-run --no-default-browser-check %U
Icon=${browser_icon_path}
Terminal=false
Categories=Network;WebBrowser;
MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
StartupNotify=true
BROWSER_EOF
        chmod 0644 "${INSTALL_ROOT}/octop-browser.desktop"
        # Place a real .desktop file on the Desktop (matching terminal/files/editor)
        # instead of a symlink; xfdesktop renders symlinked launchers with a
        # "shortcut" link emblem, which makes the browser look inconsistent.
        # Remove any stale symlink from a previous install first so `cp` does not
        # write through it and re-create the link.
        rm -f "${DESKTOP_DIR}/browser.desktop"
        cp -f "${INSTALL_ROOT}/octop-browser.desktop" "${DESKTOP_DIR}/browser.desktop"
        chmod 0755 "${DESKTOP_DIR}/browser.desktop"
    fi

    if command -v xfce4-terminal >/dev/null 2>&1; then
        local term_icon
        term_icon="$(_icon_or_theme "${INSTALL_ROOT}/icons/terminal.png" utilities-terminal)"
        cat > "${DESKTOP_DIR}/terminal.desktop" << TERM_EOF
[Desktop Entry]
Type=Application
Name=Terminal
Exec=xfce4-terminal
Icon=${term_icon}
Terminal=false
TERM_EOF
        chmod 0755 "${DESKTOP_DIR}/terminal.desktop"
    fi

    if command -v thunar >/dev/null 2>&1; then
        local files_icon
        files_icon="$(_icon_or_theme "${INSTALL_ROOT}/icons/files.png" system-file-manager)"
        cat > "${DESKTOP_DIR}/files.desktop" << FILES_EOF
[Desktop Entry]
Type=Application
Name=File Manager
Exec=thunar
Icon=${files_icon}
Terminal=false
FILES_EOF
        chmod 0755 "${DESKTOP_DIR}/files.desktop"
    fi

    if command -v mousepad >/dev/null 2>&1; then
        local editor_icon
        editor_icon="$(_icon_or_theme "${INSTALL_ROOT}/icons/editor.png" accessories-text-editor)"
        cat > "${DESKTOP_DIR}/editor.desktop" << EDIT_EOF
[Desktop Entry]
Type=Application
Name=Text Editor
Exec=mousepad
Icon=${editor_icon}
Terminal=false
EDIT_EOF
        chmod 0755 "${DESKTOP_DIR}/editor.desktop"
    fi

    write_default_panel_layout

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
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config>
  <desktops><number>1</number></desktops>
  <keyboard>
    <!-- Match the panel start button: open xfce4-appfinder -->
    <keybind key="A-F1">
      <action name="Execute"><command>xfce4-appfinder</command></action>
    </keybind>
    <keybind key="Super_L">
      <action name="Execute"><command>xfce4-appfinder</command></action>
    </keybind>
    <keybind key="Super_R">
      <action name="Execute"><command>xfce4-appfinder</command></action>
    </keybind>
    <!-- Close focused window (matches desktop shortcut "关闭窗口"). -->
    <keybind key="A-F4">
      <action name="Close"/>
    </keybind>
    <!-- Toggle show desktop (matches desktop shortcut "进入桌面"). -->
    <keybind key="C-A-D">
      <action name="ToggleShowDesktop"/>
    </keybind>
  </keyboard>
</openbox_config>
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
[ -f "$WALLPAPER" ] || WALLPAPER="/opt/octop-desktop/wallpaper.png"
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
# Older xfdesktop (EL7) may keep --reload in the foreground; never block install.
if command -v timeout >/dev/null 2>&1; then
    timeout 5 xfdesktop --display="$DISPLAY" --reload 2>/dev/null || true
else
    xfdesktop --display="$DISPLAY" --reload 2>/dev/null &
    sleep 1
fi
APPLY_EOF
    chmod +x "$APPLY_WALLPAPER_SH"

    cat > "$APPLY_ICONS_SH" << ICONS_EOF
#!/bin/bash
set -euo pipefail
LOG="${INSTALL_ROOT}/apply-icons.log"
exec >>"\$LOG" 2>&1
echo "---- \$(date -Is) apply-icon-size ----"

export DISPLAY="\${DISPLAY:-:99}"
export HOME="\${HOME:-/root}"
export XDG_CONFIG_HOME="\${XDG_CONFIG_HOME:-/root/.config}"

if [ ! -f /tmp/octop-desktop-dbus-env ]; then
    echo "missing /tmp/octop-desktop-dbus-env (desktop session not ready)"
    exit 1
fi
# shellcheck disable=SC1091
source /tmp/octop-desktop-dbus-env
if [ -z "\${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    echo "DBUS_SESSION_BUS_ADDRESS empty"
    exit 1
fi
echo "DISPLAY=\$DISPLAY DBUS=\$DBUS_SESSION_BUS_ADDRESS"

ICON_SIZE="${DESKTOP_ICON_SIZE}"
DPI="${VNC_DPI}"
command -v xfconf-query >/dev/null 2>&1 || { echo "xfconf-query missing"; exit 1; }

# Wait for xfconfd on the session bus.
ok=false
for _ in \$(seq 1 40); do
    if xfconf-query -c xfce4-desktop -l >/dev/null 2>&1; then
        ok=true
        break
    fi
    sleep 0.25
done
if [ "\$ok" != true ]; then
    echo "xfconfd not reachable on session bus"
    exit 1
fi

if [ -d /usr/share/icons/Adwaita ]; then
    xfconf-query -c xsettings -p /Net/IconThemeName --create -t string -s Adwaita
elif [ -d /usr/share/icons/hicolor ]; then
    xfconf-query -c xsettings -p /Net/IconThemeName --create -t string -s hicolor
fi

xfconf-query -c xsettings -p /Xft/DPI --create -t int -s "\$DPI"
xfconf-query -c xsettings -p /Gdk/WindowScalingFactor --create -t int -s 1

xfconf-query -c xfce4-desktop -p /desktop-icons/icon-size -r >/dev/null 2>&1 || true
xfconf-query -c xfce4-desktop -p /desktop-icons/icon-size --create -t int -s "\$ICON_SIZE"
xfconf-query -c xfce4-desktop -p /desktop-icons/style --create -t int -s 2
xfconf-query -c xfce4-desktop -p /desktop-icons/file-icons/show-trash --create -t bool -s true
xfconf-query -c xfce4-desktop -p /desktop-icons/file-icons/show-home --create -t bool -s true
xfconf-query -c xfce4-desktop -p /desktop-icons/file-icons/show-filesystem --create -t bool -s true

current="\$(xfconf-query -c xfce4-desktop -p /desktop-icons/icon-size)"
echo "icon-size=\$current theme=\$(xfconf-query -c xsettings -p /Net/IconThemeName) dpi=\$(xfconf-query -c xsettings -p /Xft/DPI)"
if [ "\$current" != "\$ICON_SIZE" ]; then
    echo "failed to set desktop icon-size (got: \$current, want: \$ICON_SIZE)"
    exit 1
fi

if command -v xfdesktop >/dev/null 2>&1; then
    if command -v timeout >/dev/null 2>&1; then
        timeout 5 xfdesktop --display="\$DISPLAY" --reload >/dev/null 2>&1 || true
    else
        xfdesktop --display="\$DISPLAY" --reload >/dev/null 2>&1 &
        sleep 1
    fi
fi

# Do NOT call ensure-panel here: rewriting the panel while xfconfd is live
# races and can drop the start-button launcher after service restarts.
# start-openbox.sh owns panel layout; we only revive a dead panel process.
if command -v xfce4-panel >/dev/null 2>&1; then
    if ! pgrep -x xfce4-panel >/dev/null 2>&1; then
        nohup xfce4-panel --display="\$DISPLAY" >/dev/null 2>&1 &
        sleep 1
    fi
fi
echo "apply-icon-size ok"
ICONS_EOF
    chmod +x "$APPLY_ICONS_SH"

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
sleep 0.5
command -v xfdesktop >/dev/null 2>&1 && xfdesktop --display=:99 &>/dev/null &
sleep 1
# Seed panel once after xfsettingsd is up. ensure-panel SIGKILLs the panel and
# restarts xfconfd so our XML wins over any stale in-memory channel.
if [ -x /opt/octop-desktop/ensure-panel.sh ]; then
    /opt/octop-desktop/ensure-panel.sh || true
else
    pkill -9 -x xfce4-panel >/dev/null 2>&1 || true
    sleep 0.2
    xfce4-panel --display=:99 &>/dev/null &
fi
command -v fcitx5 >/dev/null 2>&1 && fcitx5 -d &>/dev/null &
(
    # Wait for panel from the foreground ensure-panel; retry once if it died.
    for i in $(seq 1 20); do
        pgrep -x xfce4-panel >/dev/null 2>&1 && break
        sleep 0.5
    done
    if ! pgrep -x xfce4-panel >/dev/null 2>&1 && [ -x /opt/octop-desktop/ensure-panel.sh ]; then
        /opt/octop-desktop/ensure-panel.sh || true
    fi
    for i in $(seq 1 40); do
        pgrep -f "xfdesktop --display=:99" >/dev/null 2>&1 && break
        sleep 0.5
    done
    [ -x /opt/octop-desktop/apply-wallpaper.sh ] && /opt/octop-desktop/apply-wallpaper.sh
    [ -x /opt/octop-desktop/apply-icon-size.sh ] && /opt/octop-desktop/apply-icon-size.sh
    if command -v xfconf-query >/dev/null 2>&1; then
        # shellcheck disable=SC1091
        [ -f /tmp/octop-desktop-dbus-env ] && source /tmp/octop-desktop-dbus-env || true
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
    local localhost_args
    vncpasswd_cmd=$(detect_vncpasswd_bin) || fail "vncpasswd not found"
    localhost_args=$(detect_xvnc_localhost_args "$xvnc_bin")

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
ExecStart=${xvnc_bin} :99 -depth 24 -geometry ${GEOMETRY} -dpi ${VNC_DPI} -rfbport ${VNC_PORT} ${localhost_args} -AlwaysShared -maxclients 256 -SecurityTypes VncAuth -rfbauth ${CONF_DIR}/rfbauth
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

    for unit in "$SVC_XVNC" "$SVC_SESSION" "$SVC_OPENBOX"; do
        [ -f "/etc/systemd/system/${unit}.service" ] || fail "failed to write ${unit}.service"
    done
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
        systemctl enable "$SVC_XVNC" "$SVC_SESSION" "$SVC_OPENBOX" \
            || fail "systemctl enable failed"
        systemctl restart "$SVC_XVNC" "$SVC_SESSION" "$SVC_OPENBOX" \
            || fail "systemctl restart failed"
        sleep 2
        systemctl is-active --quiet "$SVC_XVNC" || fail "octop-desktop-xvnc not active"
        sleep 4
        # Wallpaper/icon helpers can hang on older xfdesktop; cap wait time.
        timeout 30 env DISPLAY="${DISPLAY_NUM}" HOME=/root "${APPLY_WALLPAPER_SH}" 2>/dev/null || true
        timeout 30 env DISPLAY="${DISPLAY_NUM}" HOME=/root "${APPLY_ICONS_SH}" 2>/dev/null || true
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
    local localhost_args
    vncpasswd_cmd=$(detect_vncpasswd_bin) || fail "vncpasswd not found"
    localhost_args=$(detect_xvnc_localhost_args "$xvnc_bin")
    printf '%s' "$vnc_password" | "$vncpasswd_cmd" -f > "${CONF_DIR}/rfbauth"
    chmod 600 "${CONF_DIR}/rfbauth"

    # shellcheck disable=SC2086
    nohup "$xvnc_bin" :99 -depth 24 -geometry "${GEOMETRY}" -dpi "${VNC_DPI}" -rfbport "${VNC_PORT}" \
        ${localhost_args} -AlwaysShared -maxclients 256 -SecurityTypes VncAuth -rfbauth "${CONF_DIR}/rfbauth" \
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
    DISPLAY="${DISPLAY_NUM}" HOME=/root "${APPLY_ICONS_SH}" 2>/dev/null || true
}

BUILD_DEPS_ONLY=0

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --geometry) GEOMETRY="$2"; shift 2 ;;
            --password) VNC_PASSWORD="$2"; shift 2 ;;
            --wallpaper-url) WALLPAPER_URL="$2"; shift 2 ;;
            --build-deps-only) BUILD_DEPS_ONLY=1; shift ;;
            --python) TARGET_PYTHON="$2"; shift 2 ;;
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

    if [ "$BUILD_DEPS_ONLY" = 1 ]; then
        install_python_build_deps "$family"
        echo '{"installed": true, "build_deps_only": true}'
        exit 0
    fi

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
