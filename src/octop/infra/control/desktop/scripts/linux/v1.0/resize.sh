#!/bin/bash
# Restart TigerVNC with a new geometry and re-apply wallpaper.
set -euo pipefail

GEOMETRY="${1:-1920x1080}"
if ! [[ "$GEOMETRY" =~ ^[0-9]{3,5}x[0-9]{3,5}$ ]]; then
  echo "invalid geometry: $GEOMETRY" >&2
  exit 1
fi

INSTALL_ROOT="/opt/octop-desktop"
CONF_DIR="/etc/octop-desktop"
DISPLAY_NUM=":99"
OCTOP_HOME="${OCTOP_HOME:-/root/.octop}"
DESKTOP_STATE_DIR="${OCTOP_HOME}/desktop"
DESKTOP_ENV="${DESKTOP_STATE_DIR}/desktop.env"

detect_xvnc_bin() {
  for p in /usr/bin/Xvnc /usr/bin/Xtigervnc; do
    [ -x "$p" ] && { echo "$p"; return 0; }
  done
  command -v Xvnc >/dev/null 2>&1 && { echo Xvnc; return 0; }
  command -v Xtigervnc >/dev/null 2>&1 && { echo Xtigervnc; return 0; }
  return 1
}

mkdir -p "$DESKTOP_STATE_DIR"
cat > "$DESKTOP_ENV" << EOF
export DISPLAY=${DISPLAY_NUM}
export OCTOP_DESKTOP_DISPLAY=${DISPLAY_NUM}
export OCTOP_DESKTOP_GEOMETRY=${GEOMETRY}
EOF

if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  if [ -f "/etc/systemd/system/octop-desktop-xvnc.service" ]; then
    sed -i "s/-geometry [0-9]\\+x[0-9]\\+/-geometry ${GEOMETRY}/" \
      /etc/systemd/system/octop-desktop-xvnc.service
    systemctl daemon-reload
    systemctl restart octop-desktop-xvnc octop-desktop-session octop-desktop-openbox
    sleep 3
    DISPLAY="${DISPLAY_NUM}" HOME=/root "${INSTALL_ROOT}/apply-wallpaper.sh" 2>/dev/null || true
    DISPLAY="${DISPLAY_NUM}" HOME=/root "${INSTALL_ROOT}/apply-icon-size.sh" 2>/dev/null || true
    echo "geometry set to ${GEOMETRY}"
    exit 0
  fi
fi

pkill -f "xfce4-panel" 2>/dev/null || true
pkill -f "xfdesktop" 2>/dev/null || true
pkill -f "openbox --config-file ${INSTALL_ROOT}/openbox.xml" 2>/dev/null || true
pkill -f "Xvnc.*:99" 2>/dev/null || true
pkill -f "Xtigervnc.*:99" 2>/dev/null || true
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

xvnc_bin=$(detect_xvnc_bin) || { echo "Xvnc not found" >&2; exit 1; }
nohup "$xvnc_bin" :99 -depth 24 -geometry "${GEOMETRY}" -dpi 96 -rfbport 5900 \
  -localhost yes -AlwaysShared -maxclients 256 -SecurityTypes VncAuth \
  -rfbauth "${CONF_DIR}/rfbauth" \
  > "${DESKTOP_STATE_DIR}/xvnc.log" 2>&1 &
sleep 1
nohup "${INSTALL_ROOT}/start-session.sh" > "${DESKTOP_STATE_DIR}/session.log" 2>&1 &
sleep 1
nohup "${INSTALL_ROOT}/start-openbox.sh" > "${DESKTOP_STATE_DIR}/openbox.log" 2>&1 &
sleep 3
DISPLAY="${DISPLAY_NUM}" HOME=/root "${INSTALL_ROOT}/apply-wallpaper.sh" 2>/dev/null || true
DISPLAY="${DISPLAY_NUM}" HOME=/root "${INSTALL_ROOT}/apply-icon-size.sh" 2>/dev/null || true
echo "geometry set to ${GEOMETRY}"
