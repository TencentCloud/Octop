"""Unit tests for Mimo voice adapters (voice normalization + streaming TTS)."""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

import octop.infra.voice.adapters as voice_adapters
from octop.infra.db.repos.voice_providers import VoiceProviderRow
from octop.infra.voice.adapters import (
    MIMO_PRESET_VOICES,
    _normalize_mimo_voice,
    _wav_header,
    synthesize_mimo,
)


@pytest.fixture(autouse=True)
def _skip_mimo_url_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_guard(_base_url: str) -> None:
        return None

    monkeypatch.setattr(voice_adapters, "_guard_mimo_base_url", _fake_guard)


def _mimo_row(*, extra: dict[str, Any] | None = None) -> VoiceProviderRow:
    return VoiceProviderRow(
        id=1,
        name="mimo-tts",
        kind="mimo",
        capability="tts",
        base_url="https://api.xiaomimimo.com/v1",
        api_key="sk-test",
        extra_json=json.dumps(extra) if extra else None,
        note=None,
        enabled=1,
        created_at=0,
        updated_at=0,
    )


def _sse(*events: dict[str, Any]) -> bytes:
    out = []
    for event in events:
        payload = json.dumps(event)
        # Split each payload across two data lines to exercise multi-line joins.
        mid = len(payload) // 2
        out.append(f"data:{payload[:mid]}\n".encode())
        out.append(f"data:{payload[mid:]}\n\n".encode())
    out.append(b"data: [DONE]\n\n")
    return b"".join(out)


def _audio_event(pcm: bytes) -> dict[str, Any]:
    return {"choices": [{"delta": {"audio": {"data": base64.b64encode(pcm).decode("ascii")}}}]}


@pytest.fixture
def mock_mimo_http(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Install an httpx.MockTransport-backed AsyncClient inside adapters."""

    def install(handler: Any) -> None:
        original = httpx.AsyncClient

        def factory(**kwargs: Any) -> httpx.AsyncClient:
            kwargs["transport"] = httpx.MockTransport(handler)
            return original(**kwargs)

        monkeypatch.setattr(voice_adapters.httpx, "AsyncClient", factory)

    return install


class TestNormalizeMimoVoice:
    def test_legacy_default_maps_to_preset_voice(self) -> None:
        assert _normalize_mimo_voice("mimo_default") == "冰糖"

    def test_empty_falls_back_to_preset_voice(self) -> None:
        assert _normalize_mimo_voice("") == "冰糖"
        assert _normalize_mimo_voice(None) == "冰糖"

    def test_preset_voices_pass_through(self) -> None:
        for voice in MIMO_PRESET_VOICES:
            assert _normalize_mimo_voice(voice) == voice


class TestWavHeader:
    def test_header_is_pcm16_mono_24k(self) -> None:
        header = _wav_header(8)
        assert len(header) == 44
        assert header[0:4] == b"RIFF"
        assert header[8:12] == b"WAVE"
        assert header[36:40] == b"data"
        assert int.from_bytes(header[4:8], "little") == 36 + 8
        assert int.from_bytes(header[40:44], "little") == 8
        assert int.from_bytes(header[22:24], "little") == 1  # mono
        assert int.from_bytes(header[24:28], "little") == 24000
        assert int.from_bytes(header[34:36], "little") == 16  # bits

    def test_streaming_sentinel_does_not_overflow(self) -> None:
        header = _wav_header(0xFFFF_FFFF)
        assert len(header) == 44
        assert int.from_bytes(header[40:44], "little") == 0xFFFF_FFFF


class TestMimoTTSStreaming:
    async def test_streams_pcm_chunks_wrapped_in_wav(self, mock_mimo_http: Any) -> None:
        pcm_chunks = [b"\x01\x02" * 10, b"\x03\x04" * 6]
        requests: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse(*[_audio_event(p) for p in pcm_chunks]),
            )

        mock_mimo_http(handler)
        out = b"".join(
            [
                chunk
                async for chunk in synthesize_mimo(_mimo_row(), "你好", voice_id=None, speed=1.0)
            ]
        )
        assert out[:44] == _wav_header(0xFFFF_FFFF)
        assert out[44:] == b"".join(pcm_chunks)

    async def test_request_uses_streaming_pcm16_and_normalized_voice(
        self, mock_mimo_http: Any
    ) -> None:
        requests: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse(_audio_event(b"\x00\x01")),
            )

        mock_mimo_http(handler)
        async for _ in synthesize_mimo(
            _mimo_row(extra={"voice_id": "mimo_default"}), "hi", voice_id=None, speed=1.0
        ):
            pass
        assert requests, "handler must capture the outbound request"
        body = requests[0]
        assert body["stream"] is True
        assert body["audio"]["format"] == "pcm16"
        assert body["audio"]["voice"] == "冰糖"
        # TTS text rides in the assistant message per Mimo docs.
        assert body["messages"][1]["role"] == "assistant"
        assert body["messages"][1]["content"] == "hi"

    async def test_multiline_json_without_done_marker_is_ignored(self, mock_mimo_http: Any) -> None:
        # A truncated event followed by [DONE] must not raise.
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=b'data:{"choices":\ndata: [DONE]\n\n',
            )

        mock_mimo_http(handler)
        out = b"".join(
            [chunk async for chunk in synthesize_mimo(_mimo_row(), "x", voice_id=None, speed=1.0)]
        )
        assert out == _wav_header(0xFFFF_FFFF)  # header only, no audio

    async def test_extra_voice_id_from_config_is_used(self, mock_mimo_http: Any) -> None:
        requests: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse(_audio_event(b"\x00\x01")),
            )

        mock_mimo_http(handler)
        async for _ in synthesize_mimo(
            _mimo_row(extra={"voice_id": "Chloe"}), "hi", voice_id=None, speed=1.0
        ):
            pass
        assert requests[0]["audio"]["voice"] == "Chloe"


class TestMimoTTSStreamingYieldsNothingOnEmpty:
    async def test_done_only_stream_yields_header_only(self, mock_mimo_http: Any) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=b"data: [DONE]\n\n",
            )

        mock_mimo_http(handler)
        chunks: list[bytes] = []
        stream: AsyncIterator[bytes] = synthesize_mimo(_mimo_row(), "x", voice_id=None, speed=1.0)
        async for chunk in stream:
            chunks.append(chunk)
        assert chunks == [_wav_header(0xFFFF_FFFF)]
