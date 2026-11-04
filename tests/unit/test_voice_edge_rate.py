"""Unit tests for the Edge TTS speed-to-rate conversion."""

from __future__ import annotations

import sys
import types
from collections.abc import AsyncIterator
from typing import Any

import pytest

from octop.infra.db.repos.voice_providers import VoiceProviderRow
from octop.infra.voice.adapters import synthesize_edge


def _edge_row() -> VoiceProviderRow:
    return VoiceProviderRow(
        id=1,
        name="edge-tts",
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


def _stub_edge_tts(monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]) -> None:
    class _Communicate:
        def __init__(self, _text: str, *, voice: str, rate: str) -> None:
            captured["voice"] = voice
            captured["rate"] = rate

        async def stream(self) -> AsyncIterator[dict[str, Any]]:
            return
            yield {}  # pragma: no cover - makes this an async generator

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=_Communicate))


@pytest.mark.parametrize(
    ("speed", "expected_rate"),
    [(0.8, "-20%"), (0.9, "-10%"), (1.2, "+20%"), (1.4, "+40%"), (1.9, "+90%")],
)
async def test_edge_rate_is_the_nearest_percent(
    speed: float,
    expected_rate: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    _stub_edge_tts(monkeypatch, captured)

    chunks = [
        chunk
        async for chunk in synthesize_edge(
            _edge_row(), "你好", voice_id="zh-CN-XiaoxiaoNeural", speed=speed
        )
    ]

    assert chunks == []
    assert captured["voice"] == "zh-CN-XiaoxiaoNeural"
    assert captured["rate"] == expected_rate
