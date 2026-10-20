"""WeChat iLink Bot HTTP API client.

Auth scheme mirrors the working reference implementation exactly — this is
what makes the long-poll session establish (otherwise getUpdates returns
``errcode=-14 session timeout`` indefinitely):

- ``AuthorizationType: ilink_bot_token``
- ``Authorization: Bearer <token>``
- ``X-WECHAT-UIN: <base64(random uint32)>``

The previous scheme (``Authorization: ilink_bot_token <token>`` with no
``X-WECHAT-UIN``) is rejected by the server and the session never binds.
"""

from __future__ import annotations

import base64
import json
import logging
import random
import struct
import uuid
from typing import Any, TypeVar

import aiohttp

from octop_gateway.channels.weixin.types import (
    GetConfigResponse,
    GetUpdatesResponse,
    SendMessageResponse,
    WeixinAPIError,
)

logger = logging.getLogger(__name__)

_Resp = TypeVar("_Resp", GetUpdatesResponse, SendMessageResponse, GetConfigResponse)

_EP_GET_UPDATES = "ilink/bot/getupdates"
_EP_SEND_MESSAGE = "ilink/bot/sendmessage"
_EP_GET_UPLOAD_URL = "ilink/bot/getuploadurl"
_EP_GET_CONFIG = "ilink/bot/getconfig"
_EP_SEND_TYPING = "ilink/bot/sendtyping"

_CHANNEL_VERSION = "2.2.0"
_AUTH_TYPE = "ilink_bot_token"
_ILINK_APP_ID = "bot"
_ILINK_APP_CLIENT_VERSION = str((2 << 16) | (2 << 8) | 0)
_HTTP_TIMEOUT_S = 45.0
_SUCCESS_CODE = 0

_MSG_TYPE_BOT = 2
_MSG_STATE_FINISH = 2

# Item content types
_ITEM_TYPE_TEXT = 1


def _wechat_uin() -> str:
    """Random ``X-WECHAT-UIN`` header value: base64 of a 4-byte uint32."""
    return base64.b64encode(struct.pack(">I", random.getrandbits(32))).decode("ascii")


def _client_id() -> str:
    return f"hg-weixin-{uuid.uuid4().hex}"


