"""Tests for desktop input injection."""

from __future__ import annotations

from unittest.mock import MagicMock

from octop.infra.desktop.input import InputInjector


def _force_linux(monkeypatch) -> None:
    # InputInjector decides xdotool via is_linux_virtual_display (capture.sys.platform).
    monkeypatch.setattr("octop.infra.desktop.capture.sys.platform", "linux")


def test_virtual_display_uses_xdotool_for_click(monkeypatch) -> None:
    _force_linux(monkeypatch)
    calls: list[list[str]] = []

    def fake_run(display: str | None, args: list[str]) -> bool:
        calls.append(args)
        return True

    monkeypatch.setattr("octop.infra.desktop.input.shutil.which", lambda name: "/usr/bin/xdotool")
    monkeypatch.setattr("octop.infra.desktop.input._run_xdotool", fake_run)

    inj = InputInjector(display=":99")
    inj.click(120, 340, button="left")

    assert calls == [["mousemove", "120", "340", "click", "1"]]


def test_physical_display_uses_pynput_for_click(monkeypatch) -> None:
    _force_linux(monkeypatch)
    inj = InputInjector(display=":0")
    mouse = MagicMock()
    monkeypatch.setattr(inj, "_controllers", lambda: (mouse, MagicMock()))
    monkeypatch.setattr(inj, "_with_display", lambda fn: fn())
    monkeypatch.setattr(inj, "_button", lambda name: name)

    inj.click(10, 20, button="right", clicks=2)

    mouse.position = (10, 20)
    mouse.click.assert_called_once_with("right", 2)


def test_virtual_display_does_not_init_pynput_on_click(monkeypatch) -> None:
    _force_linux(monkeypatch)
    monkeypatch.setattr("octop.infra.desktop.input.shutil.which", lambda name: "/usr/bin/xdotool")
    monkeypatch.setattr("octop.infra.desktop.input._run_xdotool", lambda *_a, **_k: True)

    inj = InputInjector(display=":99")
    controllers = MagicMock(side_effect=AssertionError("pynput should not be used"))
    monkeypatch.setattr(inj, "_controllers", controllers)

    inj.click(1, 2)
    controllers.assert_not_called()
