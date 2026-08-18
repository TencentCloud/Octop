"""Voice adapter implementations."""

from __future__ import annotations

import base64
import json
import struct
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from octop.infra.db.repos.voice_providers import VoiceProviderRow
from octop.infra.utils.ssrf_guard import validate_https_url_resolved
from octop.infra.voice.tencent_sign import tc3_headers


@dataclass(frozen=True)
class STTResult:
    text: str
    confidence: float | None = None


class BrowserOnlyError(Exception):
    """Raised when the active provider must run in the browser."""


def _parse_tencent_credentials(row: VoiceProviderRow) -> tuple[str, str]:
    extra = row.get_extra()
    secret_id = extra.get("secret_id") or ""
    secret_key = extra.get("secret_key") or ""
    if row.api_key and ":" in row.api_key:
        sid, _, sk = row.api_key.partition(":")
        secret_id = secret_id or sid
        secret_key = secret_key or sk
    if not secret_id or not secret_key:
        raise ValueError("Tencent Cloud requires secret_id and secret_key")
    return str(secret_id), str(secret_key)


def _voice_format(mime: str) -> str:
    lowered = mime.lower()
    if "webm" in lowered:
        return "webm"
    if "ogg" in lowered:
        return "ogg-opus"
    if "mp3" in lowered or "mpeg" in lowered:
        return "mp3"
    return "wav"


async def transcribe_browser() -> STTResult:
    raise BrowserOnlyError()


async def synthesize_browser(_text: str) -> AsyncIterator[bytes]:
    raise BrowserOnlyError()
    yield b""  # pragma: no cover


async def _guard_voice_base_url(base_url: str) -> None:
    """Reject SSRF: the voice provider base_url must be a public https host."""
    await validate_https_url_resolved(f"{base_url}/v1/audio")


async def transcribe_openai(
    row: VoiceProviderRow, audio: bytes, *, mime: str, language: str
) -> STTResult:
    api_key = row.api_key or ""
    if not api_key:
        raise ValueError("OpenAI API key is required")
    base_url = (row.base_url or "https://api.openai.com/v1").rstrip("/")
    await _guard_voice_base_url(base_url)
    extra = row.get_extra()
    model = str(extra.get("model") or "whisper-1")
    ext = "webm" if "webm" in mime else "wav"
    files = {"file": (f"audio.{ext}", audio, mime or "audio/webm")}
    data: dict[str, str] = {"model": model}
    if language:
        data["language"] = language.split("-")[0]
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{base_url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            data=data,
        )
        resp.raise_for_status()
        body = resp.json()
    text = str(body.get("text") or "").strip()
    return STTResult(text=text)


async def synthesize_openai(
    row: VoiceProviderRow,
    text: str,
    *,
    voice_id: str | None,
    speed: float,
) -> AsyncIterator[bytes]:
    api_key = row.api_key or ""
    if not api_key:
        raise ValueError("OpenAI API key is required")
    base_url = (row.base_url or "https://api.openai.com/v1").rstrip("/")
    await _guard_voice_base_url(base_url)
    extra = row.get_extra()
    model = str(extra.get("model") or "tts-1")
    voice = voice_id or str(extra.get("voice_id") or "alloy")
    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "speed": speed,
        "response_format": "mp3",
    }
    async with (
        httpx.AsyncClient(timeout=120.0) as client,
        client.stream(
            "POST",
            f"{base_url}/audio/speech",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        ) as resp,
    ):
        resp.raise_for_status()
        async for chunk in resp.aiter_bytes():
            if chunk:
                yield chunk


async def transcribe_tencent(
    row: VoiceProviderRow,
    audio: bytes,
    *,
    mime: str,
    language: str,
) -> STTResult:
    secret_id, secret_key = _parse_tencent_credentials(row)
    extra = row.get_extra()
    eng = str(extra.get("eng_service_type") or "16k_zh")
    if language.lower().startswith("en"):
        eng = str(extra.get("eng_service_type_en") or "16k_en")
    payload: dict[str, Any] = {
        "EngSerViceType": eng,
        "SourceType": 1,
        "VoiceFormat": _voice_format(mime),
        "Data": base64.b64encode(audio).decode("ascii"),
        "DataLen": len(audio),
    }
    headers, body = tc3_headers(
        secret_id=secret_id,
        secret_key=secret_key,
        service="asr",
        host="asr.tencentcloudapi.com",
        action="SentenceRecognition",
        version="2019-06-14",
        payload=payload,
        region=str(extra.get("region") or "ap-guangzhou"),
    )
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://asr.tencentcloudapi.com/",
            headers=headers,
            content=body.encode("utf-8"),
        )
        resp.raise_for_status()
        data = resp.json()
    response = data.get("Response") or {}
    if "Error" in response:
        err = response["Error"]
        raise RuntimeError(f"{err.get('Code')}: {err.get('Message')}")
    text = str(response.get("Result") or "").strip()
    return STTResult(text=text)