class WeixinAPIClient:
    """Thin async HTTP client for the WeChat iLink Bot API.

    Shares the channel's :class:`aiohttp.ClientSession`; never owns it.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        session: aiohttp.ClientSession,
        timeout_s: float | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._session = session
        self._timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "AuthorizationType": _AUTH_TYPE,
            "Authorization": f"Bearer {self.token}",
            "X-WECHAT-UIN": _wechat_uin(),
            "iLink-App-Id": _ILINK_APP_ID,
            "iLink-App-ClientVersion": _ILINK_APP_CLIENT_VERSION,
        }

    async def _post_json(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint}"
        headers = self._headers()
        body_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        headers["Content-Length"] = str(len(body_str.encode("utf-8")))

        async with self._session.post(
            url,
            data=body_str,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self._timeout_s or _HTTP_TIMEOUT_S),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise WeixinAPIError(ret=resp.status, errcode=resp.status, errmsg=f"HTTP {resp.status}: {body[:100]}")
            try:
                payload = await resp.json(content_type=None)
            except (aiohttp.ContentTypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                body_text = await resp.text()
                try:
                    payload = json.loads(body_text)
                except json.JSONDecodeError:
                    raise WeixinAPIError(ret=-1, errcode=-1, errmsg=f"parse error: {exc}") from exc

        ret = payload.get("ret")
        errcode = payload.get("errcode")
        if errcode is not None and errcode != _SUCCESS_CODE:
            raise WeixinAPIError(ret=ret or errcode or -1, errcode=errcode, errmsg=payload.get("errmsg"))
        if ret is not None and ret != _SUCCESS_CODE:
            raise WeixinAPIError(ret=ret, errcode=errcode, errmsg=payload.get("errmsg"))
        return payload  # type: ignore[no-any-return]

    async def _post(self, endpoint: str, data: dict[str, Any], response_type: type[_Resp]) -> _Resp:
        payload = await self._post_json(endpoint, data)
        parsed = response_type(**payload)
        if parsed.errcode is not None and parsed.errcode != 0:
            raise WeixinAPIError(ret=parsed.ret or parsed.errcode or -1, errcode=parsed.errcode, errmsg=parsed.errmsg)
        if parsed.ret is not None and parsed.ret != _SUCCESS_CODE:
            raise WeixinAPIError(
                ret=parsed.ret,
                errcode=getattr(parsed, "errcode", None),
                errmsg=getattr(parsed, "errmsg", None),
            )
        return parsed

    async def get_updates(self, sync_cursor: str, timeout_ms: int | None = None) -> GetUpdatesResponse:
        saved = self._timeout_s
        if timeout_ms is not None:
            self._timeout_s = (timeout_ms / 1000) + 5.0
        try:
            data: dict[str, Any] = {
                "get_updates_buf": sync_cursor,
                "base_info": {"channel_version": _CHANNEL_VERSION},
            }
            if timeout_ms is not None:
                data["longpolling_timeout_ms"] = timeout_ms
            return await self._post(_EP_GET_UPDATES, data, GetUpdatesResponse)
        finally:
            self._timeout_s = saved

    async def send_message(self, to_user_id: str, text: str, context_token: str = "") -> SendMessageResponse:
        return await self.send_items(
            to_user_id=to_user_id,
            items=[{"type": _ITEM_TYPE_TEXT, "text_item": {"text": text}}],
            context_token=context_token,
        )

    async def send_items(
        self,
        to_user_id: str,
        items: list[dict[str, Any]],
        context_token: str = "",
    ) -> SendMessageResponse:
        data = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": _client_id(),
                "message_type": _MSG_TYPE_BOT,
                "message_state": _MSG_STATE_FINISH,
                "context_token": context_token or None,
                "item_list": items,
            },
            "base_info": {"channel_version": _CHANNEL_VERSION},
        }
        return await self._post(_EP_SEND_MESSAGE, data, SendMessageResponse)

    async def get_upload_url(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = dict(payload)
        data.setdefault("base_info", {"channel_version": _CHANNEL_VERSION})
        return await self._post_json(_EP_GET_UPLOAD_URL, data)

    async def get_config(self, ilink_user_id: str, context_token: str = "") -> GetConfigResponse:
        data = {
            "ilink_user_id": ilink_user_id,
            "context_token": context_token,
            "base_info": {"channel_version": _CHANNEL_VERSION},
        }
        return await self._post(_EP_GET_CONFIG, data, GetConfigResponse)

    async def send_typing(self, ilink_user_id: str, typing_ticket: str, status: int) -> None:
        data = {
            "ilink_user_id": ilink_user_id,
            "typing_ticket": typing_ticket,
            "status": status,
            "base_info": {"channel_version": _CHANNEL_VERSION},
        }
        url = f"{self.base_url}/{_EP_SEND_TYPING}"
        headers = self._headers()
        body_str = json.dumps(data)
        headers["Content-Length"] = str(len(body_str.encode("utf-8")))
        async with self._session.post(
            url,
            data=body_str,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self._timeout_s or 10),
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise WeixinAPIError(ret=resp.status, errcode=resp.status, errmsg=f"HTTP {resp.status}")
            payload: dict[str, Any] = {}
            if body:
                try:
                    parsed = json.loads(body)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    payload = parsed
            ret = payload.get("ret")
            errcode = payload.get("errcode")
            if (errcode not in (None, 0)) or (ret not in (None, 0)):
                raise WeixinAPIError(
                    ret=int(ret or errcode or -1),
                    errcode=int(errcode) if errcode is not None else None,
                    errmsg=payload.get("errmsg"),
                )
