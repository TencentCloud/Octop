"""DashScope voice wire protocol tests without calling a live provider."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

import octop.infra.voice.adapters as adapters
from octop.infra.db.repos.voice_providers import VoiceProviderRow
from octop.infra.errors import ErrorCode, OctopError


def _row(
    *,
    extra: dict[str, Any] | None = None,
    base_url: str | None = None,
    api_key: str | None = "sk-test",
) -> VoiceProviderRow:
    return VoiceProviderRow(
        id=1,
        name="custom-qwen",
        kind="dashscope",
        capability="both",
        base_url=base_url,
        api_key=api_key,
        extra_json=json.dumps(extra) if extra else None,
        note=None,
        enabled=1,
        created_at=0,
        updated_at=0,
    )


@pytest.fixture
def mock_http(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[httpx.Request], httpx.Response]], None]:
    original = httpx.AsyncClient

    async def guard(_base_url: str) -> None:
        return None

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        def factory(**kwargs: Any) -> httpx.AsyncClient:
            return original(**kwargs, transport=httpx.MockTransport(handler))

        monkeypatch.setattr(adapters.httpx, "AsyncClient", factory)

    monkeypatch.setattr(adapters, "_guard_voice_base_url", guard)
    return install


def _sse(*events: dict[str, Any]) -> bytes:
    # Actual SSE framing, including metadata and JSON spanning multiple data lines.
    chunks = []
    for index, event in enumerate(events):
        chunks.append(f"id: {index}\nevent: result\n")
        chunks.extend(f"data: {line}\n" for line in json.dumps(event, indent=2).splitlines())
        chunks.append("\n")
    return "".join(chunks).encode()


@pytest.mark.parametrize(
    ("extra", "model"),
    [
        (None, "qwen3-asr-flash"),
        ({"model": "custom-asr"}, "custom-asr"),
        ({"model": "fallback", "stt_model": "qwen3-asr-flash-latest"}, "qwen3-asr-flash-latest"),
    ],
)
async def test_transcribe_uses_native_multimodal_protocol(
    mock_http: Callable[[Callable[[httpx.Request], httpx.Response]], None],
    extra: dict[str, Any] | None,
    model: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://custom.example/api/v1/services/aigc/multimodal-generation/generation"
        )
        assert request.headers["Authorization"] == "Bearer sk-test"
        payload = json.loads(request.content)
        assert payload == {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"audio": f"data:audio/wav;base64,{base64.b64encode(b'wav').decode()}"}
                        ],
                    }
                ]
            },
            "parameters": {
                "result_format": "message",
                "asr_options": {"language": "zh", "enable_itn": False},
            },
        }
        return httpx.Response(
            200,
            json={
                "output": {
                    "choices": [{"message": {"content": [{"text": "你好"}, {"text": "千问"}]}}]
                }
            },
        )

    mock_http(handler)
    result = await adapters.transcribe_dashscope(
        _row(extra=extra, base_url="https://custom.example/api/v1/"),
        b"wav",
        mime="audio/wav;codecs=pcm",
        language="ZH-CN",
    )
    assert result.text == "你好千问"


async def test_transcribe_auto_omits_language(
    mock_http: Callable[[Callable[[httpx.Request], httpx.Response]], None],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "dashscope.aliyuncs.com"
        options = json.loads(request.content)["parameters"]["asr_options"]
        assert "language" not in options
        return httpx.Response(200, json={"output": {"choices": [{"message": {"content": []}}]}})

    mock_http(handler)
    result = await adapters.transcribe_dashscope(_row(), b"wav", mime="audio/wav", language="auto")
    assert result.text == ""


@pytest.mark.parametrize(
    ("extra", "voice_id", "model", "voice"),
    [
        (None, None, "qwen3-tts-flash", "Cherry"),
        ({"model": "custom-tts", "voice_id": "Serena"}, None, "custom-tts", "Serena"),
        (
            {"model": "fallback", "tts_model": "qwen3-tts-flash-latest", "voice_id": "Serena"},
            "Dylan",
            "qwen3-tts-flash-latest",
            "Dylan",
        ),
    ],
)
async def test_synthesize_streams_native_pcm_as_wav(
    mock_http: Callable[[Callable[[httpx.Request], httpx.Response]], None],
    extra: dict[str, Any] | None,
    voice_id: str | None,
    model: str,
    voice: str,
) -> None:
    pcm_chunks = [b"\x01\x02" * 4, b"\x03\x04" * 6]

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
        )
        assert request.headers["Authorization"] == "Bearer sk-test"
        assert request.headers["X-DashScope-SSE"] == "enable"
        assert json.loads(request.content) == {
            "model": model,
            "input": {"text": "你好", "voice": voice, "language_type": "Auto"},
        }
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(
                *[
                    {"output": {"audio": {"data": base64.b64encode(pcm).decode()}}}
                    for pcm in pcm_chunks
                ],
                {
                    "output": {
                        "finish_reason": "stop",
                        "audio": {"data": "", "url": "https://unused"},
                    }
                },
            ),
        )

    mock_http(handler)
    chunks = [
        chunk
        async for chunk in adapters.synthesize_dashscope(
            _row(extra=extra), "你好", voice_id=voice_id, speed=1.5
        )
    ]
    assert chunks[0] == adapters._wav_header(0xFFFF_FFFF)
    assert b"".join(chunks[1:]) == b"".join(pcm_chunks)


@pytest.mark.parametrize("mode", ["stt", "tts_json", "tts_sse"])
async def test_provider_error_is_not_treated_as_success(
    mock_http: Callable[[Callable[[httpx.Request], httpx.Response]], None], mode: str
) -> None:
    error = {"code": "InvalidApiKey", "message": "Rejected API key", "request_id": "request-1"}

    def handler(_request: httpx.Request) -> httpx.Response:
        if mode == "tts_sse":
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=_sse(error)
            )
        return httpx.Response(200, json=error)

    mock_http(handler)
    chunks: list[bytes] = []
    with pytest.raises(OctopError) as caught:
        if mode == "stt":
            await adapters.transcribe_dashscope(_row(), b"wav", mime="audio/wav", language="zh-CN")
        else:
            async for chunk in adapters.synthesize_dashscope(
                _row(), "hello", voice_id=None, speed=1.0
            ):
                chunks.append(chunk)
    assert caught.value.code == ErrorCode.INTERNAL_ERROR
    assert caught.value.status == 502
    assert caught.value.details["provider_code"] == "InvalidApiKey"
    assert chunks == []


async def test_empty_audio_stream_raises(
    mock_http: Callable[[Callable[[httpx.Request], httpx.Response]], None],
) -> None:
    mock_http(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse({"output": {"finish_reason": "stop", "audio": {"data": ""}}}),
        )
    )
    with pytest.raises(OctopError) as caught:
        async for _ in adapters.synthesize_dashscope(_row(), "hello", voice_id=None, speed=1.0):
            pass
    assert caught.value.details["reason"] == "empty_audio"


async def test_adapters_require_api_key() -> None:
    with pytest.raises(ValueError):
        await adapters.transcribe_dashscope(
            _row(api_key=None), b"wav", mime="audio/wav", language="zh-CN"
        )
    with pytest.raises(ValueError):
        async for _ in adapters.synthesize_dashscope(
            _row(api_key=None), "hello", voice_id=None, speed=1.0
        ):
            pass
