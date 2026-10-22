"""Tests for DISPLAY helpers."""

from __future__ import annotations

from octop.infra.control.desktop.capture import display_str, is_linux_virtual_display


def test_display_str_defaults(monkeypatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    assert display_str(None).startswith(":")
    assert display_str(":7") == ":7"
    monkeypatch.setenv("DISPLAY", "/var/run/launchd:0")
    assert display_str(None) == "/var/run/launchd:0"


def test_is_linux_virtual_display(monkeypatch) -> None:
    monkeypatch.setattr("octop.infra.control.desktop.capture.sys.platform", "linux")
    assert is_linux_virtual_display(":99") is True
    assert is_linux_virtual_display(":0") is False


def test_is_linux_virtual_display_non_linux(monkeypatch) -> None:
    monkeypatch.setattr("octop.infra.control.desktop.capture.sys.platform", "darwin")
    assert is_linux_virtual_display(":99") is False
