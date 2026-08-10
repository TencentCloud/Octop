"""Tests for Docker environment detect / ensure helpers."""

from __future__ import annotations

import pytest

from octop.infra.utils import docker_env as docker_mod
from octop.infra.utils.docker_env import docker_status, ensure_docker, install_script


def test_install_script_linux() -> None:
    script = install_script(plat="linux")
    assert "get.docker.com" in script
    assert "docker info" in script


def test_install_script_darwin() -> None:
    script = install_script(plat="darwin")
    assert "brew install --cask docker" in script


def test_status_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_mod, "_platform_key", lambda: "linux")
    monkeypatch.setattr(docker_mod, "_cli_present", lambda: True)
    monkeypatch.setattr(docker_mod, "_daemon_ok", lambda: True)
    result = docker_status(attempt_install=False)
    assert result["status"] == "ready"
    assert result["cli"] is True
    assert result["daemon"] is True
    assert "install_script" in result
    assert "agent_prompt" in result


def test_status_daemon_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_mod, "_platform_key", lambda: "darwin")
    monkeypatch.setattr(docker_mod, "_cli_present", lambda: True)
    monkeypatch.setattr(docker_mod, "_daemon_ok", lambda: False)
    result = docker_status(attempt_install=False)
    assert result["status"] == "daemon_down"
    assert "未响应" in result["agent_prompt"]
    assert "CLI is present" in result["install_script"]
    assert "open -a Docker" in result["install_script"]


def test_agent_prompt_missing_vs_daemon_down() -> None:
    missing = docker_mod.agent_prompt(plat="darwin", status="missing")
    down = docker_mod.agent_prompt(plat="darwin", status="daemon_down")
    assert "brew install --cask docker" in missing
    assert "已有 docker" in down
    assert missing != down


def test_status_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_mod, "_platform_key", lambda: "linux")
    monkeypatch.setattr(docker_mod, "_cli_present", lambda: False)
    monkeypatch.setattr(docker_mod, "_daemon_ok", lambda: False)
    monkeypatch.setattr(docker_mod, "_detect_package_manager", lambda: "apt")
    monkeypatch.setattr(docker_mod, "_can_install_without_password", lambda: True)
    result = docker_status(attempt_install=False)
    assert result["status"] == "missing"
    assert result["can_auto_install"] is True


def test_ensure_skips_non_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_mod, "_platform_key", lambda: "darwin")
    monkeypatch.setattr(docker_mod, "_cli_present", lambda: False)
    monkeypatch.setattr(docker_mod, "_daemon_ok", lambda: False)
    result = ensure_docker()
    assert result["status"] == "skipped"
    assert result["reason"] == "manual_install_required"


def test_ensure_installs_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_mod, "_platform_key", lambda: "linux")
    calls = {"n": 0}

    def cli() -> bool:
        return calls["n"] >= 1

    def daemon() -> bool:
        return calls["n"] >= 1

    monkeypatch.setattr(docker_mod, "_cli_present", cli)
    monkeypatch.setattr(docker_mod, "_daemon_ok", daemon)
    monkeypatch.setattr(docker_mod, "_detect_package_manager", lambda: "apt")
    monkeypatch.setattr(docker_mod, "_can_install_without_password", lambda: True)

    def install() -> tuple[bool, str]:
        calls["n"] += 1
        return True, "apt"

    monkeypatch.setattr(docker_mod, "_try_auto_install_linux", install)
    result = ensure_docker()
    assert result["status"] == "installed"
    assert result["cli"] is True
