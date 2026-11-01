#!/bin/bash
#
# Check Octop virtual desktop readiness.
# Output (last line JSON):
#   {"ready": true, "vnc_running": true, "display": ":99", ...}

if [ -z "${BASH_VERSION:-}" ]; then exec /bin/bash "$0" "$@"; fi
set -uo pipefail

CONF_DIR="/etc/octop-desktop"
VERSION_FILE="${CONF_DIR}/version"
DISPLAY_NUM=":99"

vnc_running=false
panel_running=false
desktop_running=false
ready=false
vnc_localhost=true
checks=()
missing=()

mark() {
    checks+=("\"$1\":\"$2\"")
    [ "$2" = ok ] || missing+=("\"$1\"")
}

if [ -d /opt/octop-desktop ] || [ -d "$CONF_DIR" ]; then
    mark packages ok
else
    mark packages missing
fi

if systemctl is-active --quiet octop-desktop-xvnc 2>/dev/null; then
    vnc_running=true
    mark xvnc ok
elif pgrep -f "Xvnc.*:99" >/dev/null 2>&1 || pgrep -f "Xtigervnc.*:99" >/dev/null 2>&1; then
    vnc_running=true
    mark xvnc ok
else
    mark xvnc not_running
fi

if systemctl is-active --quiet octop-desktop-openbox 2>/dev/null; then
    mark openbox ok
elif pgrep -f "openbox --config-file /opt/octop-desktop/openbox.xml" >/dev/null 2>&1; then
    mark openbox ok
else
    mark openbox not_running
fi

if pgrep -f "xfce4-panel" >/dev/null 2>&1; then
    panel_running=true
    mark panel ok
else
    mark panel not_running
fi

if pgrep -f "xfdesktop" >/dev/null 2>&1; then
    desktop_running=true
    mark xfdesktop ok
else
    mark xfdesktop not_running
fi

if DISPLAY="$DISPLAY_NUM" xdpyinfo -display "$DISPLAY_NUM" >/dev/null 2>&1; then
    mark display ok
elif [ -S "/tmp/.X11-unix/X${DISPLAY_NUM#:}" ] && [ "$vnc_running" = true ]; then
    mark display socket_ok
else
    mark display unreachable
fi

for app in xfce4-terminal thunar mousepad; do
    if command -v "$app" >/dev/null 2>&1; then
        mark "$app" ok
    else
        mark "$app" missing
    fi
done

installed_version=$(cat "$VERSION_FILE" 2>/dev/null | tr -d '[:space:]' || echo "")

if [ "$vnc_running" = true ]; then
    vnc_localhost=true
    if command -v ss >/dev/null 2>&1; then
        if ss -ltn "sport = :5900" 2>/dev/null | grep -qE '0\.0\.0\.0:5900|\*:5900|\[::\]:5900'; then
            vnc_localhost=false
            mark vnc_bind exposed
        else
            mark vnc_bind localhost
        fi
    elif command -v netstat >/dev/null 2>&1; then
        if netstat -ltn 2>/dev/null | grep -E ':5900\b' | grep -qv '127.0.0.1:5900'; then
            vnc_localhost=false
            mark vnc_bind exposed
        else
            mark vnc_bind localhost
        fi
    else
        mark vnc_bind unknown
    fi
else
    mark vnc_bind not_running
fi

if [ "$vnc_running" = true ] && [ "$vnc_localhost" = true ] && { DISPLAY="$DISPLAY_NUM" xdpyinfo -display "$DISPLAY_NUM" >/dev/null 2>&1 || [ -S "/tmp/.X11-unix/X${DISPLAY_NUM#:}" ]; }; then
    ready=true
fi

missing_json="[]"
if [ "${#missing[@]}" -gt 0 ]; then
    missing_json="[$(IFS=,; echo "${missing[*]}")]"
fi

checks_json="{$(IFS=,; echo "${checks[*]}")}"

echo "{\"ready\":${ready},\"vnc_running\":${vnc_running},\"vnc_localhost_only\":${vnc_localhost},\"panel_running\":${panel_running},\"desktop_running\":${desktop_running},\"display\":\"${DISPLAY_NUM}\",\"version\":\"${installed_version}\",\"checks\":${checks_json},\"missing\":${missing_json}}"
