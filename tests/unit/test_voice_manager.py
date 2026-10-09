"""Unit tests for VoiceManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.voice_providers import VoiceProviderRepo, VoiceProviderRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.voice import adapters
from octop.infra.voice.manager import VoiceManager


@pytest.fixture
def voice_repos(tmp_path: Path) -> tuple[SettingsRepo, VoiceProviderRepo]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return SettingsRepo(db), VoiceProviderRepo(db)


@pytest.fixture
def voice_mgr(voice_repos: tuple[SettingsRepo, VoiceProviderRepo]) -> VoiceManager:
    settings, repo = voice_repos
    return VoiceManager(settings_repo=settings, voice_provider_repo=repo)


def test_default_active_is_browser(voice_mgr: VoiceManager) -> None:
    assert voice_mgr.get_active() == {"stt": "browser", "tts": "browser"}


def test_set_active_edge_tts_only(voice_mgr: VoiceManager) -> None:
    active = voice_mgr.set_active(tts="edge")
    assert active["tts"] == "edge"
    assert active["stt"] == "browser"


def test_edge_cannot_be_stt(voice_mgr: VoiceManager) -> None:
    with pytest.raises(OctopError) as exc:
        voice_mgr.set_active(stt="edge")
    assert exc.value.code == ErrorCode.VOICE_CAPABILITY_MISMATCH


@pytest.mark.asyncio
async def test_transcribe_browser_raises_browser_only(voice_mgr: VoiceManager) -> None:
    with pytest.raises(OctopError) as exc:
        await voice_mgr.transcribe(b"audio", mime="audio/webm")
    assert exc.value.code == ErrorCode.VOICE_BROWSER_ONLY


@pytest.mark.asyncio
async def test_synthesize_browser_raises_browser_only(voice_mgr: VoiceManager) -> None:
    with pytest.raises(OctopError) as exc:
        chunks = [c async for c in voice_mgr.synthesize("hello")]
        assert not chunks
    assert exc.value.code == ErrorCode.VOICE_BROWSER_ONLY


@pytest.mark.asyncio
async def test_configuration_probe_uses_unsaved_values(
    voice_mgr: VoiceManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_row: VoiceProviderRow | None = None
    captured_kind = ""

    async def fake_test_stt(
        row: VoiceProviderRow | None, kind: str, *, locale: str = "en"
    ) -> dict[str, object]:
        nonlocal captured_row, captured_kind
        captured_row = row
        captured_kind = kind
        return {"ok": True}

    monkeypatch.setattr(adapters, "test_stt", fake_test_stt)

    result = await voice_mgr.test_configuration(
        name="draft",
        kind="openai",
        capability="both",
        base_url="https://example.test/v1",
        api_key="sk-draft",
        extra_json='{"model":"whisper-1"}',
        mode="stt",
    )

    assert result == {"ok": True}
    assert captured_kind == "openai"
    assert captured_row is not None
    assert captured_row.name == "draft"
    assert captured_row.api_key == "sk-draft"
    assert captured_row.base_url == "https://example.test/v1"


def test_disabled_custom_provider_cannot_be_activated(
    voice_mgr: VoiceManager, voice_repos: tuple[SettingsRepo, VoiceProviderRepo]
) -> None:
    _settings, repo = voice_repos
    provider_id = repo.create(name="DisabledVoice", kind="openai", capability="both")
    repo.update(provider_id, enabled=False)

    with pytest.raises(OctopError) as exc:
        voice_mgr.set_active(stt="DisabledVoice", tts="DisabledVoice")
    assert exc.value.code == ErrorCode.VOICE_PROVIDER_DISABLED
    assert voice_mgr.get_active() == {"stt": "browser", "tts": "browser"}


@pytest.mark.parametrize("capability", ["stt", "tts"])
async def test_explicit_custom_provider_checks_capability(
    voice_mgr: VoiceManager,
    voice_repos: tuple[SettingsRepo, VoiceProviderRepo],
    capability: str,
) -> None:
    _settings, repo = voice_repos
    repo.create(name="SingleModeVoice", kind="openai", capability=capability)

    with pytest.raises(OctopError) as exc:
        if capability == "tts":
            await voice_mgr.transcribe(b"audio", mime="audio/wav", provider_name="SingleModeVoice")
        else:
            _ = [
                chunk
                async for chunk in voice_mgr.synthesize("hello", provider_name="SingleModeVoice")
            ]
    assert exc.value.code == ErrorCode.VOICE_CAPABILITY_MISMATCH


def test_invalid_tts_does_not_partially_change_active_providers(
    voice_mgr: VoiceManager, voice_repos: tuple[SettingsRepo, VoiceProviderRepo]
) -> None:
    _settings, repo = voice_repos
    repo.create(name="MyASR", kind="openai", capability="stt")
    initial = voice_mgr.set_active(tts="edge")

    with pytest.raises(OctopError) as exc:
        voice_mgr.set_active(stt="MyASR", tts="MyASR")
    assert exc.value.code == ErrorCode.VOICE_CAPABILITY_MISMATCH
    assert voice_mgr.get_active() == initial
