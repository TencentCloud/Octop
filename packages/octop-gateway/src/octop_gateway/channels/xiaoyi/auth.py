"""XiaoYi (Huawei OpenClaw) AK/SK authentication helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time


def generate_signature(sk: str, timestamp: str) -> str:
    """Generate HMAC-SHA256 signature: Base64(HMAC-SHA256(sk, timestamp))."""
    hmac_obj = hmac.new(sk.encode(), timestamp.encode(), hashlib.sha256)
    return base64.b64encode(hmac_obj.digest()).decode()


def generate_auth_headers(ak: str, sk: str, agent_id: str) -> dict[str, str]:
    """Build WebSocket authentication headers for XiaoYi."""
    timestamp = str(int(time.time() * 1000))
    signature = generate_signature(sk, timestamp)
    return {
        "x-access-key": ak,
        "x-sign": signature,
        "x-ts": timestamp,
        "x-agent-id": agent_id,
    }
