"""QQ Bot QR code binding flow.

Phase 1: :meth:`QQBotQRLogin.fetch_qr_code` creates a binding task.
Phase 2: :meth:`QQBotQRLogin.poll` or :meth:`QQBotQRLogin.wait_for_login`
returns the application credentials after confirmation in mobile QQ.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import secrets
from typing import Literal
from urllib.parse import urlencode

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from httpx import AsyncClient, HTTPError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_QQ_CONNECT_BASE = "https://q.qq.com"
_QQ_BIND_CREATE_PATH = "/lite/create_bind_task"
_QQ_BIND_POLL_PATH = "/lite/poll_bind_result"
_QQ_BIND_STATUS_COMPLETED = 2
_QQ_BIND_STATUS_EXPIRED = 3


class QQBotQRCredentials(BaseModel):
    """QQ Bot application credentials returned after QR confirmation."""

    app_id: str
    app_secret: str = Field(repr=False)
    user_openid: str | None = None


class QQBotQRCodeResponse(BaseModel):
    """A QQ Bot QR binding task ready to be rendered by a client."""

    task_id: str
    qrcode_url: str


class QQBotQRPollResult(BaseModel):
    """Result of one QQ Bot QR binding status poll."""

    status: Literal["pending", "success", "expired"]
    credentials: list[QQBotQRCredentials] = Field(default_factory=list)


class QQBotQRWaitResult(BaseModel):
    """Terminal result of waiting for a QQ Bot QR binding task."""

    connected: bool
    credentials: list[QQBotQRCredentials] = Field(default_factory=list)
    message: str = ""


class QQBotQRLogin:
    """Two-phase QQ Bot QR binding flow.

    ``fetch_qr_code`` creates a task and keeps its one-time AES key in memory.
    ``poll`` or ``wait_for_login`` consumes that task and returns the AppID and
    AppSecret after the user confirms the binding in mobile QQ. Callers own
    credential persistence; the channel never writes secrets to disk.
    """

    def __init__(self, *, source: str = "octop", poll_interval: float = 2.0) -> None:
        if poll_interval <= 0:
            raise ValueError("poll_interval must be greater than zero")
        self.source = source
        self.poll_interval = poll_interval
        self._bind_keys: dict[str, str] = {}

    async def fetch_qr_code(self) -> QQBotQRCodeResponse:
        """Create a QQ Bot binding task and return its QR target URL."""
        key = base64.b64encode(secrets.token_bytes(32)).decode()
        response = await self._post_json(_QQ_BIND_CREATE_PATH, {"key": key})
        data = self._response_data(response, "create bind task")
        task_id = str(data.get("task_id") or "")
        if not task_id:
            raise RuntimeError("QQ Bot create bind task response missing task_id")

        self._bind_keys[task_id] = key
        query = urlencode({"task_id": task_id, "source": self.source, "_wv": 2})
        return QQBotQRCodeResponse(
            task_id=task_id,
            qrcode_url=f"{_QQ_CONNECT_BASE}/qqbot/openclaw/connect.html?{query}",
        )

    async def poll(self, task_id: str) -> QQBotQRPollResult:
        """Poll one binding task without blocking between requests."""
        key = self._bind_keys.get(task_id)
        if key is None:
            raise ValueError("Unknown or expired QQ Bot QR task")

        response = await self._post_json(_QQ_BIND_POLL_PATH, {"task_id": task_id})
        data = self._response_data(response, "poll bind result")
        status = int(str(data.get("status") or 0))

        if status == _QQ_BIND_STATUS_COMPLETED:
            app_id = str(data.get("bot_appid") or "")
            encrypted_secret = str(data.get("bot_encrypt_secret") or "")
            if not app_id or not encrypted_secret:
                raise RuntimeError("QQ Bot bind result missing application credentials")
            credentials = QQBotQRCredentials(
                app_id=app_id,
                app_secret=self._decrypt_secret(encrypted_secret, key),
                user_openid=str(data.get("user_openid") or "") or None,
            )
            self._bind_keys.pop(task_id, None)
            return QQBotQRPollResult(status="success", credentials=[credentials])

        if status == _QQ_BIND_STATUS_EXPIRED:
            self._bind_keys.pop(task_id, None)
            return QQBotQRPollResult(status="expired")

        return QQBotQRPollResult(status="pending")

    async def wait_for_login(self, task_id: str, *, timeout_s: float = 480.0) -> QQBotQRWaitResult:
        """Wait until a QR task succeeds, expires, or reaches the timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            try:
                result = await self.poll(task_id)
            except HTTPError as exc:
                logger.warning("QQ Bot QR poll failed; retrying: %s", exc)
                await asyncio.sleep(min(self.poll_interval, max(0.0, deadline - loop.time())))
                continue
            if result.status == "success":
                return QQBotQRWaitResult(connected=True, credentials=result.credentials, message="QR code confirmed")
            if result.status == "expired":
                return QQBotQRWaitResult(connected=False, message="QR code expired")
            await asyncio.sleep(min(self.poll_interval, max(0.0, deadline - loop.time())))

        self.cancel(task_id)
        return QQBotQRWaitResult(connected=False, message=f"QR login timeout after {timeout_s:g} seconds")

    def cancel(self, task_id: str) -> None:
        """Forget a pending QR task and its one-time decryption key."""
        self._bind_keys.pop(task_id, None)

    async def _post_json(self, path: str, payload: dict[str, str]) -> dict[str, object]:
        async with AsyncClient(base_url=_QQ_CONNECT_BASE, timeout=10.0) as client:
            response = await client.post(path, json=payload)
            response.raise_for_status()
            body: object = response.json()
        if not isinstance(body, dict):
            raise RuntimeError("QQ Bot QR endpoint returned a malformed response")
        return {str(key): value for key, value in body.items()}

    @staticmethod
    def _response_data(response: dict[str, object], action: str) -> dict[str, object]:
        if int(str(response.get("retcode") or 0)) != 0:
            raise RuntimeError(f"QQ Bot {action} failed: {response.get('msg') or 'unknown error'}")
        data = response.get("data")
        if not isinstance(data, dict):
            raise RuntimeError(f"QQ Bot {action} response missing data")
        return {str(key): value for key, value in data.items()}

    @staticmethod
    def _decrypt_secret(encrypted_secret: str, key: str) -> str:
        encrypted = base64.b64decode(encrypted_secret, validate=True)
        raw_key = base64.b64decode(key, validate=True)
        if len(encrypted) < 29 or len(raw_key) != 32:
            raise RuntimeError("QQ Bot bind result contains invalid encrypted credentials")
        nonce = encrypted[:12]
        ciphertext_and_tag = encrypted[12:]
        return AESGCM(raw_key).decrypt(nonce, ciphertext_and_tag, None).decode()
