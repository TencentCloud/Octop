"""Unit tests for connector host CLI install helper."""

from __future__ import annotations

from typing import Any

import pytest
from tests.support.fakes import fake_bin_path

from octop.infra.connectors.gateway import cli_install


def test_cli_install_specs_registered() -> None:
    feishu = cli_install.get_cli_install_spec("feishu-cli")
    wecom = cli_install.get_cli_install_spec("wecom-cli")
    assert feishu is not None
    assert feishu.binary == "lark-cli"
    assert feishu.install_command == "npm install -g @larksuite/cli"
    assert wecom is not None
    assert wecom.binary == "wecom-cli"
    assert wecom.install_command == "npm install -g @wecom/cli"
    assert cli_install.get_cli_install_spec("tencent-ima") is None


def test_install_when_already_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_install.shutil, "which", lambda name: fake_bin_path(name))
    monkeypatch.setattr(cli_install, "_read_version", lambda _path: "1.2.3")
    out = cli_install.install_connector_cli("feishu-cli")
    assert out["ok"] is True
    assert out["already_installed"] is True
    assert out["version"] == "1.2.3"
    assert out["install_command"].startswith("npm install -g")


def test_install_fails_without_npm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _which(name: str) -> str | None:
        return None

    monkeypatch.setattr(cli_install.shutil, "which", _which)
    out = cli_install.install_connector_cli("wecom-cli")
    assert out["ok"] is False
    assert "npm" in out["error"].lower()
    assert out["install_command"] == "npm install -g @wecom/cli"
    assert out["doc_url"]


def test_install_runs_npm(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    calls: list[list[str]] = []
    state = {"installed": False}

    def _which(name: str) -> str | None:
        if name == "npm":
            return fake_bin_path("npm")
        if name in ("lark-cli", "wecom-cli"):
            return fake_bin_path(name) if state["installed"] else None
        return None

    def _run(argv: list[str], **kwargs: Any) -> Any:
        del kwargs
        calls.append(list(argv))
        if argv[1:3] == ["config", "get"]:

            class _Cfg:
                returncode = 0
                stdout = str(tmp_path)
                stderr = ""

            return _Cfg()
        state["installed"] = True

        class _Completed:
            returncode = 0
            stdout = "added 1 package"
            stderr = ""

        return _Completed()

    monkeypatch.setattr(cli_install.shutil, "which", _which)
    monkeypatch.setattr(cli_install.subprocess, "run", _run)
    monkeypatch.setattr(cli_install, "_read_version", lambda _path: "9.9.9")
    out = cli_install.install_connector_cli("feishu-cli")
    assert out["ok"] is True
    assert out["already_installed"] is False
    assert out["version"] == "9.9.9"
    install_call = [c for c in calls if c[1:3] == ["install", "-g"]][0]
    assert install_call[:3] == [fake_bin_path("npm"), "install", "-g"]
    # 全局目录可写时保持原行为：不加 --prefix 降级参数
    assert "--prefix" not in install_call


def test_install_degrades_to_user_prefix_when_global_not_writable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """npm 全局目录不可写（fnOS/容器内非 root 用户）时降级到 ~/.npm-global。"""
    calls: list[list[str]] = []
    state = {"installed": False}
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    # Windows 上 os.path.expanduser("~") 读 USERPROFILE，需一并覆盖以跨平台
    monkeypatch.setenv("USERPROFILE", str(home))

    def _which(name: str) -> str | None:
        if name == "npm":
            return fake_bin_path("npm")
        if name in ("lark-cli", "wecom-cli"):
            return fake_bin_path(name) if state["installed"] else None
        return None

    def _run(argv: list[str], **kwargs: Any) -> Any:
        del kwargs
        calls.append(list(argv))
        if argv[1:3] == ["config", "get"]:

            class _Cfg:
                returncode = 0
                stdout = "/usr/local"
                stderr = ""

            return _Cfg()
        state["installed"] = True

        class _Completed:
            returncode = 0
            stdout = "added 1 package"
            stderr = ""

        return _Completed()

    monkeypatch.setattr(cli_install.shutil, "which", _which)
    monkeypatch.setattr(cli_install.subprocess, "run", _run)
    # 模拟 /usr/local 不可写（非 root 用户）
    monkeypatch.setattr(cli_install.os, "access", lambda _p, _m: False)
    monkeypatch.setattr(cli_install, "_read_version", lambda _path: "9.9.9")
    out = cli_install.install_connector_cli("wecom-cli")
    assert out["ok"] is True
    assert out["already_installed"] is False
    install_call = [c for c in calls if c[1:3] == ["install", "-g"]][0]
    assert "--prefix" in install_call
    assert str(home / ".npm-global") in install_call
    assert cli_install._user_npm_prefix()[0] == str(home / ".npm-global")
    # Success path still returns the prefixed command so UI/docs stay consistent.
    assert out["install_command"] == (f"npm install -g --prefix {home / '.npm-global'} @wecom/cli")


def test_install_failure_message_uses_prefixed_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """When global prefix is not writable, failure guidance must not suggest bare -g."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    def _which(name: str) -> str | None:
        if name == "npm":
            return fake_bin_path("npm")
        return None

    def _run(argv: list[str], **kwargs: Any) -> Any:
        del kwargs
        if argv[1:3] == ["config", "get"]:

            class _Cfg:
                returncode = 0
                stdout = "/usr/local"
                stderr = ""

            return _Cfg()

        class _Failed:
            returncode = 243
            stdout = ""
            stderr = "EACCES: permission denied"

        return _Failed()

    monkeypatch.setattr(cli_install.shutil, "which", _which)
    monkeypatch.setattr(cli_install.subprocess, "run", _run)
    monkeypatch.setattr(cli_install.os, "access", lambda _p, _m: False)

    out = cli_install.install_connector_cli("wecom-cli")
    assert out["ok"] is False
    prefixed = f"npm install -g --prefix {home / '.npm-global'} @wecom/cli"
    assert out["install_command"] == prefixed
    assert prefixed in out["error"]
    assert "npm install -g @wecom/cli" not in out["error"].replace(prefixed, "")


def test_ensure_cli_path_injects_user_bin(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    home = tmp_path / "home"
    user_prefix = str(home / ".npm-global")
    bin_dir = cli_install._prefix_bin_dir(user_prefix)
    import os as _os

    _os.makedirs(bin_dir, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    # Windows 上 os.path.expanduser("~") 读 USERPROFILE，需一并覆盖以跨平台
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setitem(cli_install.os.environ, "PATH", "/usr/bin")
    out = cli_install.ensure_cli_path()
    assert out == bin_dir
    assert cli_install.os.environ["PATH"].startswith(bin_dir + _os.pathsep)
    # 幂等：重复调用不重复追加
    cli_install.ensure_cli_path()
    assert cli_install.os.environ["PATH"].count(bin_dir) == 1
