#!/usr/bin/env bash
set -euo pipefail
NAME="${OCTOP_MOBILE_CONTAINER:-octop-mobile-android}"
if docker inspect "$NAME" >/dev/null 2>&1; then
  docker start "$NAME" >/dev/null 2>&1 || true
  echo "Container $NAME already exists; started if stopped."
  exit 0
fi
if [ ! -e /dev/binder ] && ! lsmod 2>/dev/null | grep -q binder_linux; then
  echo "Redroid requires binder_linux; use KVM emulator backend instead." >&2
  exit 1
fi
echo "Starting Redroid container $NAME (adb on 5555)…"
docker run -d --name "$NAME" --privileged \
  -p 5555:5555 \
  redroid/redroid:13.0.0-latest \
  androidboot.redroid_gpu_mode=guest
echo "Waiting for adb device…"
sleep 5
if command -v adb >/dev/null 2>&1; then
  adb connect 127.0.0.1:5555 || true
fi
echo "Install complete."
