"""Screen capture and X11 display helpers for remote desktop."""

from __future__ import annotations

import base64
import contextlib
import io
import logging
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def display_str(display: str | None) -> str:
    return display or os.environ.get("DISPLAY") or ":0"


def is_linux_virtual_display(display: str | None) -> bool:
    """True for VNC virtual seats (:1, :99, …); :0 is the local physical display."""
    if sys.platform != "linux":
        return False
    d = display_str(display)
    if not d.startswith(":"):
        return False
    head = d[1:].split(".", 1)[0]
    try:
        return int(head) != 0
    except ValueError:
        return False


@contextmanager
def display_env(display: str | None) -> Iterator[None]:
    if not display:
        yield
        return
    with _lock:
        prev = os.environ.get("DISPLAY")
        os.environ["DISPLAY"] = display
    try:
        yield
    finally:
        with _lock:
            if prev is None:
                os.environ.pop("DISPLAY", None)
            else:
                os.environ["DISPLAY"] = prev


_IMPORT_TIMEOUT_S = 4.0
_MSS_BACKENDS = ("xgetimage", "xlib", "default")


@dataclass(frozen=True)
class CaptureFrame:
    jpeg_b64: str
    width: int
    height: int


class ScreenCapture:
    def __init__(self, *, display: str | None = None, monitor: int = 0) -> None:
        self._display = display or os.environ.get("DISPLAY")
        self._monitor = monitor
        self._mss: Any | None = None
        self._mss_backend: str | None = None
        self._capture_lock = threading.Lock()

    def close(self) -> None:
        if self._mss is not None:
            with contextlib.suppress(Exception):
                self._mss.close()
            self._mss = None
            self._mss_backend = None

    def _display_str(self) -> str:
        return display_str(self._display)

    def _prefer_import_capture(self) -> bool:
        """TigerVNC virtual displays hang or fail in mss; use ImageMagick import."""
        return is_linux_virtual_display(self._display) and shutil.which("import") is not None

    def _mss_kwargs(self) -> dict[str, Any]:
        if is_linux_virtual_display(self._display) or (
            sys.platform == "linux" and self._display is not None
        ):
            return {"display": self._display_str()}
        return {}

    def _ensure_mss(self) -> Any | None:
        if self._prefer_import_capture():
            return None
        if self._mss is not None:
            return self._mss
        for backend in _MSS_BACKENDS:
            try:
                from mss import MSS

                with display_env(self._display):
                    mss_kwargs = self._mss_kwargs()
                    if mss_kwargs:
                        sct = MSS(display=mss_kwargs["display"], backend=backend)
                    else:
                        sct = MSS(backend=backend)
                    monitors = sct.monitors
                    idx = self._monitor + 1
                    if idx >= len(monitors):
                        idx = 1 if len(monitors) > 1 else 0
                    sct.grab(monitors[idx])
                self._mss = sct
                self._mss_backend = backend
                logger.debug(
                    "desktop capture using mss backend=%s display=%s",
                    backend,
                    self._display,
                )
                return sct
            except Exception:
                with contextlib.suppress(Exception):
                    if self._mss is not None:
                        self._mss.close()
                self._mss = None
                continue
        return None

    def _capture_mss(self, *, quality: int) -> CaptureFrame | None:
        with display_env(self._display):
            try:
                from PIL import Image

                sct = self._ensure_mss()
                if sct is None:
                    return None
                monitors = sct.monitors
                idx = self._monitor + 1
                if idx >= len(monitors):
                    idx = 1 if len(monitors) > 1 else 0
                shot = sct.grab(monitors[idx])
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality, optimize=True)
                data = base64.b64encode(buf.getvalue()).decode("ascii")
                return CaptureFrame(jpeg_b64=data, width=shot.width, height=shot.height)
            except Exception:
                self.close()
                return None

    def _capture_imagemagick(self, *, quality: int) -> CaptureFrame | None:
        if not shutil.which("import"):
            return None
        display = self._display_str()
        env = os.environ.copy()
        env["DISPLAY"] = display
        proc = subprocess.Popen(
            [
                "import",
                "-silent",
                "-display",
                display,
                "-window",
                "root",
                "-quality",
                str(quality),
                "jpg:-",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout, stderr = proc.communicate(timeout=_IMPORT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            with contextlib.suppress(Exception):
                proc.communicate(timeout=1)
            logger.warning("desktop import capture timed out (display=%s)", display)
            return None
        if proc.returncode != 0 or not stdout:
            detail = (stderr or b"").decode("utf-8", errors="replace").strip()
            if detail:
                logger.debug("desktop import capture failed: %s", detail)
            return None
        from PIL import Image

        img = Image.open(io.BytesIO(stdout))
        width, height = img.size
        if stdout.startswith(b"\xff\xd8"):
            data = base64.b64encode(stdout).decode("ascii")
            return CaptureFrame(jpeg_b64=data, width=width, height=height)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = base64.b64encode(buf.getvalue()).decode("ascii")
        return CaptureFrame(jpeg_b64=data, width=width, height=height)

    def capture_jpeg(self, *, quality: int = 80) -> CaptureFrame | None:
        with self._capture_lock:
            if self._prefer_import_capture():
                frame = self._capture_imagemagick(quality=quality)
                if frame is not None:
                    return frame
                return self._capture_mss(quality=quality)
            frame = self._capture_mss(quality=quality)
            if frame is not None:
                return frame
            return self._capture_imagemagick(quality=quality)

    def list_monitors(self) -> list[dict[str, int]]:
        with display_env(self._display):
            try:
                sct = self._ensure_mss()
                if sct is not None:
                    out: list[dict[str, int]] = []
                    for i, mon in enumerate(sct.monitors):
                        if i == 0:
                            continue
                        out.append(
                            {
                                "id": i - 1,
                                "left": int(mon["left"]),
                                "top": int(mon["top"]),
                                "width": int(mon["width"]),
                                "height": int(mon["height"]),
                            }
                        )
                    if out:
                        return out
            except Exception:
                pass
            if shutil.which("xdpyinfo") and self._display:
                try:
                    env = os.environ.copy()
                    env["DISPLAY"] = self._display
                    proc = subprocess.run(
                        ["xdpyinfo", "-display", self._display],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=3,
                        check=False,
                    )
                    if proc.returncode == 0:
                        for line in proc.stdout.splitlines():
                            if "dimensions:" in line:
                                parts = line.split()[1].split("x")
                                return [
                                    {
                                        "id": 0,
                                        "left": 0,
                                        "top": 0,
                                        "width": int(parts[0]),
                                        "height": int(parts[1]),
                                    }
                                ]
                except (OSError, subprocess.TimeoutExpired):
                    pass
            return [{"id": 0, "left": 0, "top": 0, "width": 1920, "height": 1080}]
