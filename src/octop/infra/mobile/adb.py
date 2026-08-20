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
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_WM_SIZE = re.compile(r"Physical size:\s*(\d+)x(\d+)")
_DISPLAY_ID = re.compile(r"Display\s+(\d+)")


def find_adb() -> str | None:
    """Locate ``adb`` without guessing OS-specific install layouts.

    Resolution order:
    1. ``PATH`` via ``shutil.which("adb")`` (covers ``adb.exe`` on Windows).
    2. ``ANDROID_HOME`` / ``ANDROID_SDK_ROOT`` if the user set them — only
       ``<root>/platform-tools/adb[.exe]``, never hardcoded SDK paths under
       ``~/Library``, ``~/Android``, ``%LOCALAPPDATA%``, etc.
    """
    found = shutil.which("adb")
    if found:
        return found
    adb_name = "adb.exe" if os.name == "nt" else "adb"
    for env_key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = (os.environ.get(env_key) or "").strip()
        if not root:
            continue
        path = Path(root) / "platform-tools" / adb_name
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


def extract_png(data: bytes) -> bytes | None:
    """Return a PNG payload, skipping adb/screencap warning text prefixed on stdout."""
    idx = data.find(_PNG_MAGIC)
    if idx < 0:
        return None
    return data[idx:] if idx > 0 else data


def primary_display_id(device: str, *, adb: str | None = None) -> str | None:
    exe = adb or find_adb()
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-s", device, "shell", "dumpsys", "SurfaceFlinger", "--display-id"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _DISPLAY_ID.search(proc.stdout or "")
    return match.group(1) if match else None


def wm_size(device: str, *, adb: str | None = None) -> tuple[int, int] | None:
    exe = adb or find_adb()
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-s", device, "shell", "wm", "size"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _WM_SIZE.search(proc.stdout or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def screenrecord_h264_args(
    device: str,
    *,
    adb: str,
    display_id: str | None = None,
    bit_rate: int = 4_000_000,
    size: str | None = "720x1600",
) -> list[str]:
    cmd = [
        adb,
        "-s",
        device,
        "exec-out",
        "screenrecord",
        "--output-format=h264",
        "--time-limit=0",
        f"--bit-rate={bit_rate}",
    ]
    if size:
        cmd.extend(["--size", size])
    if display_id:
        cmd.extend(["--display-id", display_id])
    cmd.append("-")
    return cmd


def extract_raw_rgba(data: bytes) -> tuple[int, int, bytes] | None:
    """Parse ``screencap`` raw RGBA, skipping any text prefix on stdout."""
    for i in range(0, max(0, len(data) - 16)):
        width = int.from_bytes(data[i : i + 4], "little")
        height = int.from_bytes(data[i + 4 : i + 8], "little")
        if not (16 <= width <= 4096 and 16 <= height <= 8192):
            continue
        needed = width * height * 4
        body = data[i + 16 : i + 16 + needed]
        if len(body) != needed:
            continue
        return width, height, body
    return None


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
    return extract_png(proc.stdout)


def screencap_rgba(device: str, *, adb: str | None = None) -> tuple[int, int, bytes] | None:
    exe = adb or find_adb()
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-s", device, "exec-out", "screencap"],
            capture_output=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    return extract_raw_rgba(proc.stdout)


