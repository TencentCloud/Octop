"""Live STT probe: test_stt performs a real recognition call per provider.

Credential/config failures and provider errors must be reported as
``{"ok": false, "error": ...}``, never raised into a 500.
"""

from __future__ import annotations

import json
import struct
from collections.abc import Callable
from typing import Any

import httpx
import pytest

import octop.infra.voice.adapters as voice_adapters
from octop.infra.db.repos.voice_providers import VoiceProviderRow
from octop.infra.voice.adapters import STTResult, _probe_tone_wav
from octop.infra.voice.adapters import test_stt as probe_stt


def _row(*, kind: str, api_key: str | None = "k", extra: dict[str, Any] | None = None):
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


def _stt(*result: STTResult) -> Callable[..., Any]:
    async def fake(row: VoiceProviderRow, audio: bytes, *, mime: str, language: str):
        return result[0] if result else STTResult(text="")

    return fake


def _stt_raising(exc: Exception) -> Callable[..., Any]:
    async def fake(row: VoiceProviderRow, audio: bytes, *, mime: str, language: str):
        raise exc

    return fake


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("transcribe_openai", "transcribe_tencent", "transcribe_mimo"):
        monkeypatch.setattr(voice_adapters, name, _stt_raising(AssertionError("network used")))


TENCENT_EXTRA = {"secret_id": "sid", "secret_key": "sk", "region": "ap-guangzhou"}


def test_probe_tone_wav_is_valid_pcm16() -> None:
    wav = _probe_tone_wav()
    riff, size, wave, fmt, fmt_len, audio_fmt, channels, rate = struct.unpack_from(
        "<4sI4s4sIHHI", wav, 0
    )
    assert (riff, wave, fmt) == (b"RIFF", b"WAVE", b"fmt ")
    assert size == 36 + len(wav) - 44
    assert (audio_fmt, channels, rate) == (1, 1, 16000)
    assert len(wav) == 44 + 16000 * 2


@pytest.mark.asyncio
async def test_browser_and_missing_row_stay_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_network(monkeypatch)
    assert await probe_stt(None, "browser") == {"ok": True, "mode": "browser"}
    assert await probe_stt(None, "openai") == {"ok": False, "error": "provider not configured"}


@pytest.mark.asyncio
async def test_edge_and_unknown_kinds_stay_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_network(monkeypatch)
    assert await probe_stt(_row(kind="edge"), "edge") == {"ok": True, "mode": "edge"}
    assert await probe_stt(_row(kind="wat"), "wat") == {"ok": True, "mode": "wat"}


@pytest.mark.asyncio
async def test_credential_errors_are_reported_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _block_network(monkeypatch)
    assert await probe_stt(_row(kind="openai", api_key=None), "openai") == {
        "ok": False,
        "error": "API credentials missing",
    }
    tencent = _row(kind="tencent", api_key="no-colon")
    result = await probe_stt(tencent, "tencent")
    assert result == {"ok": False, "error": "Tencent Cloud requires secret_id and secret_key"}


@pytest.mark.asyncio
async def test_live_success_per_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    for kind in ("openai", "tencent", "mimo"):
        monkeypatch.setattr(voice_adapters, f"transcribe_{kind}", _stt(STTResult(text="")))
        row = _row(kind=kind, extra=TENCENT_EXTRA if kind == "tencent" else None)
        assert await probe_stt(row, kind) == {"ok": True, "mode": kind}


@pytest.mark.asyncio
async def test_provider_error_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        voice_adapters,
        "transcribe_tencent",
        _stt_raising(RuntimeError("UnsupportedOperation.ServerNotOpen: ASR service is not open.")),
    )
    row = _row(kind="tencent", api_key="sid:sk", extra=TENCENT_EXTRA)
    assert await probe_stt(row, "tencent") == {
        "ok": False,
        "error": "This Tencent Cloud voice service is not enabled for the account.",
    }
    assert await probe_stt(row, "tencent", locale="zh") == {
        "ok": False,
        "error": "当前腾讯云账号尚未开通该语音服务。",
    }


@pytest.mark.asyncio
async def test_network_errors_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row(kind="mimo")
    monkeypatch.setattr(voice_adapters, "transcribe_mimo", _stt_raising(httpx.ConnectError("boom")))
    assert await probe_stt(row, "mimo") == {"ok": False, "error": "network error: ConnectError"}

    request = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
    response = httpx.Response(503, request=request)
    monkeypatch.setattr(
        voice_adapters,
        "transcribe_openai",
        _stt_raising(httpx.HTTPStatusError("down", request=request, response=response)),
    )
    assert await probe_stt(row, "openai") == {"ok": False, "error": "provider returned HTTP 503"}
