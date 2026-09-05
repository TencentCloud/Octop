"""Resolve active voice providers and dispatch STT/TTS calls."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.voice_providers import VoiceProviderRepo, VoiceProviderRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.voice import adapters
from octop.infra.voice.presets import is_builtin_preset


@dataclass(frozen=True)
class ResolvedVoiceProvider:
    name: str
    kind: str
    row: VoiceProviderRow | None


class VoiceManager:
    _KEY_STT = "active_stt_provider"
    _KEY_TTS = "active_tts_provider"
    _DEFAULT = "browser"

    def __init__(
        self, *, settings_repo: SettingsRepo, voice_provider_repo: VoiceProviderRepo
    ) -> None:
        self._settings = settings_repo
        self._repo = voice_provider_repo

    def get_active(self) -> dict[str, str]:
        stt = self._settings.get(self._KEY_STT) or self._DEFAULT
        tts = self._settings.get(self._KEY_TTS) or self._DEFAULT
        return {"stt": stt, "tts": tts}

    def set_active(self, *, stt: str | None = None, tts: str | None = None) -> dict[str, str]:
        current = self.get_active()
        if stt is not None:
            self._validate_provider_name(stt, capability="stt")
            self._settings.set(self._KEY_STT, stt)
            current = {**current, "stt": stt}
        if tts is not None:
            self._validate_provider_name(tts, capability="tts")
            self._settings.set(self._KEY_TTS, tts)
            current = {**current, "tts": tts}
        return current

    def _validate_provider_name(self, name: str, *, capability: str) -> None:
        if is_builtin_preset(name):
            if name == "edge" and capability == "stt":
                raise OctopError(
                    ErrorCode.VOICE_CAPABILITY_MISMATCH, "Edge TTS does not support STT"
                )
            if name == "browser":
                return
            return
        row = self._repo.get_by_name(name)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"voice provider {name!r} not found")
        if not row.enabled:
            raise OctopError(
                ErrorCode.VOICE_PROVIDER_DISABLED, f"voice provider {name!r} is disabled"
            )
        cap = row.capability
        if cap != "both" and cap != capability:
            raise OctopError(
                ErrorCode.VOICE_CAPABILITY_MISMATCH,
                f"provider {name!r} does not support {capability.upper()}",
            )

    def resolve(self, name: str) -> ResolvedVoiceProvider:
        if is_builtin_preset(name):
            return ResolvedVoiceProvider(name=name, kind=name, row=self._repo.get_by_name(name))
        row = self._repo.get_by_name(name)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"voice provider {name!r} not found")
        if not row.enabled:
            raise OctopError(
                ErrorCode.VOICE_PROVIDER_DISABLED, f"voice provider {name!r} is disabled"
            )
        return ResolvedVoiceProvider(name=row.name, kind=row.kind, row=row)

    def media_type(self, provider_name: str | None) -> str:
        """HTTP content type of the synthesize() stream for the given provider."""
        name = provider_name or self.get_active()["tts"]
        kind = self.resolve(name).kind
        return "audio/wav" if kind == "mimo" else "audio/mpeg"

    async def transcribe(
        self,
        audio: bytes,
        *,
        mime: str,
        language: str = "zh-CN",
        provider_name: str | None = None,
    ) -> adapters.STTResult:
        name = provider_name or self.get_active()["stt"]
        resolved = self.resolve(name)
        kind = resolved.kind
        if kind == "browser":
            raise OctopError(
                ErrorCode.VOICE_BROWSER_ONLY,
                "STT is handled by the browser Web Speech API",
                details={"provider": name},
            )
        row = resolved.row
        if kind == "openai":
            if row is None:
                raise OctopError(ErrorCode.NOT_FOUND, "OpenAI voice provider is not configured")
            return await adapters.transcribe_openai(row, audio, mime=mime, language=language)
        if kind == "tencent":
            if row is None:
                raise OctopError(ErrorCode.NOT_FOUND, "Tencent voice provider is not configured")
            return await adapters.transcribe_tencent(row, audio, mime=mime, language=language)
        if kind == "mimo":
            if row is None:
                raise OctopError(ErrorCode.NOT_FOUND, "Mimo voice provider is not configured")
            return await adapters.transcribe_mimo(row, audio, mime=mime, language=language)
        raise OctopError(ErrorCode.VOICE_KIND_UNSUPPORTED, f"unsupported STT kind {kind!r}")

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        speed: float = 1.0,
        provider_name: str | None = None,
    ) -> AsyncIterator[bytes]:
        name = provider_name or self.get_active()["tts"]
        resolved = self.resolve(name)
        kind = resolved.kind
        if kind == "browser":
            raise OctopError(
                ErrorCode.VOICE_BROWSER_ONLY,
                "TTS is handled by the browser speechSynthesis API",
                details={"provider": name},
            )
        row = resolved.row
        if kind == "edge":
            source = row or VoiceProviderRow(
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
            )
            async for chunk in adapters.synthesize_edge(
                source, text, voice_id=voice_id, speed=speed
            ):
                yield chunk
            return
        if kind == "openai":
            if row is None:
                raise OctopError(ErrorCode.NOT_FOUND, "OpenAI voice provider is not configured")
            async for chunk in adapters.synthesize_openai(
                row, text, voice_id=voice_id, speed=speed
            ):
                yield chunk
            return
        if kind == "tencent":
            if row is None:
                raise OctopError(ErrorCode.NOT_FOUND, "Tencent voice provider is not configured")
            async for chunk in adapters.synthesize_tencent(
                row, text, voice_id=voice_id, speed=speed
            ):
                yield chunk
            return
        if kind == "mimo":
            if row is None:
                raise OctopError(ErrorCode.NOT_FOUND, "Mimo voice provider is not configured")
            async for chunk in adapters.synthesize_mimo(row, text, voice_id=voice_id, speed=speed):
                yield chunk
            return
        raise OctopError(ErrorCode.VOICE_KIND_UNSUPPORTED, f"unsupported TTS kind {kind!r}")

    async def test_provider(self, provider_id: int, *, mode: str) -> dict[str, Any]:
        row = self._repo.get(provider_id)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, "voice provider not found")
        if mode == "stt":
            return await adapters.test_stt(row, row.kind)
        return await adapters.test_tts(row, row.kind)

    async def test_configuration(
        self,
        *,
        name: str,
        kind: str,
        capability: str,
        base_url: str | None,
        api_key: str | None,
        extra_json: str | None,
        mode: str,
    ) -> dict[str, Any]:
        row = VoiceProviderRow(
            id=0,
            name=name,
            kind=kind,
            capability=capability,
            base_url=base_url,
            api_key=api_key,
            extra_json=extra_json,
            note=None,
            enabled=1,
            created_at=0,
            updated_at=0,
        )
        if mode == "stt":
            return await adapters.test_stt(row, kind)
        return await adapters.test_tts(row, kind)
