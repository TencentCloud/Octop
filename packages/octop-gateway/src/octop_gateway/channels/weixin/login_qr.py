"""WeChat iLink Bot QR code login flow.

Phase 1: WeixinQRLogin.fetch_qr_code()  → QRCodeResponse (token + display URL)
Phase 2: WeixinQRLogin.wait_for_login() → WeixinQrWaitResult (connected + credentials)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Final
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_QR_API_BASE_URL: Final[str] = "https://ilinkai.weixin.qq.com"
_QR_BOT_ENDPOINT: Final[str] = "ilink/bot/get_bot_qrcode"
_QR_STATUS_ENDPOINT: Final[str] = "ilink/bot/get_qrcode_status"
_DEFAULT_BOT_TYPE: Final[str] = "3"
_ILINK_CLIENT_VERSION: Final[str] = "1"
_QR_LONG_POLL_TIMEOUT_S: Final[float] = 35.0
_LOGIN_TIMEOUT_S: Final[float] = 480.0  # 8 minutes overall
_MAX_QR_REFRESH_COUNT: Final[int] = 3

# SSRF protection: only these hosts are permitted for QR login
_ALLOWED_QR_HOSTS: Final[frozenset[str]] = frozenset({"ilinkai.weixin.qq.com"})

# ── Types ────────────────────────────────────────────────────────────────────


class QRCodeResponse(BaseModel):
    """Response from WeChat QR code fetch endpoint."""

    qrcode: str  # opaque polling token
    qrcode_img_content: str  # URL to display as QR image


class _QRStatusResponse(BaseModel):
    """Internal: raw polling response from iLink."""

    status: str
    bot_token: str | None = None
    ilink_bot_id: str | None = None
    baseurl: str | None = None
    ilink_user_id: str | None = None


class WeixinQrWaitResult(BaseModel):
    """Result of waiting for QR code confirmation."""

    connected: bool
    bot_token: str | None = None
    account_id: str | None = None  # normalised ilink_bot_id
    base_url: str | None = None  # server-returned base URL for messaging
    user_id: str | None = None
    message: str = ""


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_account_id(ilink_bot_id: str | None) -> str | None:
    """Normalise WeChat ilink_bot_id by replacing '@' and '.' with '-'."""
    if not ilink_bot_id:
        return None
    return ilink_bot_id.replace("@", "-").replace(".", "-")


# ── WeixinQRLogin ─────────────────────────────────────────────────────────────


class WeixinQRLogin:
    """Two-phase QR code login for WeChat iLink Bot.

    Phase 1: fetch_qr_code() → QRCodeResponse
    Phase 2: wait_for_login() → WeixinQrWaitResult
    """

    def __init__(
        self,
        qr_base_url: str = _QR_API_BASE_URL,
        route_tag: str = "",
    ) -> None:
        validated = self._validate_qr_base_url(qr_base_url)
        self.qr_base_url = validated
        self.route_tag = route_tag
        self._active_qrcode: str | None = None
        self._refresh_count = 0

    # ── Validation ──────────────────────────────────────────────────────────

    @staticmethod
    def _validate_qr_base_url(url: str) -> str:
        """Validate URL to prevent SSRF attacks.

        Raises:
            ValueError: if URL is not HTTPS or host is not whitelisted.
        """
        url = url.rstrip("/")
        parsed = urlparse(url)

        if parsed.scheme != "https":
            raise ValueError(f"Only HTTPS allowed for QR API; got scheme: {parsed.scheme}")
        if parsed.hostname not in _ALLOWED_QR_HOSTS:
            raise ValueError(f"Unauthorized host for QR API: {parsed.hostname}. Allowed: {_ALLOWED_QR_HOSTS}")
        return url

    # ── Phase 1 ─────────────────────────────────────────────────────────────

    async def fetch_qr_code(self, reset_refresh_count: bool = True) -> QRCodeResponse:
        """Fetch a new QR code from iLink.

        Returns:
            QRCodeResponse with polling token and display URL.

        Raises:
            Exception: on API failure or malformed response.
        """
        url = f"{self.qr_base_url}/{_QR_BOT_ENDPOINT}"
        params = {"bot_type": _DEFAULT_BOT_TYPE}
        headers = {"iLink-App-ClientVersion": _ILINK_CLIENT_VERSION}
        if self.route_tag:
            headers["SKRouteTag"] = self.route_tag

        logger.debug("Fetching WeChat QR code from %s", url)
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

        logger.debug("QR code fetch response: %s", data)
        result = QRCodeResponse(**data)
        self._active_qrcode = result.qrcode
        if reset_refresh_count:
            self._refresh_count = 0
        return result

    # ── Phase 2 ─────────────────────────────────────────────────────────────

    async def wait_for_login(
        self,
        qrcode: str,
        timeout_s: float = _LOGIN_TIMEOUT_S,
        on_scanned: Callable[[], None] | None = None,
    ) -> WeixinQrWaitResult:
        """Long-poll for QR status until confirmed / expired / timeout.

        Automatically refreshes the QR up to _MAX_QR_REFRESH_COUNT times
        if it expires before the user scans.

        Args:
            qrcode:    QR code token from fetch_qr_code().
            timeout_s: Overall wall-clock timeout in seconds.
            on_scanned: Optional callback when user scans (before confirmation).

        Returns:
            WeixinQrWaitResult.

        Raises:
            TimeoutError: if polling exceeds timeout_s without confirmation.
        """
        self._active_qrcode = qrcode
        start_time = time.time()
        scanned_notified = False

        async with httpx.AsyncClient(timeout=_QR_LONG_POLL_TIMEOUT_S + 5) as client:
            while time.time() - start_time < timeout_s:
                url = f"{self.qr_base_url}/{_QR_STATUS_ENDPOINT}"
                headers = {"iLink-App-ClientVersion": _ILINK_CLIENT_VERSION}
                if self.route_tag:
                    headers["SKRouteTag"] = self.route_tag

                try:
                    response = await client.get(url, params={"qrcode": qrcode}, headers=headers)
                    response.raise_for_status()
                    raw = response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning("QR status poll failed (retrying): %s", exc)
                    await asyncio.sleep(1)
                    continue

                logger.debug("QR status response: %s", raw)
                status_resp = _QRStatusResponse(**raw)
                status = status_resp.status

                if status == "wait":
                    continue

                if status == "scaned":
                    if on_scanned and not scanned_notified:
                        scanned_notified = True
                        try:
                            on_scanned()
                        except Exception as exc:  # pylint: disable=broad-except
                            # User callbacks must not abort the login polling loop.
                            logger.exception("on_scanned callback error: %s", exc)
                    await asyncio.sleep(1)
                    continue

                if status == "confirmed":
                    logger.info("WeChat QR login confirmed")
                    return WeixinQrWaitResult(
                        connected=True,
                        bot_token=status_resp.bot_token,
                        account_id=_normalize_account_id(status_resp.ilink_bot_id),
                        base_url=status_resp.baseurl,
                        user_id=status_resp.ilink_user_id,
                        message="QR code confirmed",
                    )

                if status == "expired":
                    logger.info(
                        "QR expired (refresh %d/%d)",
                        self._refresh_count,
                        _MAX_QR_REFRESH_COUNT,
                    )
                    if self._refresh_count < _MAX_QR_REFRESH_COUNT:
                        self._refresh_count += 1
                        new_qr = await self.fetch_qr_code(reset_refresh_count=False)
                        qrcode = new_qr.qrcode
                        scanned_notified = False
                        continue
                    return WeixinQrWaitResult(
                        connected=False,
                        message=f"QR expired after {_MAX_QR_REFRESH_COUNT} refresh attempts",
                    )

                logger.warning("Unknown QR status: %s", status)
                await asyncio.sleep(1)

        return WeixinQrWaitResult(
            connected=False,
            message=f"QR login timeout (no confirmation within {timeout_s}s)",
        )
