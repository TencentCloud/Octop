"""Signed-in list routes must not return stored provider credentials."""

from __future__ import annotations

from types import SimpleNamespace

from octop.api.routers.providers import _public_row
from octop.api.routers.voice import _public_voice_row


def test_public_provider_row_hides_api_key() -> None:
    row = SimpleNamespace(
        id=1,
        name="openai",
        kind="openai",
        base_url="https://example.test/v1",
        api_key="sk-secret",
        note=None,
        enabled=True,
        get_models=lambda: [],
    )
    data = _public_row(row)
    assert data["api_key"] is None
    assert data["api_key_set"] is True


def test_public_voice_row_hides_credentials() -> None:
    row = SimpleNamespace(
        id=2,
        name="tencent",
        kind="tencent",
        capability="tts",
        base_url=None,
        api_key="sid:skey",
        note=None,
        enabled=True,
        get_extra=lambda: {"secret_id": "sid", "secret_key": "skey", "region": "ap-guangzhou"},
    )
    data = _public_voice_row(row)
    assert data["api_key"] is None
    assert data["api_key_set"] is True
    assert data["extra"]["secret_key"] is None
    assert data["extra"]["secret_id"] is None
    assert data["extra"]["region"] == "ap-guangzhou"