async def synthesize_tencent(
    row: VoiceProviderRow,
    text: str,
    *,
    voice_id: str | None,
    speed: float,
) -> AsyncIterator[bytes]:
    secret_id, secret_key = _parse_tencent_credentials(row)
    extra = row.get_extra()
    voice_type = int(voice_id or extra.get("voice_type") or 101001)
    payload: dict[str, Any] = {
        "Text": text,
        "SessionId": str(uuid.uuid4()),
        "ModelType": 1,
        "VoiceType": voice_type,
        "Codec": "mp3",
        "Speed": max(0.5, min(2.0, speed)),
    }
    headers, body = tc3_headers(
        secret_id=secret_id,
        secret_key=secret_key,
        service="tts",
        host="tts.tencentcloudapi.com",
        action="TextToVoice",
        version="2019-08-23",
        payload=payload,
        region=str(extra.get("region") or "ap-guangzhou"),
    )
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://tts.tencentcloudapi.com/",
            headers=headers,
            content=body.encode("utf-8"),
        )
        resp.raise_for_status()
        data = resp.json()
    response = data.get("Response") or {}
    if "Error" in response:
        err = response["Error"]
        raise RuntimeError(f"{err.get('Code')}: {err.get('Message')}")
    audio_b64 = response.get("Audio")
    if not audio_b64:
        raise RuntimeError("Tencent TTS returned empty audio")
    yield base64.b64decode(str(audio_b64))


async def synthesize_edge(
    row: VoiceProviderRow,
    text: str,
    *,
    voice_id: str | None,
    speed: float,
) -> AsyncIterator[bytes]:
    import edge_tts

    extra = row.get_extra()
    voice = voice_id or str(extra.get("voice_id") or "zh-CN-XiaoxiaoNeural")
    rate_pct = int((speed - 1.0) * 100)
    rate = f"{rate_pct:+d}%"
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]


async def _guard_mimo_base_url(base_url: str) -> None:
    """Reject SSRF: Mimo base_url must be a public https host."""
    await validate_https_url_resolved(base_url)


# Mimo preset voices (docs: preset voice names; "mimo_default" is not one).
MIMO_PRESET_VOICES = ("冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean")

# WAV header for raw Mimo streaming output: 24kHz PCM16LE mono.
_MIMO_WAV_SAMPLE_RATE = 24000


def _wav_header(data_len: int, sample_rate: int = _MIMO_WAV_SAMPLE_RATE) -> bytes:
    """Minimal canonical WAV header for PCM16LE mono audio.

    ``data_len`` is clamped to uint32 range; streaming callers pass a max-size
    sentinel (players that trust it simply read until the body ends).
    """
    data = min(data_len, 0xFFFF_FFFF)
    riff = min(36 + data, 0xFFFF_FFFF)
    byte_rate = sample_rate * 2
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff,
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        1,  # mono
        sample_rate,
        byte_rate,
        2,  # block align
        16,  # bits per sample
        b"data",
        data,
    )


def _normalize_mimo_voice(voice: str | None) -> str:
    """Map config values onto Mimo preset voice names.

    "mimo_default" (a legacy default from an earlier docs revision) is not a
    valid preset voice; fall back to 冰糖 (the documented default for the
    China cluster) so existing configs keep working.
    """
    if not voice or voice == "mimo_default":
        return "冰糖"
    return voice


def _mimo_audio_mime(mime: str) -> str:
    """Normalize incoming mime to a Mimo-supported format (wav or mp3)."""
    lowered = mime.lower()
    if "wav" in lowered:
        return "audio/wav"
    if "mp3" in lowered or "mpeg" in lowered:
        return "audio/mpeg"
    raise ValueError(f"Mimo STT only supports wav and mp3 audio formats (received {mime!r})")


