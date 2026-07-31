"""Unit tests for CLI runner messages and connector-cli dir cleanup."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.connectors.gateway import cli_dirs, cli_runner


def test_resolve_binary_missing_does_not_suggest_npm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_runner.shutil, "which", lambda _name: None)
    with pytest.raises(ValueError, match="连接器") as ei:
        cli_runner.resolve_binary("lark-cli")
    msg = str(ei.value)
    assert "npm install" not in msg
    assert "lark-cli" in msg


def test_format_cli_error_strips_cli_hints() -> None:
    err = cli_runner._format_cli_error(  # noqa: SLF001
        1,
        "",
        '{"ok":false,"error":{"message":"missing scope","hint":"run `lark-cli auth login`"}}',
    )
    assert "missing scope" in err
    assert "lark-cli" not in err


def test_cleanup_removes_instance_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    from octop.infra.utils.paths import PathLayout

    layout = PathLayout.from_env()
    target = layout.ensure_connector_cli_instance_dir("feishu-cli", "inst1")
    (target / "config.json").write_text("{}", encoding="utf-8")
    assert target.is_dir()
    cli_dirs.remove_connector_cli_dirs("feishu-cli", "inst1", "unused")
    assert not target.exists()


def test_cleanup_keys_from_feishu_creds() -> None:
    keys = cli_dirs.cleanup_keys_for_creds(
        "feishu-cli",
        {
            "instance_id": "i1",
            "cli_config_key": "ck1",
            "app_id": "cli_x",
        },
    )
    assert keys == {"i1", "ck1"}


def test_cleanup_keys_from_wecom_creds() -> None:
    keys = cli_dirs.cleanup_keys_for_creds(
        "wecom-cli",
        {"instance_id": "i2", "bot_id": "botx", "cli_config_key": "ck2"},
    )
    # bot_id kept for cleaning legacy dirs; runtime must not use it as CONFIG_DIR key.
    assert keys == {"i2", "botx", "ck2"}


def test_resolve_cli_config_key_prefers_cli_then_instance() -> None:
    assert (
        cli_dirs.resolve_cli_config_key(
            {"cli_config_key": "ck1", "instance_id": "i1", "app_id": "cli_x"}
        )
        == "ck1"
    )
    assert cli_dirs.resolve_cli_config_key({"instance_id": "i1", "app_id": "cli_x"}) == "i1"


def test_resolve_cli_config_key_rejects_app_or_bot_fallback() -> None:
    with pytest.raises(ValueError, match="cli_config_key"):
        cli_dirs.resolve_cli_config_key({"app_id": "cli_x", "app_secret": "s"})
    with pytest.raises(ValueError, match="cli_config_key"):
        cli_dirs.resolve_cli_config_key({"bot_id": "botx", "bot_secret": "s"})
