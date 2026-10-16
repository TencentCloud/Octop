"""Unit tests for VoiceManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.settings import SettingsRepo
from octop.infra.db.repos.voice_providers import VoiceProviderRepo, VoiceProviderRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.tencent_asr_sign import DEFAULT_ENGINE
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


@pytest.fixture
def tencent_mgr(tmp_path: Path) -> tuple[VoiceManager, VoiceProviderRepo]:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    repo = VoiceProviderRepo(db)
    manager = VoiceManager(settings_repo=SettingsRepo(db), voice_provider_repo=repo)
    return manager, repo


def _add_tencent(
    repo: VoiceProviderRepo, extra: dict[str, object], *, name: str = "tencent"
) -> None:
    repo.create(
        name=name,
        kind="tencent",
        capability="both",
        api_key="sid:skey",
        extra_json=json.dumps(extra),
    )


TENCENT_REALTIME_EXTRA: dict[str, object] = {
    "secret_id": "sid",
    "secret_key": "skey",
    "region": "ap-guangzhou",
    "realtime_stt": True,
    "app_id": "1302566622",
}


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


def test_realtime_config_is_none_by_default(voice_mgr: VoiceManager) -> None:
    assert voice_mgr.realtime_stt_config() is None


@pytest.mark.parametrize("name", ["tencent", "CustomTencent"])
def test_realtime_config_needs_tencent_as_active_stt(
    tencent_mgr: tuple[VoiceManager, VoiceProviderRepo], name: str
) -> None:
    manager, repo = tencent_mgr
    _add_tencent(repo, TENCENT_REALTIME_EXTRA, name=name)

    assert manager.realtime_stt_config() is None

    manager.set_active(stt=name)
    config = manager.realtime_stt_config()
    assert config is not None
    assert config.app_id == "1302566622"
    assert config.secret_id == "sid"
    assert config.secret_key == "skey"
    assert config.engine == DEFAULT_ENGINE


def test_realtime_config_needs_the_switch_on(
    tencent_mgr: tuple[VoiceManager, VoiceProviderRepo],
) -> None:
    manager, repo = tencent_mgr
    _add_tencent(repo, {**TENCENT_REALTIME_EXTRA, "realtime_stt": False})
    manager.set_active(stt="tencent")

    assert manager.realtime_stt_config() is None


@pytest.mark.parametrize("app_id", ["", "   ", None])
def test_realtime_config_needs_an_app_id(
    tencent_mgr: tuple[VoiceManager, VoiceProviderRepo], app_id: str | None
) -> None:
    manager, repo = tencent_mgr
    _add_tencent(repo, {**TENCENT_REALTIME_EXTRA, "app_id": app_id})
    manager.set_active(stt="tencent")

    assert manager.realtime_stt_config() is None


def test_realtime_config_needs_complete_credentials(
    tencent_mgr: tuple[VoiceManager, VoiceProviderRepo],
) -> None:
    manager, repo = tencent_mgr
    repo.create(
        name="tencent",
        kind="tencent",
        capability="both",
        extra_json=json.dumps({"realtime_stt": True, "app_id": "1302566622"}),
    )
    manager.set_active(stt="tencent")

    assert manager.realtime_stt_config() is None
