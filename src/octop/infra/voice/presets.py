"""Built-in voice provider presets."""

from __future__ import annotations

from typing import Any, Literal

VoiceCapability = Literal["stt", "tts", "both"]

_BUILTIN_PRESET_IDS = frozenset({"browser", "edge", "tencent", "openai", "mimo"})


def is_builtin_preset(name: str) -> bool:
    return name in _BUILTIN_PRESET_IDS


def load_voice_presets() -> list[dict[str, Any]]:
    return [
        {
            "id": "browser",
            "name": "Browser Native",
            "kind": "browser",
            "capability": "both",
            "free": True,
            "requires_key": False,
            "description": "Uses the browser Web Speech API — zero configuration.",
        },
        {
            "id": "edge",
            "name": "Edge TTS",
            "kind": "edge",
            "capability": "tts",
            "free": True,
            "requires_key": False,
            "description": "Free Microsoft Edge neural voices via edge-tts.",
        },
        {
            "id": "tencent",
            "name": "Tencent Cloud",
            "kind": "tencent",
            "capability": "both",
            "free": True,
            "requires_key": True,
            "description": "Tencent ASR + TTS with free trial quota for new accounts.",
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "kind": "openai",
            "capability": "both",
            "free": False,
            "requires_key": True,
            "description": "Whisper STT and OpenAI TTS.",
        },
        {
            "id": "mimo-stt",
            "name": "Xiaomi MiMo STT",
            "kind": "mimo",
            "capability": "stt",
            "free": False,
            "requires_key": True,
            "description": "Xiaomi MiMo ASR (mimo-v2.5-asr). Pay-as-you-go.",
        },
        {
            "id": "mimo-tts",
            "name": "Xiaomi MiMo TTS",
            "kind": "mimo",
            "capability": "tts",
            "free": False,
            "limited_free": True,
            "requires_key": True,
            "description": "Xiaomi MiMo TTS (mimo-v2.5-tts). Limited-time free.",
        },
    ]
