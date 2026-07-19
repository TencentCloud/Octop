"""Tests for desktop setup helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from octop.i18n import tr
from octop.infra.desktop.setup import (
    _desktop_uninstall_succeeded,
    _sanitize_subprocess_log,
    desktop_status,
    parse_geometry,
    python_deps_install_cmd,
    read_geometry,
    vnc_listens_localhost_only,
)


def test_friendly_install_log_line_maps_apt_lock() -> None:
    from octop.i18n import tr
    from octop.infra.desktop.setup import _friendly_install_log_line

    raw = "E: Unable to acquire the dpkg frontend lock (/var/lib/dpkg/lock-frontend)"
    friendly = _friendly_install_log_line(raw, "en")
    assert friendly == tr("desktop.error_apt_locked", "en")


def test_friendly_install_log_line_maps_install_json() -> None:
    from octop.i18n import tr
    from octop.infra.desktop.setup import _friendly_install_log_line

    raw = '{"installed": false, "error": "apt install failed"}'
    friendly = _friendly_install_log_line(raw, "en")
    assert friendly == tr("desktop.error_apt_failed", "en")


@pytest.mark.asyncio
async def test_iter_subprocess_lines_handles_long_line_without_newline() -> None:
    from octop.infra.desktop.setup import _iter_subprocess_lines

    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(loop=loop)
    reader.feed_data(b"x" * 100_000)
    reader.feed_eof()

    lines = [line async for line in _iter_subprocess_lines(reader)]
    assert len(lines) == 1
    assert len(lines[0]) == 100_000


def test_sanitize_subprocess_log_filters_script_paths() -> None:
    assert (
        _sanitize_subprocess_log(
            "Running /workspace/src/octop/infra/desktop/scripts/linux/v1.0/install.sh ..."
        )
        is None
    )
    assert _sanitize_subprocess_log("Starting desktop services via /opt/foo/start.sh") is None
    assert (
        _sanitize_subprocess_log("Package installed successfully")
        == "Package installed successfully"
    )


def test_desktop_uninstall_succeeded_when_deps_gone() -> None:
    with patch("octop.infra.desktop.setup._python_deps_available", return_value=False):
        assert _desktop_uninstall_succeeded() is True


def test_desktop_uninstall_succeeded_linux_stack_removed_with_host_ready() -> None:
    with (
        patch("octop.infra.desktop.setup.platform.system", return_value="Linux"),
        patch("octop.infra.desktop.setup._python_deps_available", return_value=True),
        patch("octop.infra.desktop.setup._linux_virtual_desktop_present", return_value=False),
        patch(
            "octop.infra.desktop.setup.desktop_status",
            return_value=type("S", (), {"setup_state": "ready"})(),
        ),
    ):
        assert _desktop_uninstall_succeeded() is True


def test_desktop_uninstall_failed_linux_stack_remains() -> None:
    with (
        patch("octop.infra.desktop.setup.platform.system", return_value="Linux"),
        patch("octop.infra.desktop.setup._python_deps_available", return_value=True),
        patch("octop.infra.desktop.setup._linux_virtual_desktop_present", return_value=True),
    ):
        assert _desktop_uninstall_succeeded() is False


def test_allowed_script_path_rejects_outside_bundle(tmp_path, monkeypatch) -> None:
    from octop.infra.desktop.setup import _allowed_script_path, bundled_scripts_dir

    outside = tmp_path / "evil.sh"
    outside.write_text("#!/bin/bash\n", encoding="utf-8")
    assert _allowed_script_path(outside) is False

    inside = bundled_scripts_dir() / "install.sh"
    assert inside.is_file()
    assert _allowed_script_path(inside) is True


def test_script_path_from_env_rejects_outside_bundle(tmp_path, monkeypatch) -> None:
    from octop.infra.desktop.setup import _script_path_from_env

    outside = tmp_path / "evil.sh"
    outside.write_text("#!/bin/bash\n", encoding="utf-8")
    monkeypatch.setenv("OCTOP_DESKTOP_INSTALL_SCRIPT", str(outside))
    assert _script_path_from_env("OCTOP_DESKTOP_INSTALL_SCRIPT") is None


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


def test_python_deps_install_cmd_prefers_uv(monkeypatch) -> None:
    monkeypatch.setattr(
        "octop.infra.desktop.setup.shutil.which",
        lambda name: "/usr/bin/uv" if name == "uv" else None,
    )
    monkeypatch.setattr("octop.infra.desktop.setup.sys.executable", "/venv/bin/python3")
    cmd = python_deps_install_cmd()
    assert cmd is not None
    assert cmd[:5] == ["/usr/bin/uv", "pip", "install", "--python", "/venv/bin/python3"]
    assert "mss>=9.0" in cmd


def test_python_deps_install_cmd_falls_back_to_pip(monkeypatch) -> None:
    monkeypatch.setattr("octop.infra.desktop.setup.shutil.which", lambda _name: None)
    monkeypatch.setattr("octop.infra.desktop.setup.sys.executable", "/venv/bin/python3")
    monkeypatch.setattr(
        "octop.infra.desktop.setup.importlib.util.find_spec",
        lambda name: object() if name == "pip" else None,
    )
    cmd = python_deps_install_cmd()
    assert cmd == [
        "/venv/bin/python3",
        "-m",
        "pip",
        "install",
        "mss>=9.0",
        "pynput>=1.7",
        "pillow>=10.0",
    ]


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
    assert status.reason == tr("desktop.deps_reason", "en")


def test_desktop_status_darwin_missing_perms_not_ok() -> None:
    with (
        patch("octop.infra.desktop.setup._python_deps_available", return_value=True),
        patch("octop.infra.desktop.setup.platform.system", return_value="Darwin"),
        patch("octop.infra.desktop.setup._mac_screen_recording_granted", return_value=False),
        patch("octop.infra.desktop.setup._mac_accessibility_granted", return_value=True),
    ):
        status = desktop_status()
    assert status.setup_state == "ready"
    assert status.ok is False
    assert status.permissions_needed == ("screen_recording",)


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


def test_virtual_desktop_installed_requires_complete_stack() -> None:
    from octop.infra.desktop.setup import _virtual_desktop_installed

    with (
        patch("octop.infra.desktop.setup._runtime_scripts_present", return_value=True),
        patch("octop.infra.desktop.setup.system_conf_dir") as conf,
        patch("octop.infra.desktop.setup.desktop_env_file") as env,
        patch("octop.infra.desktop.setup._systemd_available", return_value=True),
        patch("octop.infra.desktop.setup._systemd_unit_files_present", return_value=False),
    ):
        conf.return_value.is_dir.return_value = True
        env.return_value.is_file.return_value = False
        assert _virtual_desktop_installed() is False


def test_virtual_desktop_installed_ok_with_units() -> None:
    from octop.infra.desktop.setup import _virtual_desktop_installed

    with (
        patch("octop.infra.desktop.setup._runtime_scripts_present", return_value=True),
        patch("octop.infra.desktop.setup.system_conf_dir") as conf,
        patch("octop.infra.desktop.setup.desktop_env_file") as env,
        patch("octop.infra.desktop.setup._systemd_available", return_value=True),
        patch("octop.infra.desktop.setup._systemd_unit_files_present", return_value=True),
    ):
        conf.return_value.is_dir.return_value = True
        env.return_value.is_file.return_value = False
        assert _virtual_desktop_installed() is True


def test_resolve_linux_partial_install_needs_reinstall() -> None:
    from octop.infra.desktop.setup import _resolve_linux_setup

    with (
        patch("octop.infra.desktop.setup._check_vnc_localhost", return_value=(None, "")),
        patch.dict("os.environ", {"DISPLAY": ""}, clear=False),
        patch("octop.infra.desktop.setup._display_from_env_file", return_value=None),
        patch("octop.infra.desktop.setup._virtual_desktop_installed", return_value=False),
    ):
        state, _display, _reason, _vnc = _resolve_linux_setup(locale="en")
    assert state == "needs_install"


def test_desktop_status_linux_deps_missing() -> None:
    with (
        patch("octop.infra.desktop.setup._python_deps_available", return_value=False),
        patch("octop.infra.desktop.setup.platform.system", return_value="Linux"),
    ):
        status = desktop_status()
    assert status.setup_state == "deps_missing"
    assert status.install_script == ""
    assert status.start_command == ""


def test_bundled_install_script_exists() -> None:
    from octop.infra.desktop.setup import bundled_scripts_dir, resolve_install_script_path

    install = bundled_scripts_dir() / "install.sh"
    assert install.is_file()
    assert resolve_install_script_path() == install


def test_python_deps_uninstall_cmd_prefers_uv(monkeypatch) -> None:
    monkeypatch.setattr(
        "octop.infra.desktop.setup.shutil.which",
        lambda name: "/usr/bin/uv" if name == "uv" else None,
    )
    monkeypatch.setattr("octop.infra.desktop.setup.sys.executable", "/venv/bin/python3")
    from octop.infra.desktop.setup import python_deps_uninstall_cmd

    cmd = python_deps_uninstall_cmd()
    assert cmd is not None
    assert cmd[:4] == ["/usr/bin/uv", "pip", "uninstall", "-y"]
    assert "mss" in cmd
