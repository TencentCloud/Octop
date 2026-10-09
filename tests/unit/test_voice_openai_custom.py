"""OpenAI-compatible voice requests respect custom models and upload formats."""

from __future__ import annotations

import json
from collections.abc import Callable
from email import policy
from email.parser import BytesParser
from typing import Any

import httpx
import pytest

import octop.infra.voice.adapters as voice_adapters
from octop.infra.db.repos.voice_providers import VoiceProviderRow


def _row(extra: dict[str, str]) -> VoiceProviderRow:
    return VoiceProviderRow(
        id=1,
        name="CustomVoice",
        kind="openai",
        capability="both",
        base_url="https://custom.example/v1/",
        api_key="custom-key",
        extra_json=json.dumps(extra),
        note=None,
        enabled=1,
        created_at=0,
        updated_at=0,
    )


@pytest.fixture
def mock_openai_http(monkeypatch: pytest.MonkeyPatch) -> Any:
    original = httpx.AsyncClient

    async def skip_url_guard(_base_url: str) -> None:
        pass

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        def factory(**kwargs: Any) -> httpx.AsyncClient:
            return original(**{**kwargs, "transport": httpx.MockTransport(handler)})

        monkeypatch.setattr(voice_adapters.httpx, "AsyncClient", factory)

    monkeypatch.setattr(voice_adapters, "_guard_voice_base_url", skip_url_guard)
    return install


def _multipart(request: httpx.Request) -> dict[str, Any]:
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode() + request.content
    )
    return {
        str(part.get_param("name", header="content-disposition")): part
        for part in message.iter_parts()
    }


async def test_custom_models_and_saved_voice_are_sent_to_provider(mock_openai_http: Any) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("transcriptions"):
            return httpx.Response(200, json={"text": "  transcript  "})
        return httpx.Response(200, content=b"speech")

    mock_openai_http(handler)
    row = _row(
        {
            "stt_model": "custom-asr",
            "tts_model": "custom-tts",
            "model": "legacy-model",
            "voice_id": "saved-voice",
        }
    )
    result = await voice_adapters.transcribe_openai(
        row, b"audio", mime="audio/wav", language="zh-CN"
    )
    assert result.text == "transcript"
    saved = b"".join(
        [
            chunk
            async for chunk in voice_adapters.synthesize_openai(
                row, "hello", voice_id=None, speed=1.0
            )
        ]
    )
    overridden = b"".join(
        [
            chunk
            async for chunk in voice_adapters.synthesize_openai(
                row, "hello", voice_id="override-voice", speed=1.25
            )
        ]
    )
    assert saved == overridden == b"speech"
    assert [str(request.url) for request in requests] == [
        "https://custom.example/v1/audio/transcriptions",
        "https://custom.example/v1/audio/speech",
        "https://custom.example/v1/audio/speech",
    ]
    assert all(request.headers["authorization"] == "Bearer custom-key" for request in requests)
    stt_fields = _multipart(requests[0])
    assert stt_fields["model"].get_payload(decode=True) == b"custom-asr"
    assert stt_fields["language"].get_payload(decode=True) == b"zh"
    saved_payload = json.loads(requests[1].content)
    assert saved_payload == {
        "model": "custom-tts",
        "input": "hello",
        "voice": "saved-voice",
        "speed": 1.0,
        "response_format": "mp3",
    }
    override_payload = json.loads(requests[2].content)
    assert override_payload["voice"] == "override-voice"
    assert override_payload["speed"] == 1.25


@pytest.mark.parametrize(
    ("extra", "stt_model", "tts_model"),
    [({"model": "legacy-voice"}, "legacy-voice", "legacy-voice"), ({}, "whisper-1", "tts-1")],
)
async def test_legacy_model_and_default_model_fallback(
    mock_openai_http: Any, extra: dict[str, str], stt_model: str, tts_model: str
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("transcriptions"):
            return httpx.Response(200, json={"text": "transcript"})
        return httpx.Response(200, content=b"speech")

    mock_openai_http(handler)
    row = _row(extra)
    await voice_adapters.transcribe_openai(row, b"audio", mime="audio/wav", language="")
    _ = [
        chunk
        async for chunk in voice_adapters.synthesize_openai(row, "hello", voice_id=None, speed=1.0)
    ]
    fields = _multipart(requests[0])
    assert fields["model"].get_payload(decode=True).decode() == stt_model
    assert "language" not in fields
    tts_payload = json.loads(requests[1].content)
    assert tts_payload["model"] == tts_model
    assert tts_payload["voice"] == "alloy"


@pytest.mark.parametrize(
    ("mime", "extension"),
    [
        ("audio/mp4", "m4a"),
        ("audio/x-m4a", "m4a"),
        ("audio/ogg; codecs=opus", "ogg"),
        ("audio/mpeg", "mp3"),
    ],
)
async def test_upload_preserves_audio_extension_and_mime(
    mock_openai_http: Any, mime: str, extension: str
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"text": "transcript"})

    mock_openai_http(handler)
    await voice_adapters.transcribe_openai(_row({}), b"original-audio", mime=mime, language="")
    file = _multipart(requests[0])["file"]
    assert file.get_filename() == f"audio.{extension}"
    assert file.get_payload(decode=True) == b"original-audio"
    assert f"Content-Type: {mime}\r\n".encode() in requests[0].content


@pytest.mark.parametrize("mode", ["stt", "tts"])
async def test_http_provider_errors_propagate(mock_openai_http: Any, mode: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    mock_openai_http(handler)
    with pytest.raises(httpx.HTTPStatusError) as exc:
        if mode == "stt":
            await voice_adapters.transcribe_openai(
                _row({}), b"audio", mime="audio/wav", language=""
            )
        else:
            _ = [
                chunk
                async for chunk in voice_adapters.synthesize_openai(
                    _row({}), "hello", voice_id=None, speed=1.0
                )
            ]
    assert exc.value.response.status_code == 401


@pytest.mark.parametrize("mode", ["stt", "tts"])
async def test_json_provider_errors_are_reported_by_probe(mock_openai_http: Any, mode: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"message": "Unknown model"}})

    mock_openai_http(handler)
    probe = voice_adapters.test_stt if mode == "stt" else voice_adapters.test_tts
    result = await probe(_row({}), "openai")
    assert result["ok"] is False
    assert "Unknown model" in result["error"]


async def test_blank_stt_text_is_valid_for_probe(mock_openai_http: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": ""})

    mock_openai_http(handler)
    assert await voice_adapters.test_stt(_row({}), "openai") == {"ok": True, "mode": "openai"}
