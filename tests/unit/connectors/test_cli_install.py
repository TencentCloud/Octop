"""Unit tests for connector host CLI install helper."""

from __future__ import annotations

import os
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


def test_obsidian_cli_install_links_bundled_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    home = tmp_path / "home"
    source = tmp_path / "Obsidian.app" / "Contents" / "MacOS" / "obsidian-cli"
    source.parent.mkdir(parents=True)
    source.write_text("obsidian", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    monkeypatch.setattr(cli_install, "obsidian_bundle_candidates", lambda: [str(source)])
    monkeypatch.setattr(cli_install, "_prefix_writable", lambda _prefix: False)
    monkeypatch.setattr(cli_install, "_read_version", lambda _path: "1.12.7")
    dest_name = "obsidian.exe" if os.name == "nt" else "obsidian"
    dest = home / ".local" / "bin" / dest_name

    def _which(name: str) -> str | None:
        if name == "obsidian" and dest.is_file():
            return str(dest)
        return None

    monkeypatch.setattr(cli_install.shutil, "which", _which)
    status = cli_install.cli_install_status("obsidian-cli")
    assert status["installed"] is False
    assert status["install_command"]
    assert "npm" not in status["install_command"]
    assert str(source) in status["install_command"]

    out = cli_install.install_connector_cli("obsidian-cli")
    assert out["ok"] is True
    assert out["already_installed"] is False
    assert out["installed"] is True
    assert out["version"] == "1.12.7"
    assert dest.is_file()


def test_obsidian_cli_install_fails_without_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_install.shutil, "which", lambda _name: None)
    monkeypatch.setattr(cli_install, "obsidian_bundle_candidates", lambda: [])
    monkeypatch.setattr(cli_install, "_prefix_writable", lambda _prefix: False)
    status = cli_install.cli_install_status("obsidian-cli")
    assert status["installed"] is False
    assert status["install_command"]
    out = cli_install.install_connector_cli("obsidian-cli")
    assert out["ok"] is False
    assert out["install_command"]
    assert "npm install" not in out["error"]
    assert out["install_command"] in out["error"]


def test_linux_obsidian_install_copies_into_user_bin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(cli_install.sys, "platform", "linux")
    monkeypatch.setattr(cli_install.os, "name", "posix")
    monkeypatch.setattr(cli_install, "_prefix_writable", lambda _prefix: True)
    source = "/opt/Obsidian/obsidian-cli"
    dest = cli_install._obsidian_install_destination(source)
    assert dest == os.path.join(str(tmp_path), ".local", "bin", "obsidian")
    command = cli_install.obsidian_install_command(source, dest)
    assert "cp " in command
    assert "chmod 755" in command
    assert "ln -s" not in command
    assert source in command


def test_macos_obsidian_install_symlinks_system_bin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_install.sys, "platform", "darwin")
    monkeypatch.setattr(cli_install.os, "name", "posix")
    monkeypatch.setattr(cli_install.os.path, "isdir", lambda path: path == "/usr/local/bin")
    monkeypatch.setattr(cli_install, "_prefix_writable", lambda _prefix: True)
    source = "/Applications/Obsidian.app/Contents/MacOS/obsidian-cli"
    dest = cli_install._obsidian_install_destination(source)
    assert dest == os.path.join("/usr/local/bin", "obsidian")
    command = cli_install.obsidian_install_command(source, dest)
    assert command.startswith("ln -sfn ")
    assert source in command


def test_windows_obsidian_com_stays_beside_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    home = tmp_path / "home"
    source = tmp_path / "Obsidian" / "Obsidian.com"
    source.parent.mkdir()
    source.write_text("redirector", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(cli_install.os, "name", "nt")
    monkeypatch.setattr(cli_install.sys, "platform", "win32")
    monkeypatch.setattr(cli_install, "obsidian_bundle_candidates", lambda: [str(source)])
    monkeypatch.setattr(cli_install, "_read_version", lambda _path: "1.12.7")

    def _which(name: str) -> str | None:
        if name != "obsidian":
            return None
        for part in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(part, "Obsidian.com")
            if os.path.isfile(candidate):
                return candidate
        return None

    monkeypatch.setattr(cli_install.shutil, "which", _which)
    out = cli_install.install_connector_cli("obsidian-cli")
    assert out["ok"] is True
    assert out["installed"] is True
    assert out["binary_path"] == str(source)
    assert out["version"] == "1.12.7"
    assert "copy /Y" not in out["install_command"]
    assert str(source.parent) in out["install_command"]
    assert not (home / ".local" / "bin" / "obsidian.exe").exists()
    assert not (home / ".local" / "bin" / "Obsidian.com").exists()


def test_windows_bundle_candidates_use_redirector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_install.os, "name", "nt")
    monkeypatch.setattr(cli_install.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\a\AppData\Local")
    monkeypatch.setenv("PROGRAMFILES", r"C:\Program Files")
    paths = cli_install.obsidian_bundle_candidates()
    assert paths[0] == os.path.join(r"C:\Users\a\AppData\Local", "Obsidian", "Obsidian.com")
    assert os.path.join(r"C:\Program Files", "Obsidian", "obsidian-cli.exe") in paths
    assert all(os.path.basename(path).lower() != "obsidian.exe" for path in paths)


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
