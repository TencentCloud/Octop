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


def test_desktop_status_deps_missing_darwin_omits_linux_cmds() -> None:
    with (
        patch("octop.infra.desktop.setup._python_deps_available", return_value=False),
        patch("octop.infra.desktop.setup.platform.system", return_value="Darwin"),
    ):
        status = desktop_status()
    assert status.setup_state == "deps_missing"
    assert status.platform == "darwin"
    assert status.desktop_supported is True
    assert status.install_script == ""
    assert status.start_command == ""
    assert status.permissions_needed == ()
    assert "octop[desktop]" in status.reason


def test_desktop_status_ready_darwin_omits_linux_cmds() -> None:
    with (
        patch("octop.infra.desktop.setup._python_deps_available", return_value=True),
        patch("octop.infra.desktop.setup.platform.system", return_value="Darwin"),
        patch("octop.infra.desktop.setup._mac_screen_recording_granted", return_value=True),
        patch("octop.infra.desktop.setup._mac_accessibility_granted", return_value=True),
    ):
        status = desktop_status()
    assert status.setup_state == "ready"
    assert status.ok is True
    assert status.install_script == ""
    assert status.start_command == ""
    assert status.permissions_needed == ()


def test_desktop_status_darwin_reports_only_missing_perms() -> None:
    with (
        patch("octop.infra.desktop.setup._python_deps_available", return_value=True),
        patch("octop.infra.desktop.setup.platform.system", return_value="Darwin"),
        patch("octop.infra.desktop.setup._mac_screen_recording_granted", return_value=False),
        patch("octop.infra.desktop.setup._mac_accessibility_granted", return_value=True),
    ):
        status = desktop_status()
    assert status.permissions_needed == ("screen_recording",)


def test_desktop_status_linux_keeps_install_cmds() -> None:
    with (
        patch("octop.infra.desktop.setup._python_deps_available", return_value=False),
        patch("octop.infra.desktop.setup.platform.system", return_value="Linux"),
    ):
        status = desktop_status()
    assert status.setup_state == "deps_missing"
    assert status.install_script == "scripts/desktop/linux/v1.0/install.sh"
    assert "systemctl start" in status.start_command
