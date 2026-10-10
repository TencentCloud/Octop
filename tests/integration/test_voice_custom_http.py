"""Custom voice providers remain configurable and dispatch through their protocol."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

import octop.infra.voice.adapters as voice_adapters
from octop.infra.db.repos.voice_providers import VoiceProviderRow
from octop.infra.voice.adapters import STTResult


@pytest.mark.parametrize("kind", ["openai", "dashscope"])
async def test_custom_voice_provider_lifecycle_and_dispatch(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    client, _srv, auth = env
    extra = {"stt_model": "custom-asr", "tts_model": "custom-tts", "voice_id": "Cherry"}
    created = await client.post(
        "/api/admin/voice/providers",
        headers=auth,
        json={
            "name": "MyVoice",
            "kind": kind,
            "capability": "both",
            "base_url": "https://voice.example/v1",
            "api_key": "custom-key",
            "extra_json": json.dumps(extra),
            "note": "My voice service",
        },
    )
    assert created.status_code == 201
    provider = created.json()
    assert provider["name"] == "MyVoice"
    assert provider["kind"] == kind
    assert provider["capability"] == "both"
    assert provider["extra"] == extra

    for path in ("/api/voice/providers", "/api/admin/voice/providers"):
        listed = await client.get(path, headers=auth)
        assert listed.status_code == 200
        assert provider in listed.json()

    extra["tts_model"] = "updated-tts"
    updated = await client.patch(
        f"/api/admin/voice/providers/{provider['id']}",
        headers=auth,
        json={
            "base_url": "https://updated.example/v1",
            "api_key": "updated-key",
            "extra_json": json.dumps(extra),
            "note": "Updated service",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["base_url"] == "https://updated.example/v1"
    assert updated.json()["api_key"] == "updated-key"
    assert updated.json()["extra"] == extra
    assert updated.json()["note"] == "Updated service"

    calls: list[str] = []

    def assert_configured_row(row: VoiceProviderRow) -> None:
        assert row.name == "MyVoice"
        assert row.kind == kind
        assert row.base_url == "https://updated.example/v1"
        assert row.api_key == "updated-key"
        assert row.get_extra() == extra

    async def transcribe(
        row: VoiceProviderRow, audio: bytes, *, mime: str, language: str
    ) -> STTResult:
        assert_configured_row(row)
        assert audio == b"custom-audio"
        assert mime == "audio/wav"
        assert language == "en-US"
        calls.append("stt")
        return STTResult(text="Custom transcript", confidence=0.9)

    async def synthesize(
        row: VoiceProviderRow, text: str, *, voice_id: str | None, speed: float
    ) -> AsyncIterator[bytes]:
        assert_configured_row(row)
        assert text == "Custom speech"
        assert voice_id == "Serena"
        assert speed == 1.25
        calls.append("tts")
        yield b"custom-speech"

    monkeypatch.setattr(voice_adapters, f"transcribe_{kind}", transcribe)
    monkeypatch.setattr(voice_adapters, f"synthesize_{kind}", synthesize)
    active = await client.put(
        "/api/voice/active",
        headers=auth,
        json={"stt": "MyVoice", "tts": "MyVoice"},
    )
    assert active.status_code == 200
    assert active.json() == {"stt": "MyVoice", "tts": "MyVoice", "stt_realtime": False}
    assert (await client.get("/api/voice/active", headers=auth)).json() == active.json()

    for changes in ({"capability": "stt"}, {"enabled": False}):
        blocked_update = await client.patch(
            f"/api/admin/voice/providers/{provider['id']}", headers=auth, json=changes
        )
        assert blocked_update.status_code == 409
        assert blocked_update.json()["error"]["code"] == "PROVIDER_REFERENCED"
        listed = await client.get("/api/voice/providers", headers=auth)
        assert updated.json() in listed.json()
        assert (await client.get("/api/voice/active", headers=auth)).json() == active.json()

    stt = await client.post(
        "/api/voice/stt",
        headers=auth,
        files={"audio": ("speech.wav", b"custom-audio", "audio/wav")},
        data={"language": "en-US"},
    )
    assert stt.status_code == 200
    assert stt.json() == {"text": "Custom transcript", "confidence": 0.9}

    tts = await client.post(
        "/api/voice/tts",
        headers=auth,
        json={"text": "Custom speech", "voice_id": "Serena", "speed": 1.25},
    )
    assert tts.status_code == 200
    assert tts.headers["content-type"] == ("audio/wav" if kind == "dashscope" else "audio/mpeg")
    assert tts.content == b"custom-speech"
    assert calls == ["stt", "tts"]

    blocked = await client.delete(f"/api/admin/voice/providers/{provider['id']}", headers=auth)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "PROVIDER_REFERENCED"
    switched = await client.put(
        "/api/voice/active", headers=auth, json={"stt": "browser", "tts": "browser"}
    )
    assert switched.status_code == 200
    deleted = await client.delete(f"/api/admin/voice/providers/{provider['id']}", headers=auth)
    assert deleted.status_code == 204
    listed = await client.get("/api/voice/providers", headers=auth)
    assert all(row["name"] != "MyVoice" for row in listed.json())


async def test_custom_voice_configuration_validation(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
) -> None:
    client, _srv, auth = env
    valid = {"name": "MyVoice", "kind": "openai", "capability": "both"}
    invalid_changes = [
        {"kind": "unsupported"},
        {"capability": "invalid"},
        {"extra_json": "{malformed"},
        {"extra_json": "[]"},
    ]
    for changes in invalid_changes + [{"name": ""}, {"name": "   "}]:
        response = await client.post(
            "/api/admin/voice/providers", headers=auth, json={**valid, **changes}
        )
        assert response.status_code == 422, changes

    created = await client.post("/api/admin/voice/providers", headers=auth, json=valid)
    assert created.status_code == 201
    for changes in invalid_changes:
        response = await client.patch(
            f"/api/admin/voice/providers/{created.json()['id']}",
            headers=auth,
            json=changes,
        )
        assert response.status_code == 422, changes
    listed = await client.get("/api/voice/providers", headers=auth)
    assert listed.json() == [created.json()]


async def test_custom_voice_names_preserve_builtin_configuration(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
) -> None:
    client, _srv, auth = env
    conflict = await client.post(
        "/api/admin/voice/providers",
        headers=auth,
        json={"name": "mimo", "kind": "openai", "capability": "both"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "PROVIDER_NAME_TAKEN"

    preset = await client.post(
        "/api/admin/voice/providers",
        headers=auth,
        json={"name": "openai", "kind": "openai", "capability": "both"},
    )
    assert preset.status_code == 201
    assert preset.json()["name"] == "openai"
    assert preset.json()["kind"] == "openai"
