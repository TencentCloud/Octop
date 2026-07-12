#!/bin/bash
set -euo pipefail

_xvnc_alive() {
  local pattern="$1"
  local pid stat
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    stat="$(ps -o stat= -p "$pid" 2>/dev/null || true)"
    [[ "$stat" == Z* ]] && continue
    return 0
  done < <(pgrep -f "$pattern" 2>/dev/null || true)
  return 1
}

if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  systemctl start octop-desktop-xvnc octop-desktop-session octop-desktop-openbox
else
  OCTOP_HOME="${OCTOP_HOME:-$HOME/.octop}"
  INSTALL_ROOT="/opt/octop-desktop"
  DISPLAY_NUM=":99"
  if ! _xvnc_alive "Xvnc.*${DISPLAY_NUM}"; then
    rm -f "/tmp/.X${DISPLAY_NUM#:}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM#:}"
    nohup "$(command -v Xvnc || command -v Xtigervnc)" :99 -depth 24 -geometry 1920x1080 \
      -rfbport 5900 -localhost yes -AlwaysShared -maxclients 256 -SecurityTypes VncAuth \
      -rfbauth /etc/octop-desktop/rfbauth \
      > "${OCTOP_HOME}/desktop/xvnc.log" 2>&1 &
    sleep 1
  fi
  if ! _xvnc_alive "openbox --config-file ${INSTALL_ROOT}/openbox.xml"; then
    nohup "${INSTALL_ROOT}/start-session.sh" > "${OCTOP_HOME}/desktop/session.log" 2>&1 &
    sleep 1
    nohup "${INSTALL_ROOT}/start-openbox.sh" > "${OCTOP_HOME}/desktop/openbox.log" 2>&1 &
    sleep 1
  fi
fi
echo "octop-desktop services started"
