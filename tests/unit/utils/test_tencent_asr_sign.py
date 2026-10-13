"""Tests for Tencent realtime ASR V2 WebSocket URL signing."""

from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import quote

from octop.infra.utils.tencent_asr_sign import (
    ASR_V2_HOST,
    DEFAULT_ENGINE,
    DEFAULT_EXPIRED_SECONDS,
    asr_v2_signature,
    build_asr_v2_url,
)

_ORIGIN = (
    f"{ASR_V2_HOST}/asr/v2/1302566622"
    "?engine_model_type=16k_zh_en_2.0&expired=1700003600&needvad=1&nonce=12345"
    "&secretid=AKIDSID&timestamp=1700000000&voice_format=1&voice_id=vtest"
)
_SIGNATURE = "rhoZKciBwud6h4DGanqKV1YVWLw="


def _fixed_url(**overrides: object) -> str:
    kwargs: dict[str, object] = {
        "app_id": "1302566622",
        "secret_id": "AKIDSID",
        "secret_key": "SKEY",
        "voice_id": "vtest",
        "timestamp": 1700000000,
        "nonce": 12345,
    }
    kwargs.update(overrides)
    return build_asr_v2_url(**kwargs)  # type: ignore[arg-type]


def _query_of(url: str) -> str:
    return url.split("?", 1)[1].rsplit("&signature=", 1)[0]


def test_signature_is_hmac_sha1_base64() -> None:
    expected = base64.b64encode(
        hmac.new(b"SKEY", _ORIGIN.encode("utf-8"), hashlib.sha1).digest()
    ).decode("ascii")
    assert expected == _SIGNATURE
    assert asr_v2_signature(_ORIGIN, "SKEY") == _SIGNATURE


def test_build_url_matches_locked_origin_and_encoded_signature() -> None:
    assert _fixed_url() == f"wss://{_ORIGIN}&signature={quote(_SIGNATURE, safe='')}"


def test_signature_value_is_percent_encoded() -> None:
    tail = _fixed_url().split("&signature=", 1)[1]
    assert tail == "rhoZKciBwud6h4DGanqKV1YVWLw%3D"
    assert not any(ch in tail for ch in "=+/")


def test_params_are_sorted_and_pcm_is_selected() -> None:
    query = _query_of(_fixed_url())
    keys = [part.split("=", 1)[0] for part in query.split("&")]
    assert keys == sorted(keys)
    assert "voice_format=1" in query
    assert "needvad=1" in query
    assert f"engine_model_type={DEFAULT_ENGINE}" in query
    assert f"expired={1700000000 + DEFAULT_EXPIRED_SECONDS}" in query


def test_origin_values_are_not_percent_encoded() -> None:
    url = _fixed_url(secret_id="sid+slash/eq=")
    assert "secretid=sid+slash/eq=&" in url


def test_engine_is_overridable() -> None:
    assert f"engine_model_type={'16k_zh'}&" in _fixed_url(engine="16k_zh") + "&"


def test_voice_id_is_regenerated_per_call() -> None:
    first = build_asr_v2_url(app_id="a", secret_id="s", secret_key="k")
    second = build_asr_v2_url(app_id="a", secret_id="s", secret_key="k")
    assert first != second
    assert "voice_id=" in first
