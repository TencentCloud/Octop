"""Tests for DISPLAY helpers."""

from __future__ import annotations

from octop.infra.desktop.capture import display_str, is_linux_virtual_display


def test_display_str_defaults() -> None:
    assert display_str(None).startswith(":")


def test_is_linux_virtual_display(monkeypatch) -> None:
    monkeypatch.setattr("octop.infra.desktop.capture.sys.platform", "linux")
    assert is_linux_virtual_display(":99") is True
    assert is_linux_virtual_display(":0") is False


def test_is_linux_virtual_display_non_linux(monkeypatch) -> None:
    monkeypatch.setattr("octop.infra.desktop.capture.sys.platform", "darwin")
    assert is_linux_virtual_display(":99") is False
