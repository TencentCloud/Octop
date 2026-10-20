"""Unit tests for browser launch mode (auto / headed / headless)."""

from __future__ import annotations

import sys

import pytest

from octop_browser.mode import (
    has_desktop_environment,
    normalize_mode,
    resolve_headless,
)


def test_normalize_default_is_auto():
    assert normalize_mode(None) == "auto"
    assert normalize_mode("") == "auto"


def test_normalize_lower_and_strip():
    assert normalize_mode("HEADED") == "headed"
    assert normalize_mode("  headless  ") == "headless"


def test_normalize_invalid():
    with pytest.raises(ValueError):
        normalize_mode("ghost")


def test_resolve_explicit_modes():
    assert resolve_headless("headless") is True
    assert resolve_headless("headed") is False


def test_resolve_auto_with_display(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    assert resolve_headless("auto") is False  # has desktop → headed


def test_resolve_auto_with_wayland(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    assert resolve_headless("auto") is False


def test_resolve_auto_no_display_on_linux(monkeypatch):
    if sys.platform == "darwin" or sys.platform.startswith("win"):
        pytest.skip("auto-headless detection only meaningful on Linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert resolve_headless("auto") is True  # no desktop → headless


def test_has_desktop_macos_or_windows():
    if sys.platform == "darwin" or sys.platform.startswith("win"):
        assert has_desktop_environment() is True
    else:
        # On Linux it depends on env vars; just ensure it returns a bool.
        assert isinstance(has_desktop_environment(), bool)
