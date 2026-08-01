"""Unit tests for Feishu CLI user device-code auth."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.support.fakes import fake_bin_path

from octop.infra.connectors.gateway import feishu_creds, feishu_user_auth


def test_start_user_login_parses_device_flow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def _fake_run(
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_s: float = 30.0,
        cwd: str | None = None,
        stdin_text: str | None = None,
    ) -> str:
        del timeout_s, cwd, stdin_text
        calls.append(list(argv))
        if argv[1:3] == ["config", "init"]:
            return "{}"
        if argv[1:3] == ["config", "default-as"]:
            return "ok"
        if argv[1:3] == ["auth", "login"] and "--no-wait" in argv:
            return json.dumps(
                {
                    "device_code": "DEVCODE",
                    "expires_in": 600,
                    "verification_url": "https://accounts.feishu.cn/oauth/v1/device/verify?x=1",
                    "hint": "scan me",
                }
            )
        raise AssertionError(argv)

    monkeypatch.setattr(feishu_user_auth, "run_cli", _fake_run)
    monkeypatch.setattr(feishu_creds, "run_cli", _fake_run)
    monkeypatch.setattr(feishu_creds, "resolve_binary", lambda _n: fake_bin_path("lark-cli"))

    out = feishu_user_auth.start_user_device_login(
        config_dir=tmp_path,
        app_id="cli_x",
        app_secret="sec",
    )
    assert out["device_code"] == "DEVCODE"
    assert out["verification_url"].startswith("https://accounts.feishu.cn/")
    assert out["expires_in"] == 600
    login = next(c for c in calls if c[1:3] == ["auth", "login"] and "--no-wait" in c)
    assert "--json" in login
    # Full domain scopes (not --recommend-only): docs +search needs search:docs:read
    assert "--domain" in login and "all" in login
    assert "--recommend" not in login
    assert "--scope" in login
    scope_idx = login.index("--scope")
    assert "search:docs:read" in login[scope_idx + 1]


def test_complete_user_login_sets_default_as_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def _fake_run(
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_s: float = 30.0,
        cwd: str | None = None,
        stdin_text: str | None = None,
    ) -> str:
        del timeout_s, cwd, stdin_text, env
        calls.append(list(argv))
        if argv[1:3] == ["config", "init"]:
            return "{}"
        if argv[1:3] == ["auth", "login"] and "--device-code" in argv:
            return json.dumps({"ok": True})
        if argv[1:4] == ["config", "default-as", "user"]:
            return "Default identity set to: user"
        if argv[1:3] == ["auth", "status"]:
            return json.dumps(
                {
                    "identity": "user",
                    "defaultAs": "user",
                    "identities": {
                        "bot": {"available": True},
                        "user": {"available": True, "status": "valid"},
                    },
                }
            )
        if argv[1:3] == ["auth", "check"]:
            return json.dumps({"ok": True})
        if argv[1:3] == ["config", "default-as"]:
            return "ok"
        raise AssertionError(argv)

    monkeypatch.setattr(feishu_user_auth, "run_cli", _fake_run)
    monkeypatch.setattr(feishu_creds, "run_cli", _fake_run)
    monkeypatch.setattr(feishu_creds, "resolve_binary", lambda _n: fake_bin_path("lark-cli"))

    out = feishu_user_auth.complete_user_device_login(
        config_dir=tmp_path,
        app_id="cli_x",
        app_secret="sec",
        device_code="DEVCODE",
    )
    assert out["ok"] is True
    assert out["identity"] == "user"
    assert out["user_available"] is True
    assert out["search_docs_scope"] is True
    assert any(c[1:4] == ["config", "default-as", "user"] for c in calls)


def test_ensure_feishu_respects_default_as_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def _fake_run(
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout_s: float = 30.0,
        cwd: str | None = None,
        stdin_text: str | None = None,
    ) -> str:
        del timeout_s, cwd, stdin_text, env
        calls.append(list(argv))
        return "{}"

    monkeypatch.setattr(feishu_creds, "run_cli", _fake_run)
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    # Pretend already initialized with matching fingerprint
    from octop.infra.connectors.gateway.cli_fingerprint import credential_fingerprint

    fp = credential_fingerprint("cli_x", "sec")
    (tmp_path / ".octop_feishu_fingerprint").write_text(fp + "\n", encoding="utf-8")

    feishu_creds.ensure_feishu_cli_config(
        tmp_path,
        binary=fake_bin_path("lark-cli"),
        app_id="cli_x",
        app_secret="sec",
        env={},
        default_as="user",
    )
    assert any(c[1:4] == ["config", "default-as", "user"] for c in calls)
    assert not any(c[1:4] == ["config", "default-as", "bot"] for c in calls)
