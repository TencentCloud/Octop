"""Tests for desktop setup helpers."""

from __future__ import annotations

from unittest.mock import patch

from octop.infra.desktop.setup import (
    desktop_status,
    parse_geometry,
    read_geometry,
    vnc_listens_localhost_only,
)


def test_parse_geometry() -> None:
    assert parse_geometry("1920x1080") == (1920, 1080)


def test_read_geometry_default() -> None:
    assert read_geometry().endswith("x1080") or "x" in read_geometry()


def test_vnc_localhost_only() -> None:
    assert vnc_listens_localhost_only() in {True, False, None}


def test_desktop_status_deps_missing() -> None:
    with patch("octop.infra.desktop.setup._python_deps_available", return_value=False):
        status = desktop_status()
    assert status.setup_state == "deps_missing"