async def transcribe_mimo(
    row: VoiceProviderRow, audio: bytes, *, mime: str, language: str
) -> STTResult:
    api_key = row.api_key or ""
    if not api_key:
        raise ValueError("Mimo API key is required")
    base_url = (row.base_url or "https://api.xiaomimimo.com/v1").rstrip("/")
    await _guard_mimo_base_url(base_url)
    mimo_mime = _mimo_audio_mime(mime)
    audio_b64 = base64.b64encode(audio).decode("ascii")
    data_url = f"data:{mimo_mime};base64,{audio_b64}"
    # Map browser locale (e.g. "zh-CN") to Mimo language code ("zh", "en", "auto")
    lang = "auto"
    if language:
        lang = (
            "zh"
            if language.lower().startswith("zh")
            else "en"
            if language.lower().startswith("en")
            else "auto"
        )
    payload: dict[str, Any] = {
        "model": "mimo-v2.5-asr",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data_url},
                    }
                ],
            }
        ],
        "asr_options": {"language": lang},
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("Mimo ASR returned no choices")
    text = str(choices[0].get("message", {}).get("content") or "").strip()
    return STTResult(text=text)


async def synthesize_mimo(
    row: VoiceProviderRow,
    text: str,
    *,
    voice_id: str | None,
    speed: float,
) -> AsyncIterator[bytes]:
    api_key = row.api_key or ""
    if not api_key:
        raise ValueError("Mimo API key is required")
    base_url = (row.base_url or "https://api.xiaomimimo.com/v1").rstrip("/")
    await _guard_mimo_base_url(base_url)
    extra = row.get_extra()
    voice = _normalize_mimo_voice(voice_id or str(extra.get("voice_id") or "") or None)
    # Mimo TTS: text goes in assistant message, optional style in user message.
    # Speed is not a direct API parameter; ignored for stability.
    payload: dict[str, Any] = {
        "model": "mimo-v2.5-tts",
        "messages": [
            {"role": "user", "content": "Speak naturally."},
            {"role": "assistant", "content": text},
        ],
        "audio": {"format": "pcm16", "voice": voice},
        "stream": True,
    }
    # Low-latency streaming: request pcm16 chunks (24kHz PCM16LE mono) and
    # wrap them in a WAV container on the fly so standard players work.
    yield _wav_header(0xFFFF_FFFF)  # unknown length → max data size sentinel
    async with (
        httpx.AsyncClient(timeout=120.0) as client,
        client.stream(
            "POST",
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            json=payload,
        ) as resp,
    ):
        resp.raise_for_status()
        buf = ""
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                # Blank line terminates an SSE event; other lines are ignored.
                if not line.strip():
                    buf = ""
                continue
            buf += line[len("data:") :]
            if buf.strip() == "[DONE]":
                break
            try:
                event = json.loads(buf)
            except json.JSONDecodeError:
                continue  # JSON event may span multiple data lines.
            buf = ""
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            audio = delta.get("audio")
            if not audio:
                continue
            data = audio.get("data")
            if not data:
                continue
            pcm = base64.b64decode(data)
            if pcm:
                yield pcm


async def test_stt(row: VoiceProviderRow | None, kind: str) -> dict[str, Any]:
    if kind == "browser":
        return {"ok": True, "mode": "browser"}
    if row is None:
        return {"ok": False, "error": "provider not configured"}
    if not row.api_key and kind in {"openai", "tencent", "mimo"}:
        return {"ok": False, "error": "API credentials missing"}
    return {"ok": True, "mode": kind}


async def test_tts(row: VoiceProviderRow | None, kind: str) -> dict[str, Any]:
    if kind == "browser":
        return {"ok": True, "mode": "browser"}
    if kind == "edge":
        chunks: list[bytes] = []
        async for part in synthesize_edge(
            row
            or VoiceProviderRow(
                id=0,
                name="edge",
                kind="edge",
                capability="tts",
                base_url=None,
                api_key=None,
                extra_json=None,
                note=None,
                enabled=1,
                created_at=0,
                updated_at=0,
            ),
            "ping",
            voice_id=None,
            speed=1.0,
        ):
            chunks.append(part)
        return {"ok": bool(chunks), "bytes": sum(len(c) for c in chunks)}
    if row is None:
        return {"ok": False, "error": "provider not configured"}
    if not row.api_key and kind in {"openai", "tencent", "mimo"}:
        return {"ok": False, "error": "API credentials missing"}
    chunks = []
    synth = (
        synthesize_mimo
        if kind == "mimo"
        else synthesize_openai
        if kind == "openai"
        else synthesize_tencent
    )
    async for part in synth(row, "ping", voice_id=None, speed=1.0):
        chunks.append(part)
    return {"ok": bool(chunks), "bytes": sum(len(c) for c in chunks)}
