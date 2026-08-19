"""adb discovery, device listing, capture, and input helpers."""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_DEVICE_LINE = re.compile(r"^(\S+)\s+(device|emulator)\s*$")


def find_adb() -> str | None:
    found = shutil.which("adb")
    if found:
        return found
    home = Path.home()
    candidates = (
        home / "Library/Android/sdk/platform-tools/adb",
        home / "Android/Sdk/platform-tools/adb",
        Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools/adb",
        Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools/adb",
    )
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def list_devices(*, adb: str | None = None) -> list[str]:
    exe = adb or find_adb()
    if not exe:
        return []
    try:
        proc = subprocess.run(
            [exe, "devices"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    devices: list[str] = []
    for line in proc.stdout.splitlines()[1:]:
        match = _DEVICE_LINE.match(line.strip())
        if match:
            devices.append(match.group(1))
    return devices


def screencap_png(device: str, *, adb: str | None = None) -> bytes | None:
    exe = adb or find_adb()
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-s", device, "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    return proc.stdout


def capture_jpeg_frame(
    device: str,
    *,
    quality: int = 80,
    adb: str | None = None,
) -> tuple[bytes, int, int] | None:
    png = screencap_png(device, adb=adb)
    if not png:
        return None
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed; mobile capture unavailable")
        return None
    try:
        img = Image.open(io.BytesIO(png))
    except OSError:
        return None
    width, height = img.size
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=max(30, min(95, quality)))
    return buf.getvalue(), width, height


def tap(device: str, x: int, y: int, *, adb: str | None = None) -> bool:
    exe = adb or find_adb()
    if not exe:
        return False
    try:
        proc = subprocess.run(
            [exe, "-s", device, "shell", "input", "tap", str(x), str(y)],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def swipe(
    device: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int = 300,
    *,
    adb: str | None = None,
) -> bool:
    exe = adb or find_adb()
    if not exe:
        return False
    try:
        proc = subprocess.run(
            [
                exe,
                "-s",
                device,
                "shell",
                "input",
                "swipe",
                str(x1),
                str(y1),
                str(x2),
                str(y2),
                str(duration_ms),
            ],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def shell(device: str, command: str, *, adb: str | None = None) -> tuple[int, str]:
    exe = adb or find_adb()
    if not exe:
        return 127, "adb not found"
    try:
        proc = subprocess.run(
            [exe, "-s", device, "shell", command],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 124, "timeout"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()
