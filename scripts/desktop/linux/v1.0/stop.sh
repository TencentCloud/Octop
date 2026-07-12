#!/bin/bash
set -euo pipefail
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  systemctl stop octop-desktop-openbox octop-desktop-session octop-desktop-xvnc || true
else
  INSTALL_ROOT="/opt/octop-desktop"
  pkill -f "openbox --config-file ${INSTALL_ROOT}/openbox.xml" 2>/dev/null || true
  pkill -f "xfce4-panel" 2>/dev/null || true
  pkill -f "xfdesktop" 2>/dev/null || true
  pkill -f "start-session.sh" 2>/dev/null || true
  pkill -f "Xvnc.*:99" 2>/dev/null || true
  pkill -f "Xtigervnc.*:99" 2>/dev/null || true
  rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
fi
echo "octop-desktop services stopped"
