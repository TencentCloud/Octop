"""Execution layer for login captcha: the only outbound-I/O seam.

Providers stay pure (request spec + verdict); this module owns the HTTP
call, timeout, error -> OctopError mapping, and the siteverify test seam.
Ensures a login captcha token against the effective provider.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from octop.infra.auth.captcha.providers import get_provider
from octop.infra.auth.captcha.store import EffectiveCaptcha
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_TEST_URLS: dict[str, str] = {}


def set_test_siteverify_url(slug: str, url: str | None) -> None:
    if url is None:
        _TEST_URLS.pop(slug, None)
    else:
        _TEST_URLS[slug] = url


def _failed() -> OctopError:
    return OctopError(
        ErrorCode.CAPTCHA_FAILED,
        "Captcha verification failed. Try again.",
    )


async def ensure_captcha(
    effective: EffectiveCaptcha, token: str | None, client_ip: str = "unknown"
) -> None:
    provider = get_provider(effective.slug)
    if provider is None or not provider.requires_token:
        return
    if not (token or "").strip():
        raise OctopError(
            ErrorCode.CAPTCHA_REQUIRED,
            "This server requires a captcha token to sign in.",
        )
    call = provider.verify_call(
        site_key=effective.site_key,
        secret=effective.secret,
        token=(token or "").strip(),
        client_ip=client_ip,
        cam_id=effective.cam_id,
        cam_key=effective.cam_key,
    )
    url = _TEST_URLS.get(provider.slug) or call.url
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            if call.json_body is not None:
                resp = await client.post(url, json=call.json_body, headers=call.headers)
            elif call.method == "GET":
                resp = await client.get(url, params=call.params)
            else:
                resp = await client.post(url, data=call.data)
            body: Any = resp.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("captcha siteverify request failed: %s", exc)
        raise _failed() from None
    if not isinstance(body, dict):
        raise _failed()
    codes = body.get("error-codes") or body.get("error_codes")
    if codes:
        logger.warning("captcha siteverify error-codes=%s", codes)
    provider.interpret(body, min_score=effective.v3_min_score)
