"""Tests for the desktop shell ownership boundary (OCTOP_DESKTOP_SHELL=1)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from fastapi import BackgroundTasks, Request

from octop.infra.desktop import SHELL_OWNED_ENV_KEYS, desktop_shell_enabled
from octop.infra.utils.env_file import apply_env_file, apply_env_file_replace, save_env_file


def test_desktop_shell_enabled_detects_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OCTOP_DESKTOP_SHELL", raising=False)
    assert desktop_shell_enabled() is False
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    assert desktop_shell_enabled() is True
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "true")
    assert desktop_shell_enabled() is True


def test_shell_owned_env_keys_covers_bind_and_identity() -> None:
    for key in ("OCTOP_DESKTOP_SHELL", "OCTOP_GREEN_PACKAGES", "OCTOP_BIND_HOST", "OCTOP_PORT"):
        assert key in SHELL_OWNED_ENV_KEYS


def test_apply_env_file_never_overrides_shell_owned_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "env"
    save_env_file(path, {"OCTOP_PORT": "9999", "OCTOP_DESKTOP_SHELL": "0", "KEEP": "yes"})
    monkeypatch.setenv("OCTOP_PORT", "12345")
    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    apply_env_file(path)
    assert os.environ["OCTOP_PORT"] == "12345"
    assert os.environ["OCTOP_DESKTOP_SHELL"] == "1"
    assert os.environ["KEEP"] == "yes"


def test_apply_env_file_replace_keeps_shell_owned_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "env"
    monkeypatch.setenv("OCTOP_HOME", "/shell/home")
    save_env_file(path, {})
    apply_env_file_replace(path, previous={"OCTOP_HOME": "/file/home"})
    assert os.environ["OCTOP_HOME"] == "/shell/home"


def _fake_env_server(root: Path) -> Any:
    return type("Server", (), {"paths": type("Paths", (), {"root": root})()})()


@pytest.mark.asyncio
async def test_envs_api_rejects_shell_owned_key_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.api.routers import envs as envs_router
    from octop.infra.errors import OctopError

    server = _fake_env_server(tmp_path)
    with pytest.raises(OctopError):
        await envs_router.batch_save_envs(
            {"OCTOP_PORT": "8088"},
            _=None,
            server=server,
        )


@pytest.mark.asyncio
async def test_envs_api_rejects_shell_owned_key_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.api.routers import envs as envs_router
    from octop.infra.errors import OctopError

    server = _fake_env_server(tmp_path)
    with pytest.raises(OctopError):
        await envs_router.delete_env("OCTOP_DESKTOP_SHELL", _=None, server=server)


@pytest.mark.asyncio
async def test_update_api_rejects_when_shell_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.api.routers import update as update_router
    from octop.infra.errors import ErrorCode, OctopError

    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    monkeypatch.setattr(update_router, "get_editable_path", lambda: None)
    monkeypatch.setattr(update_router, "get_local_version", lambda: "1.0.0")
    monkeypatch.setattr(update_router, "detect_service_mode", lambda: None)

    # /status returns a benign shell-owned payload, never probing PyPI.
    status = await update_router.update_status(_=None, server=None)
    assert status["updates_managed_by_shell"] is True
    assert status["has_update"] is False

    # Mutating endpoints are rejected before any work.
    with pytest.raises(OctopError) as exc:
        await update_router.check_for_updates(_=None, server=None)
    assert exc.value.code == ErrorCode.FORBIDDEN

    with pytest.raises(OctopError) as exc:
        await update_router.update_settings(
            update_router.UpdateSettingsBody(stable_only=False), server=None, _=None
        )
    assert exc.value.code == ErrorCode.FORBIDDEN

    with pytest.raises(OctopError) as exc:
        await update_router.trigger_upgrade(
            request=Request({"type": "http", "headers": []}),
            body=update_router.UpgradeBody(),
            server=None,
            _=None,
        )
    assert exc.value.code == ErrorCode.FORBIDDEN

    with pytest.raises(OctopError) as exc:
        await update_router.restart_service_endpoint(BackgroundTasks(), server=None, _=None)
    assert exc.value.code == ErrorCode.FORBIDDEN


def test_self_update_run_upgrade_refuses_shell_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.setup import self_update

    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    result = self_update.run_upgrade(version="9.9.9")
    assert result.success is False
    assert "shell" in (result.error or "")


def test_cli_update_refuses_shell_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.cli.commands.update import update

    monkeypatch.setenv("OCTOP_DESKTOP_SHELL", "1")
    with pytest.raises(SystemExit) as exc:
        update.callback(check=False, yes=True, verbose=False, allow_prerelease=False)
    assert exc.value.code == 1