def capture_jpeg_frame(
    device: str,
    *,
    quality: int = 80,
    max_side: int = 720,
    adb: str | None = None,
) -> tuple[bytes, int, int, int, int] | None:
    """Capture a JPEG preview.

    Returns ``(jpeg, stream_w, stream_h, device_w, device_h)``. Stream size may
    be downscaled for bandwidth; device size is the true screen for tap mapping.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed; mobile capture unavailable")
        return None

    img: Image.Image | None = None
    raw = screencap_rgba(device, adb=adb)
    if raw is not None:
        width, height, body = raw
        try:
            img = Image.frombytes("RGBA", (width, height), body).convert("RGB")
        except ValueError:
            img = None
    if img is None:
        png = screencap_png(device, adb=adb)
        if not png:
            return None
        try:
            img = Image.open(io.BytesIO(png)).convert("RGB")
        except OSError:
            return None

    device_w, device_h = img.size
    stream = img
    longest = max(device_w, device_h)
    if max_side > 0 and longest > max_side:
        scale = max_side / float(longest)
        stream = img.resize(
            (max(1, int(device_w * scale)), max(1, int(device_h * scale))),
            Image.Resampling.BILINEAR,
        )
    buf = io.BytesIO()
    stream.save(buf, format="JPEG", quality=max(30, min(95, quality)))
    sw, sh = stream.size
    return buf.getvalue(), sw, sh, device_w, device_h


_INPUT_SUBPROCESS_TIMEOUT_S = 20.0

# Common Android keycodes for Remote Android chrome.
KEYCODE_HOME = 3
KEYCODE_BACK = 4
KEYCODE_VOLUME_UP = 24
KEYCODE_VOLUME_DOWN = 25
KEYCODE_POWER = 26
KEYCODE_APP_SWITCH = 187


def tap(device: str, x: int, y: int, *, adb: str | None = None) -> bool:
    exe = adb or find_adb()
    if not exe:
        return False
    try:
        proc = subprocess.run(
            [exe, "-s", device, "shell", "input", "tap", str(x), str(y)],
            capture_output=True,
            timeout=_INPUT_SUBPROCESS_TIMEOUT_S,
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
            timeout=_INPUT_SUBPROCESS_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def keyevent(device: str, keycode: int, *, adb: str | None = None) -> bool:
    exe = adb or find_adb()
    if not exe:
        return False
    try:
        proc = subprocess.run(
            [exe, "-s", device, "shell", "input", "keyevent", str(int(keycode))],
            capture_output=True,
            timeout=_INPUT_SUBPROCESS_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def input_text(device: str, text: str, *, adb: str | None = None) -> bool:
    """Type text via ``adb shell input text`` (ASCII / Latin; spaces as ``%s``)."""
    exe = adb or find_adb()
    if not exe:
        return False
    raw = text or ""
    if not raw:
        return True
    # ``input text`` treats space as %s; keep the payload shell-safe.
    escaped = (
        raw.replace("\\", "\\\\")
        .replace("%", "%%")
        .replace(" ", "%s")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
        .replace("&", "\\&")
        .replace("|", "\\|")
        .replace(";", "\\;")
        .replace("<", "\\<")
        .replace(">", "\\>")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )
    try:
        proc = subprocess.run(
            [exe, "-s", device, "shell", "input", "text", escaped],
            capture_output=True,
            timeout=_INPUT_SUBPROCESS_TIMEOUT_S,
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


# One shell round-trip for the Remote Phone info panel.
_DEVICE_INFO_SHELL = (
    "echo model=$(getprop ro.product.model); "
    "echo market=$(getprop ro.product.marketname); "
    "echo manufacturer=$(getprop ro.product.manufacturer); "
    "echo release=$(getprop ro.build.version.release); "
    "echo sdk=$(getprop ro.build.version.sdk); "
    "echo size=$(wm size 2>/dev/null | tr '\\n' ' '); "
    "echo density=$(wm density 2>/dev/null | tr '\\n' ' '); "
    "echo mem_kb=$(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null); "
    "echo cores=$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo); "
    "echo df=$(df -k /data 2>/dev/null | awk 'NR==2{print $2,$3,$4}'); "
    "echo fps=$(dumpsys display 2>/dev/null | grep -oE 'fps=[0-9.]+' | head -1)"
)

_KV_LINE = re.compile(r"^([a-z_]+)=(.*)$")
_SIZE_PAIR = re.compile(r"(\d+)\s*x\s*(\d+)", re.I)
_DENSITY_NUM = re.compile(r"(?:density|Override density|Physical density)\s*:\s*(\d+)", re.I)
_FPS_NUM = re.compile(r"fps=([0-9.]+)", re.I)


def _parse_kv_block(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        match = _KV_LINE.match(raw.strip())
        if match:
            out[match.group(1)] = match.group(2).strip()
    return out


def _kb_to_gb(kb: float) -> float:
    return round(kb / (1024 * 1024), 3)


def parse_device_info_payload(device: str, text: str) -> dict[str, object]:
    """Parse ``_DEVICE_INFO_SHELL`` stdout into a JSON-ready dict."""
    kv = _parse_kv_block(text)
    model = kv.get("market") or kv.get("model") or None
    if model == "":
        model = None
    manufacturer = kv.get("manufacturer") or None
    if manufacturer == "":
        manufacturer = None
    release = kv.get("release") or None
    sdk = kv.get("sdk") or None

    width: int | None = None
    height: int | None = None
    size_match = _SIZE_PAIR.search(kv.get("size", ""))
    if size_match:
        width, height = int(size_match.group(1)), int(size_match.group(2))

    density_dpi: int | None = None
    dens_match = _DENSITY_NUM.search(kv.get("density", ""))
    if dens_match:
        density_dpi = int(dens_match.group(1))
    else:
        digits = re.search(r"(\d+)", kv.get("density", ""))
        if digits:
            density_dpi = int(digits.group(1))

    refresh_hz: float | None = None
    fps_match = _FPS_NUM.search(kv.get("fps", ""))
    if fps_match:
        try:
            refresh_hz = round(float(fps_match.group(1)), 1)
        except ValueError:
            refresh_hz = None

    mem_total_mb: int | None = None
    mem_raw = kv.get("mem_kb", "").strip()
    if mem_raw.isdigit():
        mem_total_mb = int(int(mem_raw) / 1024)

    cpu_cores: int | None = None
    cores_raw = kv.get("cores", "").strip()
    if cores_raw.isdigit():
        cpu_cores = int(cores_raw)

    storage_total_gb: float | None = None
    storage_used_gb: float | None = None
    storage_avail_gb: float | None = None
    df_parts = kv.get("df", "").split()
    if len(df_parts) >= 3:
        try:
            total_kb, used_kb, avail_kb = (
                float(df_parts[0]),
                float(df_parts[1]),
                float(df_parts[2]),
            )
            storage_total_gb = _kb_to_gb(total_kb)
            storage_used_gb = _kb_to_gb(used_kb)
            storage_avail_gb = _kb_to_gb(avail_kb)
        except ValueError:
            pass

    return {
        "device": device,
        "model": model,
        "manufacturer": manufacturer,
        "android_version": release,
        "sdk": int(sdk) if sdk and sdk.isdigit() else None,
        "width": width,
        "height": height,
        "density_dpi": density_dpi,
        "refresh_hz": refresh_hz,
        "mem_total_mb": mem_total_mb,
        "cpu_cores": cpu_cores,
        "storage_total_gb": storage_total_gb,
        "storage_used_gb": storage_used_gb,
        "storage_avail_gb": storage_avail_gb,
    }


def device_info(device: str, *, adb: str | None = None) -> dict[str, object]:
    """Probe a connected device for the Remote Phone info panel."""
    _code, out = shell(device, _DEVICE_INFO_SHELL, adb=adb)
    info = parse_device_info_payload(device, out)
    if info.get("width") is None or info.get("height") is None:
        size = wm_size(device, adb=adb)
        if size:
            info["width"], info["height"] = size
    return info
