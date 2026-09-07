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


@pytest.mark.asyncio
async def test_configuration_probe_uses_unsaved_values(
    voice_mgr: VoiceManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_row: VoiceProviderRow | None = None
    captured_kind = ""

    async def fake_test_stt(row: VoiceProviderRow | None, kind: str) -> dict[str, object]:
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


def test_set_active_siliconflow_preset(voice_mgr: VoiceManager) -> None:
    active = voice_mgr.set_active(tts="siliconflow")
    assert active["tts"] == "siliconflow"
    assert active["stt"] == "browser"


def test_resolve_siliconflow_preset_kind_is_openai(voice_mgr: VoiceManager) -> None:
    resolved = voice_mgr.resolve("siliconflow")
    assert resolved.kind == "openai"


def test_resolve_openai_compatible_preset_kind_is_openai(voice_mgr: VoiceManager) -> None:
    resolved = voice_mgr.resolve("openai-compatible")
    assert resolved.kind == "openai"


@pytest.mark.asyncio
async def test_configuration_probe_openai_compatible_custom_base_url(
    voice_mgr: VoiceManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    async def fake_test_tts(row: VoiceProviderRow | None, kind: str) -> dict[str, object]:
        assert row is not None
        captured["base_url"] = row.base_url
        captured["extra"] = row.get_extra()
        return {"ok": True}

    monkeypatch.setattr(adapters, "test_tts", fake_test_tts)

    result = await voice_mgr.test_configuration(
        name="draft-relay",
        kind="openai",
        capability="tts",
        base_url="https://relay.example.com/v1",
        api_key="sk-test",
        extra_json='{"model":"tts-custom","stt_model":"whisper-1","voice_id":"alloy"}',
        mode="tts",
    )

    assert result == {"ok": True}
    assert captured["base_url"] == "https://relay.example.com/v1"
    assert captured["extra"].get("model") == "tts-custom"


def test_set_active_piper_preset(voice_mgr: VoiceManager) -> None:
    active = voice_mgr.set_active(tts="piper")
    assert active["tts"] == "piper"
    assert active["stt"] == "browser"


def test_resolve_piper_preset_kind() -> None:
    from octop.infra.voice.manager import _preset_kind

    assert _preset_kind("piper") == "piper"


def test_piper_cannot_be_stt(voice_mgr: VoiceManager) -> None:
    with pytest.raises(OctopError) as exc:
        voice_mgr.set_active(stt="piper")
    assert exc.value.code == ErrorCode.VOICE_CAPABILITY_MISMATCH
