#!/bin/bash
# Install the virtual desktop and its system Chromium into the image.
# Does not start Xvnc. The user still confirms enablement in the dashboard.
#
# Laya is not included. CPU torch plus the multilingual checkpoint needs about
# 4 GB of disk and ~2 GB of RAM, and the checkpoint is downloaded on first start.
# The Android container is a separate multi-gigabyte image and is not included.
set -euo pipefail

SCRIPT="/app/src/octop/infra/control/desktop/scripts/linux/v1.0/install.sh"
if [ ! -f "$SCRIPT" ]; then
    echo "desktop install script missing: $SCRIPT" >&2
    exit 1
fi

bash "$SCRIPT" --no-start

if ! command -v Xvnc >/dev/null 2>&1 && ! command -v Xtigervnc >/dev/null 2>&1; then
    echo "Xvnc was not installed" >&2
    exit 1
fi
# Desktop prefers system Chromium. A second Playwright browser download is not used.
# Debian arm64 sometimes has no chromium package; Firefox still runs the desktop,
# but Browser AI only treats a Chromium binary as bundled.
browser_flag=false
if [ -x /usr/bin/chromium ] || [ -x /usr/bin/chromium-browser ]; then
    browser_flag=true
elif [ -x /usr/bin/firefox-esr ] || [ -x /usr/bin/firefox ]; then
    echo "system Chromium missing; desktop browser is Firefox. Browser AI stays unbundled." >&2
else
    echo "desktop browser missing after desktop install" >&2
    exit 1
fi
test -x /opt/octop-desktop/start-openbox.sh
test -x /opt/octop-desktop/start-session.sh
test -f /etc/octop-desktop/rfbauth

for cmd in /proc/[0-9]*/cmdline; do
    [ -r "$cmd" ] || continue
    if tr '\0' ' ' < "$cmd" | grep -qE 'X(vnc|tigervnc)'; then
        echo "desktop services must stay stopped in the image" >&2
        exit 1
    fi
done

mkdir -p /etc/octop
cat > /etc/octop/bundled-components.json << EOF
{"desktop": true, "browser": ${browser_flag}, "laya": false}
EOF

if command -v apt-get >/dev/null 2>&1; then
    apt-get purge -y build-essential python3-dev python3.12-dev >/dev/null 2>&1 || true
    apt-get autoremove -y >/dev/null 2>&1 || true
    rm -rf /var/lib/apt/lists/*
fi
