"""HTTP glue for the live STT probe: provider errors surface as ok:false."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

import octop.infra.voice.adapters as voice_adapters

TENCENT_EXTRA = {"secret_id": "sid", "secret_key": "sk", "region": "ap-guangzhou"}


def _raising(exc: Exception) -> Any:
    async def fake(row: Any, audio: bytes, *, mime: str, language: str) -> Any:
        raise exc

    return fake


async def test_probe_stt_reports_provider_error_over_http(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _srv, auth = env
    monkeypatch.setattr(
        voice_adapters,
        "transcribe_tencent",
        _raising(RuntimeError("AuthFailure.SecretIdNotFound: The SecretId is not found.")),
    )

    r = await client.post(
        "/api/admin/voice/providers/test-configuration",
        headers={**auth, "Accept-Language": "zh"},
        json={
            "name": "tencent-asr",
            "kind": "tencent",
            "capability": "both",
            "api_key": "sid:sk",
            "extra_json": json.dumps(TENCENT_EXTRA),
            "mode": "stt",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"] == "SecretId 不存在，请检查密钥是否填写正确。"


async def test_probe_stt_success_over_http(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.voice.adapters import STTResult

    async def fake(row: Any, audio: bytes, *, mime: str, language: str) -> STTResult:
        assert mime == "audio/wav"
        return STTResult(text="")

    client, _srv, auth = env
    monkeypatch.setattr(voice_adapters, "transcribe_tencent", fake)

    r = await client.post(
        "/api/admin/voice/providers/test-configuration",
        headers=auth,
        json={
            "name": "tencent-asr",
            "kind": "tencent",
            "capability": "both",
            "api_key": "sid:sk",
            "extra_json": json.dumps(TENCENT_EXTRA),
            "mode": "stt",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "mode": "tencent"}
