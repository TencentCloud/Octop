"""STT upload MIME → provider format mapping (Tencent / Mimo)."""

from __future__ import annotations

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.voice.adapters import _mimo_audio_mime, _voice_format


@pytest.mark.parametrize(
    ("mime", "expected"),
    [
        ("audio/mp3", "mp3"),
        ("audio/mpeg", "mp3"),
        ("audio/wav", "wav"),
        ("audio/ogg", "ogg-opus"),
        ("audio/mp4", "m4a"),
        ("audio/m4a", "m4a"),
        ("audio/aac", "m4a"),
        ("audio/amr", "amr"),
        ("audio/silk", "silk"),
        ("audio/speex", "speex"),
        ("audio/pcm", "pcm"),
    ],
)
def test_tencent_voice_format_mapping(mime: str, expected: str) -> None:
    assert _voice_format(mime) == expected


def test_tencent_voice_format_rejects_unknown_container() -> None:
    with pytest.raises(OctopError) as exc:
        _voice_format("audio/webm")
    assert exc.value.code == ErrorCode.VOICE_KIND_UNSUPPORTED
    assert exc.value.details == {"mime": "audio/webm"}


def test_mimo_mime_mapping() -> None:
    assert _mimo_audio_mime("audio/wav") == "audio/wav"
    assert _mimo_audio_mime("audio/mpeg") == "audio/mpeg"
    with pytest.raises(OctopError) as exc:
        _mimo_audio_mime("audio/webm")
    assert exc.value.code == ErrorCode.VOICE_KIND_UNSUPPORTED
