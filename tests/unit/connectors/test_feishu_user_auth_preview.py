"""Unit tests for Feishu live user-auth preview."""

from __future__ import annotations

import pytest

from octop.infra.connectors.gateway import feishu_user_auth


def test_live_preview_missing_secret() -> None:
    out = feishu_user_auth.live_user_auth_preview({"app_id": "cli_x"})
    assert out["user_auth_valid"] is False
    assert out["user_auth_needs_reauth"] is True


def test_live_preview_maps_auth_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        feishu_user_auth,
        "prepare_feishu_cli_env",
        lambda *_a, **_k: ("/bin/lark-cli", {"LARKSUITE_CLI_CONFIG_DIR": "/x"}),
    )
    monkeypatch.setattr(
        feishu_user_auth,
        "read_auth_status",
        lambda **_k: {
            "identities": {
                "user": {
                    "available": True,
                    "tokenStatus": "valid",
                    "expiresAt": "2026-08-01T00:00:00Z",
                    "refreshExpiresAt": "2026-08-07T00:00:00Z",
                }
            }
        },
    )
    monkeypatch.setattr(
        feishu_user_auth,
        "_auth_has_scope",
        lambda **_k: True,
    )
    out = feishu_user_auth.live_user_auth_preview(
        {
            "app_id": "cli_x",
            "app_secret": "sec",
            "cli_config_key": "k1",
            "instance_id": "i1",
        }
    )
    assert out["user_auth_valid"] is True
    assert out["user_auth_needs_reauth"] is False
    assert out["search_docs_scope"] is True
    assert out["user_refresh_expires_at"] == "2026-08-07T00:00:00Z"


def test_live_preview_expired_needs_reauth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        feishu_user_auth,
        "prepare_feishu_cli_env",
        lambda *_a, **_k: ("/bin/lark-cli", {}),
    )
    monkeypatch.setattr(
        feishu_user_auth,
        "read_auth_status",
        lambda **_k: {
            "identities": {
                "user": {
                    "available": False,
                    "tokenStatus": "expired",
                }
            }
        },
    )
    out = feishu_user_auth.live_user_auth_preview(
        {"app_id": "cli_x", "app_secret": "sec", "cli_config_key": "k1"}
    )
    assert out["user_auth_needs_reauth"] is True
    assert out["user_auth_valid"] is False
