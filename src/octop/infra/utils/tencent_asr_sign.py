"""Tencent Cloud realtime speech recognition (ASR V2) WebSocket URL signing.

This is a *different* scheme from :mod:`octop.infra.utils.tencent_sign`, which
implements TC3-HMAC-SHA256 for the JSON APIs (``SentenceRecognition`` /
``TextToVoice``).  Realtime ASR V2 authenticates through query parameters:

1. every parameter except ``signature`` is sorted by key and joined into
   ``asr.cloud.tencent.com/asr/v2/<appid>?k1=v1&k2=v2`` (no ``wss://`` prefix,
   and the values are *not* percent-encoded);
2. that string is signed with ``HMAC-SHA1(secret_key)`` and base64-encoded;
3. only the resulting ``signature`` value is percent-encoded when appended to
   the final URL.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import quote
from uuid import uuid4

ASR_V2_HOST = "asr.cloud.tencent.com"
#: Large-model engine; supports Mandarin + English + Cantonese and 30 dialects.
DEFAULT_ENGINE = "16k_zh_en_2.0"
#: Tencent's ``voice_format`` token for raw 16-bit mono PCM.
PCM_VOICE_FORMAT = 1
DEFAULT_EXPIRED_SECONDS = 3600


def asr_v2_signature(origin: str, secret_key: str) -> str:
    """Return the base64 HMAC-SHA1 signature for a realtime ASR ``origin``."""
    digest = hmac.new(secret_key.encode("utf-8"), origin.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def build_asr_v2_url(
    *,
    app_id: str,
    secret_id: str,
    secret_key: str,
    engine: str = DEFAULT_ENGINE,
    voice_id: str | None = None,
    timestamp: int | None = None,
    nonce: int | None = None,
    expired_seconds: int = DEFAULT_EXPIRED_SECONDS,
) -> str:
    """Build a signed ``wss://`` URL for one realtime ASR connection.

    ``voice_id`` must be unique per connection (a new one per call by default),
    and ``timestamp`` / ``nonce`` are injectable so tests can pin the signature.
    """
    issued_at = int(time.time()) if timestamp is None else int(timestamp)
    params: dict[str, str] = {
        "secretid": secret_id,
        "timestamp": str(issued_at),
        "expired": str(issued_at + int(expired_seconds)),
        "nonce": str(secrets.randbelow(2**31) if nonce is None else int(nonce)),
        "engine_model_type": engine,
        "voice_id": voice_id or uuid4().hex,
        "voice_format": str(PCM_VOICE_FORMAT),
        "needvad": "1",
    }
    ordered = sorted(params)
    path = f"{ASR_V2_HOST}/asr/v2/{app_id}"
    query = "&".join(f"{key}={params[key]}" for key in ordered)
    signature = quote(asr_v2_signature(f"{path}?{query}", secret_key), safe="")
    return f"wss://{path}?{query}&signature={signature}"
