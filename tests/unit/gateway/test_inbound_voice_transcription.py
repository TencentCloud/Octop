"""Inbound voice notes are transcribed with the active server-side STT provider."""

from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    FileContent,
    InboundMessage,
    TextContent,
)

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.voice_providers import VoiceProviderRepo
from octop.infra.gateway.process.harness_request import build_content_from_message
from octop.infra.voice import adapters
from octop.infra.voice.inbound import InboundAudioTranscriber
from octop.infra.voice.manager import VoiceManager

WAV_HEADER = b"RIFF\x24\x00\x00\x00WAVEfmt "


class _MemoryMedia:
    """Minimal MediaBackend stand-in: ``read(key)`` from a dict."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    async def read(self, key: str) -> bytes:
        return self.files[key]


@pytest.fixture
def voice_mgr(tmp_path: Path) -> VoiceManager:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return VoiceManager(settings_repo=SettingsRepo(db), voice_provider_repo=VoiceProviderRepo(db))


def _enable_server_stt(mgr: VoiceManager) -> None:
    mgr._repo.create(  # type: ignore[attr-defined]
        name="asr",
        kind="mimo",
        capability="stt",
        base_url="https://stt.example.test/v1",
        api_key="k",
    )
    mgr.set_active(stt="asr")


@pytest.fixture
def fake_mimo(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake_transcribe_mimo(row: Any, audio: bytes, *, mime: str, language: str) -> Any:
        calls.append({"audio": audio, "mime": mime, "language": language, "provider": row.name})
        return adapters.STTResult(text="remind me to water the plants")

    monkeypatch.setattr(adapters, "transcribe_mimo", fake_transcribe_mimo)
    return calls


def _voice_msg(*parts: Any, text: str | None = None) -> InboundMessage:
    content: list[Any] = [TextContent(text=text)] if text else []
    content.extend(parts)
    return InboundMessage(
        channel_id="tg-1",
        channel_type="telegram",
        channel_subject=ChannelSubject(subject_id="u1", chat_type="direct"),
        content=content,
        metadata={"sender_id": "u1"},
    )


@pytest.mark.asyncio
async def test_browser_default_keeps_old_behaviour(
    voice_mgr: VoiceManager, fake_mimo: list[dict[str, Any]]
) -> None:
    transcriber = InboundAudioTranscriber(voice_mgr, ffmpeg="")
    media = _MemoryMedia({"inbound/a.wav": WAV_HEADER})
    msg = _voice_msg(AudioContent(local_path="inbound/a.wav", mime_type="audio/wav"))

    content = await build_content_from_message(msg, media_backend=media, transcriber=transcriber)

    assert fake_mimo == []
    assert "Voice message transcript" not in str(content)


@pytest.mark.asyncio
async def test_wav_voice_note_is_transcribed_without_ffmpeg(
    voice_mgr: VoiceManager, fake_mimo: list[dict[str, Any]]
) -> None:
    _enable_server_stt(voice_mgr)
    transcriber = InboundAudioTranscriber(voice_mgr, ffmpeg="")
    media = _MemoryMedia({"inbound/a.wav": WAV_HEADER})
    msg = _voice_msg(
        AudioContent(local_path="inbound/a.wav", mime_type="audio/wav"), text="see voice note"
    )

    content = await build_content_from_message(msg, media_backend=media, transcriber=transcriber)

    assert isinstance(content, str)
    assert content.startswith("see voice note")
    assert "[Voice message transcript]\nremind me to water the plants" in content
    # The path hint stays so the agent can still reference the file.
    assert "inbound/a.wav" in content
    assert fake_mimo[0]["mime"] == "audio/wav"
    assert fake_mimo[0]["language"] == ""
    assert fake_mimo[0]["provider"] == "asr"


@pytest.mark.asyncio
async def test_transcript_label_follows_locale(
    voice_mgr: VoiceManager, fake_mimo: list[dict[str, Any]]
) -> None:
    _enable_server_stt(voice_mgr)
    transcriber = InboundAudioTranscriber(voice_mgr, ffmpeg="")
    raw = base64.b64encode(WAV_HEADER).decode()
    msg = _voice_msg(AudioContent(data=raw, mime_type="audio/wav"))

    content = await build_content_from_message(msg, locale="zh", transcriber=transcriber)

    assert "[语音消息转写]\nremind me to water the plants" in str(content)


@pytest.mark.asyncio
async def test_ogg_without_ffmpeg_is_skipped(
    voice_mgr: VoiceManager, fake_mimo: list[dict[str, Any]]
) -> None:
    _enable_server_stt(voice_mgr)
    transcriber = InboundAudioTranscriber(voice_mgr, ffmpeg="")
    media = _MemoryMedia({"inbound/v.ogg": b"OggS fake"})
    msg = _voice_msg(AudioContent(local_path="inbound/v.ogg", mime_type="audio/ogg"))

    content = await build_content_from_message(msg, media_backend=media, transcriber=transcriber)

    assert fake_mimo == []
    assert "inbound/v.ogg" in str(content)
    assert "Voice message transcript" not in str(content)


@pytest.mark.asyncio
async def test_provider_error_does_not_block_turn(
    voice_mgr: VoiceManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_server_stt(voice_mgr)

    async def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("upstream 500")

    monkeypatch.setattr(adapters, "transcribe_mimo", boom)
    transcriber = InboundAudioTranscriber(voice_mgr, ffmpeg="")
    media = _MemoryMedia({"inbound/a.wav": WAV_HEADER})
    msg = _voice_msg(AudioContent(local_path="inbound/a.wav", mime_type="audio/wav"))

    content = await build_content_from_message(msg, media_backend=media, transcriber=transcriber)

    assert "inbound/a.wav" in str(content)
    assert "Voice message transcript" not in str(content)


@pytest.mark.asyncio
async def test_oversized_audio_is_skipped(
    voice_mgr: VoiceManager, fake_mimo: list[dict[str, Any]]
) -> None:
    _enable_server_stt(voice_mgr)
    transcriber = InboundAudioTranscriber(voice_mgr, ffmpeg="", max_bytes=8)
    media = _MemoryMedia({"inbound/a.wav": WAV_HEADER})
    msg = _voice_msg(AudioContent(local_path="inbound/a.wav", mime_type="audio/wav"))

    await build_content_from_message(msg, media_backend=media, transcriber=transcriber)

    assert fake_mimo == []


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
async def test_ogg_opus_voice_note_is_converted_to_wav(
    voice_mgr: VoiceManager, fake_mimo: list[dict[str, Any]], tmp_path: Path
) -> None:
    ogg = tmp_path / "note.ogg"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi",
            "-i", "sine=frequency=440:duration=1", "-c:a", "libopus", "-ac", "1", str(ogg),
        ],
        check=True,
    )  # fmt: skip
    _enable_server_stt(voice_mgr)
    transcriber = InboundAudioTranscriber(voice_mgr)
    media = _MemoryMedia({"inbound/note.ogg": ogg.read_bytes()})
    msg = _voice_msg(AudioContent(local_path="inbound/note.ogg", mime_type="audio/ogg"))

    content = await build_content_from_message(msg, media_backend=media, transcriber=transcriber)

    assert "[Voice message transcript]" in str(content)
    sent = fake_mimo[0]
    assert sent["mime"] == "audio/wav"
    assert sent["audio"][:4] == b"RIFF"
    assert sent["audio"][8:12] == b"WAVE"


@pytest.mark.asyncio
async def test_uploaded_audio_file_is_transcribed(
    voice_mgr: VoiceManager, fake_mimo: list[dict[str, Any]]
) -> None:
    """Web chat uploads arrive as FileContent; audio ones get a transcript too."""
    _enable_server_stt(voice_mgr)
    transcriber = InboundAudioTranscriber(voice_mgr, ffmpeg="")
    media = _MemoryMedia({"inbound/memo.mp3": b"ID3fake", "inbound/notes.pdf": b"%PDF"})
    msg = _voice_msg(
        FileContent(local_path="inbound/memo.mp3", filename="memo.mp3", mime_type="audio/mpeg"),
        FileContent(
            local_path="inbound/notes.pdf", filename="notes.pdf", mime_type="application/pdf"
        ),
    )

    content = await build_content_from_message(msg, media_backend=media, transcriber=transcriber)

    assert len(fake_mimo) == 1
    assert fake_mimo[0]["mime"] == "audio/mpeg"
    assert "[Voice message transcript]" in str(content)
    assert "inbound/notes.pdf" in str(content)
