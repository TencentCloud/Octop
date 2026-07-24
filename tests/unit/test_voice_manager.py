"""Unit tests for VoiceManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.voice_providers import VoiceProviderRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.voice.manager import VoiceManager


@pytest.fixture
def voice_mgr(tmp_path: Path) -> VoiceManager:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    settings = SettingsRepo(db)
    repo = VoiceProviderRepo(db)
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
