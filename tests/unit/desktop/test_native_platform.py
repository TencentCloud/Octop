"""Tests for native vs virtual desktop capture paths."""

from __future__ import annotations

from octop.infra.desktop.capture import ScreenCapture
from octop.infra.desktop.input import InputInjector


def test_mac_uses_mss_not_import(monkeypatch) -> None:
    monkeypatch.setattr("octop.infra.desktop.capture.sys.platform", "darwin")
    cap = ScreenCapture(display=None, monitor=0)
    assert cap._prefer_import_capture() is False
    assert cap._mss_kwargs() == {}


def test_windows_input_uses_pynput_path(monkeypatch) -> None:
    monkeypatch.setattr("octop.infra.desktop.capture.sys.platform", "win32")
    inj = InputInjector(display=None)
    monkeypatch.setattr("octop.infra.desktop.input.shutil.which", lambda _: "/usr/bin/xdotool")
    assert inj._use_xdotool() is False
