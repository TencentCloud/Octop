#!/usr/bin/env bash
# Install / start the Octop Remote Phone Android container (Redroid).
#
# DinD / docker.sock notes:
# - Prefer --network host so adb 5555 is reachable at 127.0.0.1 from the
#   Octop process (same netns as dockerd). Falls back to -p 5555:5555.
# - Mount binderfs when present; use --cgroupns=host for nested runtimes.
set -euo pipefail

NAME="${OCTOP_MOBILE_CONTAINER:-octop-mobile-android}"
ADB_HOST="${OCTOP_MOBILE_ADB_HOST:-127.0.0.1:5555}"
IMAGE="${OCTOP_MOBILE_IMAGE:-redroid/redroid:13.0.0-latest}"
BOOT_WAIT_SECS="${OCTOP_MOBILE_BOOT_WAIT_SECS:-45}"

_connect_adb() {
  if ! command -v adb >/dev/null 2>&1; then
    echo "adb not found on PATH; install Android platform-tools, then run: adb connect ${ADB_HOST}"
    return 0
  fi
  echo "Connecting adb to ${ADB_HOST}…"
  adb disconnect "${ADB_HOST}" >/dev/null 2>&1 || true
  adb connect "${ADB_HOST}" || true
  adb devices || true
}

_container_running() {
  docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null | grep -qi true
}

_wait_for_boot() {
  local i
  echo "Waiting up to ${BOOT_WAIT_SECS}s for Android boot…"
  for i in $(seq 1 "$BOOT_WAIT_SECS"); do
    if ! _container_running; then
      echo "Container $NAME exited during boot:" >&2
      docker logs --tail 80 "$NAME" >&2 || true
      return 1
    fi
    # Prefer getprop when the image exposes it; ignore failures mid-boot.
    if docker exec "$NAME" getprop sys.boot_completed 2>/dev/null | grep -qx 1; then
      echo "Android boot completed."
      return 0
    fi
    # Fallback: adbd listening is enough for our stream path.
    if command -v adb >/dev/null 2>&1; then
      if adb connect "${ADB_HOST}" >/dev/null 2>&1 \
        && adb devices 2>/dev/null | grep -qE "${ADB_HOST//./\\.}[[:space:]]+device"; then
        echo "adb device ${ADB_HOST} is online."
        return 0
      fi
    fi
    sleep 1
  done
  echo "Timed out waiting for Android boot / adb." >&2
  docker ps -a --filter "name=^/${NAME}$" >&2 || true
  docker logs --tail 80 "$NAME" >&2 || true
  return 1
}

_run_args=(
  --name "$NAME"
  --privileged
  --cgroupns=host
  --restart unless-stopped
)

# binderfs makes nested Redroid much more reliable when the host exposes it.
if [ -d /dev/binderfs ]; then
  _run_args+=(-v /dev/binderfs:/dev/binderfs)
fi
if [ -e /dev/binder ]; then
  _run_args+=(--device /dev/binder)
fi

# Host networking: Octop + dockerd share localhost → adb connect 127.0.0.1:5555 works.
# Bridge publish is the fallback when host network is unavailable.
if docker network inspect host >/dev/null 2>&1; then
  _run_args+=(--network host)
  echo "Using --network host (adb at ${ADB_HOST})."
else
  _run_args+=(-p 5555:5555)
  echo "Using published port 5555:5555 (adb at ${ADB_HOST})."
fi

if docker inspect "$NAME" >/dev/null 2>&1; then
  echo "Container $NAME already exists; ensuring it is running…"
  docker start "$NAME" >/dev/null 2>&1 || true
  if ! _container_running; then
    echo "Existing container failed to stay up; recreating…" >&2
    docker rm -f "$NAME" >/dev/null 2>&1 || true
  else
    _wait_for_boot
    _connect_adb
    echo "Install complete."
    exit 0
  fi
fi

if [ ! -e /dev/binder ] && [ ! -d /dev/binderfs ] \
  && ! lsmod 2>/dev/null | grep -q binder_linux; then
  echo "Redroid requires binder (/dev/binder or binderfs); use physical USB or KVM emulator instead." >&2
  exit 1
fi

echo "Starting Redroid container $NAME from ${IMAGE}…"
docker run -d "${_run_args[@]}" \
  "$IMAGE" \
  androidboot.redroid_gpu_mode=guest

_wait_for_boot
_connect_adb
echo "Install complete."
