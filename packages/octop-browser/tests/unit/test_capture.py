"""Unit tests for the screenshot path-resolution logic.

These cover the *path computation* in ``actions.capture._resolve_path``
without spinning up Chrome — the actual CDP round-trip is covered by the
finnie live test suite.
"""

from __future__ import annotations

from pathlib import Path

from octop_browser.actions.capture import _resolve_path
from octop_browser.settings import OctopSettings


def _cfg(tmp_path: Path) -> OctopSettings:
    return OctopSettings(screenshots_dir=tmp_path)


def test_default_filename_is_timestamped_png(tmp_path: Path):
    p = _resolve_path(None, _cfg(tmp_path))
    assert p.parent == tmp_path
    assert p.name.startswith("octop-")
    assert p.suffix == ".png"
    # Created the directory if it didn't exist.
    assert tmp_path.exists()


def test_absolute_path_is_used_verbatim(tmp_path: Path):
    target = tmp_path / "snap" / "shot.png"
    p = _resolve_path(target, _cfg(tmp_path / "elsewhere"))
    assert p == target
    assert target.parent.exists()  # parent dir auto-created


def test_relative_path_resolves_under_screenshots_dir(tmp_path: Path):
    p = _resolve_path("daily/shot.png", _cfg(tmp_path))
    assert p == tmp_path / "daily" / "shot.png"
    assert (tmp_path / "daily").exists()


def test_user_home_is_expanded(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = _resolve_path("~/myshot.png", _cfg(tmp_path / "ignored"))
    # ~ is expanded *before* the relative-path branch; an absolute path
    # then bypasses screenshots_dir entirely.
    assert p == tmp_path / "myshot.png"


def test_apply_viewport_sends_setdevicemetricsoverride(tmp_path: Path):
    """``_InternalCDPSession._apply_viewport`` should emit a
    ``Emulation.setDeviceMetricsOverride`` CDP call with the configured
    width/height — that's what makes default screenshots come out at a
    sensible size instead of Chromium's tiny ~800×600 default.
    """
    import asyncio

    from octop_browser.profile import Profile
    from octop_browser.session import _InternalCDPSession
    from octop_browser.settings import OctopSettings

    sent: list[tuple[str, dict]] = []

    class _FakeClient:
        async def send(self, method: str, params: dict | None = None) -> dict:
            sent.append((method, params or {}))
            return {}

    cfg = OctopSettings(viewport_width=1280, viewport_height=720)
    profile = Profile(name="t", data_dir=tmp_path, cdp_port=9999)
    sess = _InternalCDPSession(profile, cfg)
    sess._client = _FakeClient()  # type: ignore[assignment]

    asyncio.run(sess._apply_viewport())

    assert sent == [
        (
            "Emulation.setDeviceMetricsOverride",
            {
                "width": 1280,
                "height": 720,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
        )
    ]
