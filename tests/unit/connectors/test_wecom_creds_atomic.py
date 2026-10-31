"""WeCom CLI credential materialization: key durability and cache fast path."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from octop.infra.connectors.gateway.wecom_creds import materialize_wecom_bot_config

_ITEMS = [
    {
        "url": "https://example.com/mcp/doc",
        "type": "streamable-http",
        "is_authed": False,
        "biz_type": "doc",
    }
]


def _materialize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_fetch(*, bot_id: str, bot_secret: str) -> list[dict[str, Any]]:
        return _ITEMS

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.wecom_creds._fetch_mcp_config",
        _fake_fetch,
    )
    materialize_wecom_bot_config(tmp_path, bot_id="bid", bot_secret="bsec")


def test_materialize_repairs_lost_encryption_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _materialize(tmp_path, monkeypatch)
    key_path = tmp_path / ".encryption_key"
    # Simulate a torn/truncated key write: encrypted cache and marker stay valid.
    key_path.write_text("torn\n", encoding="utf-8")

    _materialize(tmp_path, monkeypatch)

    key_text = key_path.read_text(encoding="utf-8").strip()
    assert len(key_text) == 44
    key = base64.b64decode(key_text)
    bot_raw = (tmp_path / "bot.enc").read_bytes()
    assert json.loads(AESGCM(key).decrypt(bot_raw[:12], bot_raw[12:], None))["id"] == "bid"
    mcp_raw = (tmp_path / "mcp_config.enc").read_bytes()
    assert json.loads(AESGCM(key).decrypt(mcp_raw[:12], mcp_raw[12:], None)) == _ITEMS


def test_failed_repair_does_not_keep_stale_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _materialize(tmp_path, monkeypatch)
    (tmp_path / ".encryption_key").write_text("torn\n", encoding="utf-8")

    def _boom(*, bot_id: str, bot_secret: str) -> list[dict[str, Any]]:
        raise ValueError("simulated get_mcp_config failure")

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.wecom_creds._fetch_mcp_config",
        _boom,
    )
    with pytest.raises(ValueError, match="simulated get_mcp_config failure"):
        materialize_wecom_bot_config(tmp_path, bot_id="bid", bot_secret="bsec")

    assert not (tmp_path / ".octop_wecom_fingerprint").exists()


def test_key_write_is_atomic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_fetch(*, bot_id: str, bot_secret: str) -> list[dict[str, Any]]:
        return _ITEMS

    monkeypatch.setattr(
        "octop.infra.connectors.gateway.wecom_creds._fetch_mcp_config",
        _fake_fetch,
    )

    def _raise_swap_failure(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated failure during swap")

    monkeypatch.setattr("os.replace", _raise_swap_failure)
    with pytest.raises(OSError, match="simulated failure during swap"):
        materialize_wecom_bot_config(tmp_path, bot_id="bid", bot_secret="bsec")

    assert list(tmp_path.iterdir()) == []
