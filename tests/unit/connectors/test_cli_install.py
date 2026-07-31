"""Unit tests for connector host CLI install helper."""

from __future__ import annotations

from typing import Any

import pytest

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
    monkeypatch.setattr(cli_install.shutil, "which", lambda name: f"/usr/bin/{name}")
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


def test_install_runs_npm(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    state = {"installed": False}

    def _which(name: str) -> str | None:
        if name == "npm":
            return "/usr/bin/npm"
        if name in ("lark-cli", "wecom-cli"):
            return f"/usr/bin/{name}" if state["installed"] else None
        return None

    def _run(argv: list[str], **kwargs: Any) -> Any:
        del kwargs
        calls.append(list(argv))
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
    assert calls and calls[0][:3] == ["/usr/bin/npm", "install", "-g"]
