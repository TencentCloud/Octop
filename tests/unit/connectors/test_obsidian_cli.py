"""Obsidian CLI gateway adapter: vault scoping and command allowlist."""

from __future__ import annotations

from typing import Any

import pytest

from octop.infra.connectors.gateway import cli_install
from octop.infra.connectors.gateway.adapters import obsidian_cli


def _patch_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        obsidian_cli,
        "locate_obsidian_binary",
        lambda _explicit=None: "obsidian-bin",
    )


def test_search_argv_is_scoped_to_instance_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def _run(argv: list[str], **_kwargs: Any) -> str:
        seen["argv"] = argv
        return "[]"

    _patch_binary(monkeypatch)
    monkeypatch.setattr(obsidian_cli, "run_cli", _run)
    out = obsidian_cli.call_tool(
        {"vault": "My Vault"},
        "search",
        {"query": "meeting", "vault": "Other", "limit": 5},
    )
    assert out == "[]"
    argv = seen["argv"]
    assert argv[0] == "obsidian-bin"
    assert argv[1] == "vault=My Vault"
    assert argv[2] == "search"
    assert "query=meeting" in argv
    assert "format=json" in argv
    assert "limit=5" in argv
    assert not any(part.startswith("vault=Other") for part in argv)


def test_help_rejects_eval_and_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("denied commands must not reach the CLI")

    _patch_binary(monkeypatch)
    monkeypatch.setattr(obsidian_cli, "run_cli", _run)
    with pytest.raises(ValueError, match="不允许执行"):
        obsidian_cli.call_tool({"vault": "Notes"}, "help", {"command": "eval"})
    with pytest.raises(ValueError, match="不允许执行"):
        obsidian_cli.call_tool({"vault": "Notes"}, "help", {"command": "delete"})
    with pytest.raises(ValueError, match="不允许执行"):
        obsidian_cli.call_tool({"vault": "Notes"}, "help", {"command": "dev:screenshot"})


def test_search_rejects_newline_query(monkeypatch: pytest.MonkeyPatch) -> None:
    def _run(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("should not run")

    _patch_binary(monkeypatch)
    monkeypatch.setattr(obsidian_cli, "run_cli", _run)
    with pytest.raises(ValueError, match="换行"):
        obsidian_cli.call_tool({"vault": "Notes"}, "search", {"query": "a\nb"})


def test_probe_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_install.shutil, "which", lambda _name: None)
    monkeypatch.setattr(cli_install, "obsidian_bundle_candidates", lambda: [])
    with pytest.raises(ValueError, match="未找到 Obsidian CLI"):
        obsidian_cli.probe_credentials({"vault": "Notes"})


def test_probe_unknown_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_binary(monkeypatch)

    def _run(argv: list[str], **_kwargs: Any) -> str:
        assert argv[:3] == ["obsidian-bin", "vault=Missing", "vault"]
        raise ValueError("Unknown vault Missing")

    monkeypatch.setattr(obsidian_cli, "run_cli", _run)
    with pytest.raises(ValueError, match="找不到库"):
        obsidian_cli.probe_credentials({"vault": "Missing"})


def test_probe_app_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_binary(monkeypatch)

    def _run(*_args: object, **_kwargs: object) -> str:
        raise ValueError("Obsidian is not running")

    monkeypatch.setattr(obsidian_cli, "run_cli", _run)
    with pytest.raises(ValueError, match="未在运行"):
        obsidian_cli.probe_credentials({"vault": "Notes"})
