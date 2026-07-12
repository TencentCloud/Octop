"""Tests for desktop screen capture helpers."""

from __future__ import annotations

import base64
import io
from unittest.mock import MagicMock

from octop.infra.desktop.capture import CaptureFrame, ScreenCapture


def test_prefer_import_on_linux_virtual_display(monkeypatch) -> None:
    cap = ScreenCapture(display=":99")
    monkeypatch.setattr(
        "octop.infra.desktop.capture.shutil.which",
        lambda name: "/usr/bin/import" if name == "import" else None,
    )
    assert cap._prefer_import_capture() is True


def test_prefer_import_false_on_non_linux(monkeypatch) -> None:
    cap = ScreenCapture(display=":99")
    monkeypatch.setattr("octop.infra.desktop.capture.sys.platform", "darwin")
    assert cap._prefer_import_capture() is False


def test_capture_prefers_import_on_linux_virtual_display(monkeypatch) -> None:
    frame = CaptureFrame(jpeg_b64="abc", width=100, height=80)
    cap = ScreenCapture(display=":99", monitor=0)
    mss_calls: list[int] = []

    monkeypatch.setattr(
        cap,
        "_capture_imagemagick",
        lambda *, quality: frame,
    )
    monkeypatch.setattr(
        cap,
        "_capture_mss",
        lambda *, quality: mss_calls.append(quality) or None,
    )
    got = cap.capture_jpeg(quality=70)
    assert got == frame
    assert mss_calls == []


def test_capture_prefers_mss_on_non_virtual_display(monkeypatch) -> None:
    frame = CaptureFrame(jpeg_b64="abc", width=100, height=80)
    cap = ScreenCapture(display=":0", monitor=0)
    import_calls: list[int] = []

    monkeypatch.setattr(cap, "_capture_mss", lambda *, quality: frame)
    monkeypatch.setattr(
        cap,
        "_capture_imagemagick",
        lambda *, quality: import_calls.append(quality) or None,
    )
    got = cap.capture_jpeg(quality=70)
    assert got == frame
    assert import_calls == []


def test_import_jpeg_passthrough_without_reencode(monkeypatch) -> None:
    from PIL import Image

    jpeg_buf = io.BytesIO()
    Image.new("RGB", (64, 48), color=(10, 20, 30)).save(jpeg_buf, format="JPEG", quality=80)
    raw = jpeg_buf.getvalue()

    cap = ScreenCapture(display=":99", monitor=0)

    class _Proc:
        returncode = 0

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            return raw, b""

    monkeypatch.setattr("octop.infra.desktop.capture.shutil.which", lambda name: "/usr/bin/import")
    monkeypatch.setattr("octop.infra.desktop.capture.subprocess.Popen", lambda *a, **k: _Proc())

    frame = cap._capture_imagemagick(quality=70)
    assert frame is not None
    assert frame.width == 64
    assert frame.height == 48
    assert frame.jpeg_b64 == base64.b64encode(raw).decode("ascii")


def test_close_releases_mss() -> None:
    cap = ScreenCapture(display=":99", monitor=0)
    mock_mss = MagicMock()
    cap._mss = mock_mss
    cap.close()
    mock_mss.close.assert_called_once()
    assert cap._mss is None
