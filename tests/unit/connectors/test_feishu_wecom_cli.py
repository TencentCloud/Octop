"""Unit tests for Feishu / WeCom CLI gateway adapters."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from octop.infra.connectors.builder import validate_create_credentials
from octop.infra.connectors.catalog import get_catalog_entry
from octop.infra.connectors.gateway.adapters import feishu_cli, wecom_cli
from octop.infra.connectors.gateway.wecom_creds import materialize_wecom_bot_config


def test_catalog_entries_registered() -> None:
    feishu = get_catalog_entry("feishu-cli")
    wecom = get_catalog_entry("wecom-cli")
    assert feishu is not None and feishu.mcp_mode == "gateway"
    assert wecom is not None and wecom.mcp_mode == "gateway"


def test_validate_feishu_and_wecom_credentials() -> None:
    feishu = validate_create_credentials(
        "feishu-cli",
        {"app_secret": "sec", "app_id": "cli_xxx"},
    )
    assert feishu["app_id"] == "cli_xxx"
    assert feishu["app_secret"] == "sec"
    assert "internal_token" in feishu
    assert "cli_config_key" in feishu
    assert feishu["cli_config_key"]
    assert "api_key" not in feishu

    wecom = validate_create_credentials(
        "wecom-cli",
        {"bot_secret": "secret", "bot_id": "bot_xxx"},
    )
    assert wecom["bot_id"] == "bot_xxx"
    assert wecom["bot_secret"] == "secret"
    assert "cli_config_key" in wecom
    assert wecom["cli_config_key"]
    assert "api_key" not in wecom

    # Legacy payload still accepted (api_key as secret)
    legacy = validate_create_credentials(
        "feishu-cli",
        {"api_key": "legacy-sec", "app_id": "cli_yyy"},
    )
    assert legacy["app_secret"] == "legacy-sec"


def test_wecom_materialize_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    items = [
        {
            "url": "https://example.com/mcp/doc",
            "type": "streamable-http",
            "is_authed": False,
            "biz_type": "doc",
        }
    ]

    def _fake_fetch(*, bot_id: str, bot_secret: str) -> list[dict[str, Any]]:
        assert bot_id == "bid"
        assert bot_secret == "bsec"
        return items

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.wecom_creds._fetch_mcp_config",
        _fake_fetch,
    )
    materialize_wecom_bot_config(tmp_path, bot_id="bid", bot_secret="bsec")
    key_b64 = (tmp_path / ".encryption_key").read_text(encoding="utf-8").strip()
    key = base64.b64decode(key_b64)
    raw = (tmp_path / "bot.enc").read_bytes()
    nonce, ct = raw[:12], raw[12:]
    plain = AESGCM(key).decrypt(nonce, ct, None)
    bot = json.loads(plain.decode("utf-8"))
    assert bot["id"] == "bid"
    assert bot["secret"] == "bsec"
    mcp_raw = (tmp_path / "mcp_config.enc").read_bytes()
    mcp_plain = AESGCM(key).decrypt(mcp_raw[:12], mcp_raw[12:], None)
    assert json.loads(mcp_plain.decode("utf-8")) == items


def test_feishu_prepare_avoids_external_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setenv("LARKSUITE_CLI_APP_ID", "should-be-cleared")
    monkeypatch.setenv("LARKSUITE_CLI_APP_SECRET", "should-be-cleared")
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.feishu_cli.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )
    calls: list[dict[str, Any]] = []

    def _fake_ensure(
        config_dir: Path,
        *,
        binary: str,
        app_id: str,
        app_secret: str,
        env: dict[str, str],
        default_as: str = "bot",
    ) -> None:
        calls.append(
            {
                "config_dir": config_dir,
                "binary": binary,
                "app_id": app_id,
                "app_secret": app_secret,
                "env": env,
                "default_as": default_as,
            }
        )
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.ensure_feishu_cli_config",
        _fake_ensure,
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )

    env = feishu_cli._prepare_env(  # noqa: SLF001
        {"app_id": "cli_x", "app_secret": "sec", "instance_id": "i1"}
    )
    assert "LARKSUITE_CLI_APP_ID" not in env
    assert "LARKSUITE_CLI_APP_SECRET" not in env
    assert "LARKSUITE_CLI_CONFIG_DIR" in env
    assert len(calls) == 1
    assert calls[0]["app_id"] == "cli_x"
    assert calls[0]["default_as"] == "bot"


def test_wecom_doc_invokes_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wecom_cli.resolve_binary",
        lambda _name: "/usr/bin/wecom-cli",
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.wecom_creds._fetch_mcp_config",
        lambda **_kwargs: [
            {
                "url": "https://example.com/mcp/doc",
                "type": "streamable-http",
                "biz_type": "doc",
            }
        ],
    )

    def _fake_run(
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_s: float = 30.0,
        cwd: str | None = None,
        stdin_text: str | None = None,
    ) -> str:
        del timeout_s, cwd, stdin_text
        captured["argv"] = argv
        captured["env"] = env
        return '{"ok":true}'

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.wecom_cli.run_cli",
        _fake_run,
    )
    out = wecom_cli.call_tool(
        {"bot_id": "b1", "bot_secret": "s1", "instance_id": "inst1"},
        "doc",
        {"method": "create_doc", "args": {"doc_type": 3}},
    )
    assert out == '{"ok":true}'
    assert captured["argv"][:3] == ["/usr/bin/wecom-cli", "doc", "create_doc"]
    assert json.loads(captured["argv"][3]) == {"doc_type": 3}
    assert "WECOM_CLI_CONFIG_DIR" in (captured["env"] or {})
    cfg = Path(str((captured["env"] or {})["WECOM_CLI_CONFIG_DIR"]))
    assert (cfg / "bot.enc").is_file()
    assert (cfg / "mcp_config.enc").is_file()


def test_feishu_calendar_shortcut_flags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.feishu_cli.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.ensure_feishu_cli_config",
        lambda *a, **k: None,
    )

    def _fake_run(
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_s: float = 30.0,
        cwd: str | None = None,
        stdin_text: str | None = None,
    ) -> str:
        del timeout_s, cwd, stdin_text
        captured["argv"] = argv
        captured["env"] = env
        return '{"ok":true}'

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.feishu_cli.run_cli",
        _fake_run,
    )
    feishu_cli.call_tool(
        {"app_id": "a1", "app_secret": "s1", "instance_id": "i1"},
        "calendar",
        {"method": "+agenda", "args": {"days": 3}},
    )
    assert captured["argv"][:4] == [
        "/usr/bin/lark-cli",
        "calendar",
        "+agenda",
        "--format",
    ]
    assert "--as" in captured["argv"] and "bot" in captured["argv"]
    assert "--days" in captured["argv"]
    assert "3" in captured["argv"]
    env = captured["env"] or {}
    assert "LARKSUITE_CLI_APP_ID" not in env
    assert "LARKSUITE_CLI_APP_SECRET" not in env
    assert env["LARKSUITE_CLI_CONFIG_DIR"]


def test_probe_requires_bot_even_when_default_as_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.feishu_cli.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.ensure_feishu_cli_config",
        lambda *a, **k: None,
    )

    def _fake_run(
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_s: float = 30.0,
        cwd: str | None = None,
        stdin_text: str | None = None,
    ) -> str:
        del timeout_s, cwd, stdin_text, env
        assert argv[1:3] == ["auth", "status"]
        return json.dumps(
            {
                "identity": "user",
                "identities": {
                    "bot": {"available": False},
                    "user": {"available": True},
                },
            }
        )

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.feishu_cli.run_cli",
        _fake_run,
    )
    with pytest.raises(ValueError, match="App ID / App Secret"):
        feishu_cli.probe_credentials(
            {
                "app_id": "a1",
                "app_secret": "s1",
                "instance_id": "i1",
                "default_as": "user",
            }
        )


def test_tool_counts() -> None:
    assert {t["name"] for t in wecom_cli.list_tools()} == {
        "doc",
        "schedule",
        "msg",
        "help",
    }
    assert {t["name"] for t in feishu_cli.list_tools()} == {
        "doc",
        "base",
        "calendar",
        "im",
        "help",
    }


def test_docs_search_requires_user_auth_without_shell_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.feishu_cli.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.ensure_feishu_cli_config",
        lambda *a, **k: None,
    )
    called = False

    def _fake_run(*_a: Any, **_k: Any) -> str:
        nonlocal called
        called = True
        raise AssertionError("should not invoke CLI before user auth")

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.feishu_cli.run_cli",
        _fake_run,
    )
    with pytest.raises(ValueError, match="连接器") as ei:
        feishu_cli.call_tool(
            {"app_id": "a1", "app_secret": "s1", "instance_id": "i1"},
            "doc",
            {"method": "+search", "args": {"query": "q"}},
        )
    msg = str(ei.value)
    assert "lark-cli" not in msg
    assert called is False


def test_docs_search_uses_as_user(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.feishu_cli.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.ensure_feishu_cli_config",
        lambda *a, **k: None,
    )

    def _fake_run(
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_s: float = 30.0,
        cwd: str | None = None,
        stdin_text: str | None = None,
    ) -> str:
        del timeout_s, cwd, stdin_text, env
        captured.setdefault("calls", []).append(list(argv))
        if argv[1:3] == ["auth", "check"]:
            return '{"ok":true}'
        captured["argv"] = argv
        return '{"ok":true}'

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.feishu_cli.run_cli",
        _fake_run,
    )
    feishu_cli.call_tool(
        {
            "app_id": "a1",
            "app_secret": "s1",
            "instance_id": "i1",
            "default_as": "user",
        },
        "doc",
        {"method": "+search", "args": {"query": "计划"}},
    )
    assert captured["argv"][:3] == ["/usr/bin/lark-cli", "docs", "+search"]
    assert "--as" in captured["argv"]
    assert captured["argv"][captured["argv"].index("--as") + 1] == "user"
    assert "bot" not in captured["argv"]


def test_docs_search_missing_scope_message(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.feishu_cli.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.resolve_binary",
        lambda _name: "/usr/bin/lark-cli",
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.feishu_creds.ensure_feishu_cli_config",
        lambda *a, **k: None,
    )

    def _fake_run(
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_s: float = 30.0,
        cwd: str | None = None,
        stdin_text: str | None = None,
    ) -> str:
        del timeout_s, cwd, stdin_text, env
        if argv[1:3] == ["auth", "check"]:
            raise ValueError("missing required scope(s): search:docs:read")
        raise AssertionError(argv)

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.adapters.feishu_cli.run_cli",
        _fake_run,
    )
    with pytest.raises(ValueError, match="登录授权") as ei:
        feishu_cli.call_tool(
            {
                "app_id": "a1",
                "app_secret": "s1",
                "instance_id": "i1",
                "default_as": "user",
            },
            "doc",
            {"method": "+search", "args": {"query": "q"}},
        )
    assert "lark-cli" not in str(ei.value)


def test_humanize_missing_search_scope() -> None:
    msg = feishu_cli._humanize_cli_error(  # noqa: SLF001
        "missing required scope(s): search:docs:read"
        ' | run `lark-cli auth login --scope "search:docs:read"`'
    )
    assert "连接器" in msg
    assert "登录授权" in msg
    assert "lark-cli" not in msg
    assert "禁止" in msg


def test_humanize_rejects_bot_as_for_user_only_commands() -> None:
    msg = feishu_cli._humanize_cli_error(  # noqa: SLF001
        "--as bot is not supported, this command only supports: user"
        ' | run `lark-cli auth login --scope "search:docs:read"`'
    )
    assert "连接器" in msg
    assert "lark-cli" not in msg
    assert "auth login" not in msg
    assert "禁止" in msg
