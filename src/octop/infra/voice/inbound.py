"""Transcribe inbound voice notes and audio attachments before a turn starts.

Channel messages (Telegram voice notes, audio files uploaded in the web chat, ...)
reach the agent as workspace path hints, so a text-only model cannot use them.
When an admin selects a server-side STT provider (OpenAI-compatible, Tencent or
Xiaomi MiMo) in the voice settings, :class:`InboundAudioTranscriber` turns every
audio attachment into text that is added to the user turn. The default
``browser`` provider runs in the browser only, so nothing changes until a server
provider is configured.

Audio is normalised to 16 kHz mono WAV with ``ffmpeg`` when it is installed
(every provider accepts WAV; Telegram voice notes are OGG/Opus). Without
``ffmpeg`` only WAV and MP3 attachments are transcribed. Failures never block
the turn: the attachment keeps its path hint and the error is logged.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from octop_gateway.models import AudioContent, ContentPart, FileContent

logger = logging.getLogger(__name__)

#: STT kinds that transcribe on the server (``browser`` is client-side only).
SERVER_STT_KINDS = frozenset({"openai", "tencent", "mimo"})
#: Formats every server STT adapter accepts as-is.
_PASSTHROUGH_MIMES = {
    "audio/wav": "audio/wav",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vnd.wave": "audio/wav",
    "audio/mpeg": "audio/mpeg",
    "audio/mp3": "audio/mpeg",
    "audio/x-mp3": "audio/mpeg",
}
_EXT_MIMES = {".wav": "audio/wav", ".mp3": "audio/mpeg"}
#: File uploads (web chat) with these extensions are treated as audio too.
_AUDIO_EXTS = frozenset(
    {".aac", ".amr", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav", ".weba"}
)

DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_SECONDS = 300
_FFMPEG_TIMEOUT_S = 60.0
_WAV_BYTES_PER_SECOND = 16000 * 2  # 16 kHz, mono, 16-bit


@dataclass(frozen=True)
class AudioTranscript:
    """Transcript of one audio attachment."""

    text: str
    truncated: bool = False
    max_seconds: int = DEFAULT_MAX_SECONDS


class InboundAudioTranscriber:
    """Transcribe audio parts of an inbound message with the active STT provider."""

    def __init__(
        self,
        voice_manager: Any,
        *,
        ffmpeg: str | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_seconds: int = DEFAULT_MAX_SECONDS,
    ) -> None:
        self._voice = voice_manager
        self._ffmpeg = ffmpeg if ffmpeg is not None else shutil.which("ffmpeg")
        self._max_bytes = max_bytes
        self._max_seconds = max_seconds
        self._warned_no_ffmpeg = False

    def active_server_provider(self) -> str | None:
        """Name of the active STT provider when it transcribes server-side, else None."""
        try:
            name = self._voice.get_active()["stt"]
            if self._voice.resolve(name).kind in SERVER_STT_KINDS:
                return str(name)
        except Exception:  # missing/disabled provider means "off"
            logger.debug("inbound STT disabled: active provider unavailable", exc_info=True)
        return None

    async def transcribe_parts(
        self,
        parts: Sequence[ContentPart],
        *,
        media_backend: Any,
    ) -> list[AudioTranscript]:
        audio_parts = [
            p for p in parts if isinstance(p, AudioContent | FileContent) and _is_audio_part(p)
        ]
        if not audio_parts:
            return []
        provider = self.active_server_provider()
        if provider is None:
            return []
        transcripts: list[AudioTranscript] = []
        for part in audio_parts:
            result = await self._transcribe_one(
                part, media_backend=media_backend, provider=provider
            )
            if result is not None and result.text:
                transcripts.append(result)
        return transcripts

    async def _transcribe_one(
        self, part: AudioContent | FileContent, *, media_backend: Any, provider: str
    ) -> AudioTranscript | None:
        key = part.local_path or "inline audio"
        try:
            inline = getattr(part, "data", None)
            if inline:
                data = base64.b64decode(inline)
            elif media_backend is not None and part.local_path:
                data = await media_backend.read(part.local_path)
            else:
                return None
        except Exception:
            logger.warning("inbound STT: cannot read audio attachment %s", key, exc_info=True)
            return None
        if not data:
            return None
        if len(data) > self._max_bytes:
            logger.warning(
                "inbound STT: %s is %d bytes (limit %d), skipped", key, len(data), self._max_bytes
            )
            return None

        truncated = False
        mime = _source_mime(part)
        if self._ffmpeg:
            wav = await self._to_wav(data, key)
            if wav is None:
                return None
            data, mime = wav, "audio/wav"
            truncated = len(wav) >= (self._max_seconds - 1) * _WAV_BYTES_PER_SECOND
        elif mime not in ("audio/wav", "audio/mpeg"):
            if not self._warned_no_ffmpeg:
                logger.warning(
                    "inbound STT: ffmpeg not found, %s audio cannot be transcribed "
                    "(install ffmpeg to enable OGG/Opus voice notes)",
                    mime or "unknown",
                )
                self._warned_no_ffmpeg = True
            return None

        try:
            result = await self._voice.transcribe(
                data, mime=mime, language="", provider_name=provider
            )
        except Exception:  # never block the turn on STT errors
            logger.warning("inbound STT: provider %s failed for %s", provider, key, exc_info=True)
            return None
        text = str(getattr(result, "text", "") or "").strip()
        return AudioTranscript(text=text, truncated=truncated, max_seconds=self._max_seconds)

    async def _to_wav(self, data: bytes, key: str) -> bytes | None:
        """Decode any audio container to 16 kHz mono PCM WAV (capped at max_seconds)."""
        assert self._ffmpeg is not None
        with tempfile.TemporaryDirectory(prefix="octop-stt-") as tmp:
            src = Path(tmp) / "input"
            dst = Path(tmp) / "output.wav"
            src.write_bytes(data)
            proc = await asyncio.create_subprocess_exec(
                self._ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(src),
                "-t",
                str(self._max_seconds),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                "-y",
                str(dst),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, err = await asyncio.wait_for(proc.communicate(), timeout=_FFMPEG_TIMEOUT_S)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                logger.warning("inbound STT: ffmpeg timed out on %s", key)
                return None
            if proc.returncode != 0 or not dst.is_file():
                logger.warning(
                    "inbound STT: ffmpeg could not decode %s: %s",
                    key,
                    (err or b"").decode(errors="replace").strip()[:300],
                )
                return None
            return dst.read_bytes()


def _is_audio_part(part: AudioContent | FileContent) -> bool:
    if isinstance(part, AudioContent):
        return bool(part.local_path or part.data)
    if part.local_path:
        mime = (part.mime_type or "").split(";", 1)[0].strip().lower()
        return mime.startswith("audio/") or Path(part.local_path).suffix.lower() in _AUDIO_EXTS
    return False


def _source_mime(part: AudioContent | FileContent) -> str:
    raw = (part.mime_type or "").split(";", 1)[0].strip().lower()
    if raw in _PASSTHROUGH_MIMES:
        return _PASSTHROUGH_MIMES[raw]
    suffix = Path(part.local_path or "").suffix.lower()
    return _EXT_MIMES.get(suffix, raw)


__all__ = [
    "SERVER_STT_KINDS",
    "AudioTranscript",
    "InboundAudioTranscriber",
]
