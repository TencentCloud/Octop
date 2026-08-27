"""DingTalk Device Flow helpers for one-click application registration."""

from __future__ import annotations

from typing import Any

import httpx

_BASE_URL = "https://oapi.dingtalk.com"
_TIMEOUT_SECONDS = 15.0


def _require_success(data: Any, operation: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RuntimeError(f"DingTalk {operation} returned an invalid response")
    if data.get("errcode") != 0:
        message = str(data.get("errmsg") or "unknown error")
        raise RuntimeError(f"DingTalk {operation} failed: {message}")
    return data


async def generate() -> dict[str, Any]:
    """Initialize Device Flow and return the public QR-code metadata."""
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT_SECONDS) as client:
        init_response = await client.post("/app/registration/init", json={})
        init_response.raise_for_status()
        initialized = _require_success(init_response.json(), "registration init")
        nonce = initialized.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise RuntimeError("DingTalk registration init response is missing nonce")

        begin_response = await client.post(
            "/app/registration/begin",
            json={"nonce": nonce},
        )
        begin_response.raise_for_status()
        started = _require_success(begin_response.json(), "registration begin")

    required = (
        "device_code",
        "user_code",
        "verification_uri_complete",
    )
    if any(not isinstance(started.get(key), str) or not started[key] for key in required):
        raise RuntimeError("DingTalk registration begin response is incomplete")
    return started


async def poll(device_code: str) -> dict[str, Any]:
    """Poll a DingTalk Device Flow registration without exposing its device code."""
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT_SECONDS) as client:
        response = await client.post(
            "/app/registration/poll",
            json={"device_code": device_code},
        )
        response.raise_for_status()
    return _require_success(response.json(), "registration poll")
