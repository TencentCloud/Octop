"""Voice probe (test_stt/test_tts) behavior per provider kind.

Success paths must stay untouched; failure paths must return
``{"ok": false, "error": ...}`` instead of raising into a 500.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest

import octop.infra.voice.adapters as voice_adapters
from octop.infra.db.repos.voice_providers import VoiceProviderRow
from octop.infra.voice.adapters import STTResult
from octop.infra.voice.adapters import test_stt as probe_stt
from octop.infra.voice.adapters import test_tts as probe_tts


def _row(
    *,
    kind: str,
    api_key: str | None = "k",
    extra: dict[str, Any] | None = None,
) -> VoiceProviderRow:
    return VoiceProviderRow(
        id=1,
        name=f"{kind}-probe",
        kind=kind,
        capability="both",
        base_url=None,
        api_key=api_key,
        extra_json=json.dumps(extra) if extra else None,
        note=None,
        enabled=1,
        created_at=0,
        updated_at=0,
    )


def _stream(*chunks: bytes) -> Callable[..., AsyncIterator[bytes]]:
    async def fake(row: VoiceProviderRow, text: str, *, voice_id: str | None, speed: float):
        for chunk in chunks:
            yield chunk

    return fake


def _raising(exc: Exception) -> Callable[..., AsyncIterator[bytes]]:
    async def fake(row: VoiceProviderRow, text: str, *, voice_id: str | None, speed: float):
        raise exc
        yield b""  # pragma: no cover

    return fake


TENCENT_EXTRA = {"secret_id": "sid", "secret_key": "sk", "region": "ap-guangzhou"}


@pytest.mark.asyncio
async def test_browser_probe_stays_offline() -> None:
    assert await probe_stt(None, "browser") == {"ok": True, "mode": "browser"}
    assert await probe_tts(None, "browser") == {"ok": True, "mode": "browser"}


@pytest.mark.asyncio
async def test_missing_row_is_reported() -> None:
    assert await probe_stt(None, "openai") == {"ok": False, "error": "provider not configured"}
    assert await probe_tts(None, "mimo") == {"ok": False, "error": "provider not configured"}


async def _stt_ok(row: VoiceProviderRow, audio: bytes, *, mime: str, language: str) -> STTResult:
    return STTResult(text="")


@pytest.mark.asyncio
async def test_openai_and_mimo_keep_api_key_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(voice_adapters, "synthesize_openai", _stream(b"audio"))
    monkeypatch.setattr(voice_adapters, "synthesize_mimo", _stream(b"audio"))
    monkeypatch.setattr(voice_adapters, "transcribe_openai", _stt_ok)
    monkeypatch.setattr(voice_adapters, "transcribe_mimo", _stt_ok)
    for kind in ("openai", "mimo"):
        assert await probe_stt(_row(kind=kind, api_key=None), kind) == {
            "ok": False,
            "error": "API credentials missing",
        }
        assert await probe_tts(_row(kind=kind, api_key=None), kind) == {
            "ok": False,
            "error": "API credentials missing",
        }
        assert await probe_stt(_row(kind=kind), kind) == {"ok": True, "mode": kind}
        assert await probe_tts(_row(kind=kind), kind) == {"ok": True, "bytes": 5}


@pytest.mark.asyncio
async def test_edge_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voice_adapters, "synthesize_edge", _stream(b"a", b"bb"))
    assert await probe_tts(None, "edge") == {"ok": True, "bytes": 3}
    monkeypatch.setattr(voice_adapters, "synthesize_edge", _raising(RuntimeError("edge down")))
    assert await probe_tts(None, "edge") == {"ok": False, "error": "edge down"}


@pytest.mark.asyncio
async def test_tencent_credentials_from_extra_are_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(voice_adapters, "transcribe_tencent", _stt_ok)
    row = _row(kind="tencent", api_key=None, extra=TENCENT_EXTRA)
    assert await probe_stt(row, "tencent") == {"ok": True, "mode": "tencent"}


@pytest.mark.asyncio
async def test_tencent_incomplete_credentials_are_reported_without_network() -> None:
    expected = {"ok": False, "error": "Tencent Cloud requires secret_id and secret_key"}
    assert await probe_stt(_row(kind="tencent", api_key="no-colon"), "tencent") == expected
    assert (
        await probe_tts(_row(kind="tencent", api_key=None, extra={"secret_id": "sid"}), "tencent")
        == expected
    )


@pytest.mark.asyncio
async def test_tencent_provider_error_is_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        voice_adapters,
        "synthesize_tencent",
        _raising(RuntimeError("AuthFailure.SecretIdNotFound: The SecretId is not found.")),
    )
    row = _row(kind="tencent", api_key="sid:sk", extra=TENCENT_EXTRA)
    assert await probe_tts(row, "tencent") == {
        "ok": False,
        "error": "SecretId was not found. Check that the key is correct.",
    }
    assert await probe_tts(row, "tencent", locale="zh") == {
        "ok": False,
        "error": "SecretId 不存在，请检查密钥是否填写正确。",
    }


@pytest.mark.asyncio
async def test_tencent_network_errors_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row(kind="tencent", api_key="sid:sk", extra=TENCENT_EXTRA)
    monkeypatch.setattr(voice_adapters, "synthesize_tencent", _raising(httpx.ConnectError("boom")))
    assert await probe_tts(row, "tencent") == {"ok": False, "error": "network error: ConnectError"}

    request = httpx.Request("POST", "https://tts.tencentcloudapi.com/")
    response = httpx.Response(500, request=request)
    monkeypatch.setattr(
        voice_adapters,
        "synthesize_tencent",
        _raising(httpx.HTTPStatusError("server error", request=request, response=response)),
    )
    assert await probe_tts(row, "tencent") == {"ok": False, "error": "provider returned HTTP 500"}


@pytest.mark.asyncio
async def test_tencent_success_path_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voice_adapters, "synthesize_tencent", _stream(b"mp3data"))
    row = _row(kind="tencent", api_key="sid:sk", extra=TENCENT_EXTRA)
    assert await probe_tts(row, "tencent") == {"ok": True, "bytes": 7}
