"""Unit tests for WeCom CLI error humanization and probe."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.support.fakes import fake_bin_path

from octop.infra.connectors.gateway.adapters import wecom_cli


def test_humanize_strips_init_hint() -> None:
    msg = wecom_cli._humanize_cli_error(  # noqa: SLF001
        "未找到 MCP 配置缓存，请先运行 `wecom-cli init`"
    )
    assert "Bot ID" in msg or "Secret" in msg
    assert "wecom-cli" not in msg
    assert "终端命令" in msg or "禁止" in msg


def test_humanize_passes_business_permission_errors() -> None:
    raw = "Error: 当前企业暂不支持授权机器人「日程」使用权限"
    assert wecom_cli._humanize_cli_error(raw) == raw  # noqa: SLF001


def test_humanize_unrecognized_method_not_bad_creds() -> None:
    raw = (
        "error: unrecognized subcommand 'list'\n\n"
        "Usage: wecom-cli doc [COMMAND]\n\n"
        "For more information, try '--help'."
    )
    msg = wecom_cli._humanize_cli_error(raw)  # noqa: SLF001
    assert "凭证无效" not in msg
    assert "MCP 配置未就绪" not in msg
    assert "wecom-cli" not in msg
    assert "list" in msg or "方法" in msg or "method" in msg.lower()


def test_call_tool_humanizes_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wecom_cli.resolve_binary",
        lambda _n: fake_bin_path("wecom-cli"),
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wecom_cli.materialize_wecom_bot_config",
        lambda *a, **k: None,
    )

    def _fake_run(*_a: Any, **_k: Any) -> str:
        raise ValueError("请先运行 `wecom-cli init`")

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wecom_cli.run_cli",
        _fake_run,
    )
    with pytest.raises(ValueError, match="Bot") as ei:
        wecom_cli.call_tool(
            {"bot_id": "b1", "bot_secret": "s1", "instance_id": "i1"},
            "doc",
            {"method": "create_doc", "args": {}},
        )
    assert "wecom-cli" not in str(ei.value)


def test_probe_requires_non_empty_mcp_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wecom_cli.resolve_binary",
        lambda _n: fake_bin_path("wecom-cli"),
    )

    def _materialize(config_dir: Path, *, bot_id: str, bot_secret: str) -> None:
        del bot_id, bot_secret
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "mcp_config.enc").write_bytes(b"not-a-valid-enc")
        (config_dir / "bot.enc").write_bytes(b"x")

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wecom_cli.materialize_wecom_bot_config",
        _materialize,
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wecom_cli.read_mcp_items_count",
        lambda _dir: 0,
    )
    with pytest.raises(ValueError, match="MCP"):
        wecom_cli.probe_credentials({"bot_id": "b1", "bot_secret": "s1", "instance_id": "i1"})


def test_probe_ok_with_mcp_items(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wecom_cli.resolve_binary",
        lambda _n: fake_bin_path("wecom-cli"),
    )

    def _materialize(config_dir: Path, *, bot_id: str, bot_secret: str) -> None:
        del bot_id, bot_secret
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "mcp_config.enc").write_bytes(b"ok")

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wecom_cli.materialize_wecom_bot_config",
        _materialize,
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wecom_cli.read_mcp_items_count",
        lambda _dir: 2,
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wecom_cli.run_cli",
        lambda *_a, **_k: "usage: wecom-cli doc",
    )
    wecom_cli.probe_credentials({"bot_id": "b1", "bot_secret": "s1", "instance_id": "i1"})
