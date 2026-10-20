"""Tencent Yuanbao channel over binary WebSocket."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import secrets
import time
import urllib.parse
from collections.abc import Mapping
from datetime import datetime
from typing import cast

import aiohttp

from octop_gateway.channel import BaseChannel, MessageProcessor
from octop_gateway.channels.yuanbao import protocol as proto
from octop_gateway.channels.yuanbao.config import YuanbaoConfig, _YuanbaoToken
from octop_gateway.channels.yuanbao.constants import (
    _CST,
    _INBOUND_DEDUPE_TTL_SECONDS,
    _MAX_MEDIA_SIZE_BYTES,
    _RESOURCE_DOWNLOAD_PATH,
    _TOKEN_REFRESH_MARGIN_SECONDS,
    _UPLOAD_INFO_PATH,
)
from octop_gateway.channels.yuanbao.utils import (
    _basename_from_url,
    _compute_signature,
    _content_filename,
    _cos_sign,
    _first_image_info,
    _first_media_url,
    _guess_mime_type,
    _normalize_media_url,
    _optional_int,
    _parse_image_size,
    _redact_account,
    _resolve_media_filename,
    _resource_id_from_url,
    _single_text_body_text,
)
from octop_gateway.constraints import ChannelConstraints
from octop_gateway.models import (
    AudioContent,
    ChannelSubject,
    ContentPart,
    FileContent,
    ImageContent,
    InboundMessage,
    TextContent,
    VideoContent,
)

logger = logging.getLogger(__name__)


class YuanbaoChannel(BaseChannel):
    """Tencent Yuanbao bot channel over binary WebSocket."""

    channel_type = "yuanbao"

    def __init__(
        self,
        processor: MessageProcessor,
        *,
        config: YuanbaoConfig | None = None,
        channel_id: str | None = None,
        tenant_id: str | None = None,
        constraints: ChannelConstraints | None = None,
    ) -> None:
        self._config = config or YuanbaoConfig()
        super().__init__(
            processor,
            channel_id=channel_id,
            tenant_id=tenant_id,
            constraints=constraints,
            config=self._config,
        )
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._ping_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._connect_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future[bytes]] = {}
        self._seq_no = 0
        self._stopping = False
        self._should_reconnect = False
        self._connected = False
        self._token_cache: _YuanbaoToken | None = None
        self._bot_id = self._config.bot_id
        self._seen_message_ids: dict[str, float] = {}

    def _default_constraints(self) -> ChannelConstraints:
        return ChannelConstraints(
            typing_keepalive_interval=2.0,
            send_rate_limit=(2, 5.0),
            show_thinking=False,
            show_tool_hints=True,
        )

    async def start(self) -> None:
        """Fetch a Yuanbao token, open WebSocket, and auth-bind."""
        missing = self._config.missing_credentials()
        if missing:
            raise RuntimeError(f"YuanbaoChannel missing required credentials: {', '.join(missing)}")

        self._stopping = False
        await self._ensure_http()
        if self._config.probe_mode == "sign_token":
            token = await self._sign_token(force=True)
            logger.info(
                "YuanbaoChannel probe ok (bot_id=%s, api_domain=%s)", token.bot_id[:12], self._config.api_domain
            )
            return

        await self._connect_once(force_token=True)
        self._should_reconnect = True
        self._ping_task = asyncio.create_task(self._ping_loop())
        logger.info("YuanbaoChannel started (bot_id=%s, api_domain=%s)", self._bot_id[:12], self._config.api_domain)

    async def stop(self) -> None:
        """Stop background tasks, close WebSocket and HTTP session."""
        self._stopping = True
        self._should_reconnect = False
        self._connected = False

        for task in (self._reconnect_task, self._ping_task, self._receive_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._reconnect_task = None
        self._ping_task = None
        self._receive_task = None

        if self._ws and not self._ws.closed:
            with contextlib.suppress(Exception):
                await self._ws.close()
        self._ws = None

        self._fail_pending(RuntimeError("YuanbaoChannel stopped"))
        await self._close_http()
        logger.info("YuanbaoChannel stopped")

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        """Send text through Yuanbao WebSocket."""
        await self._send_msg_body(subject, proto.encode_text_body(text))

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        """Send rich content through Yuanbao WebSocket when possible."""
        msg_body: proto.YuanbaoMessageBody = []
        for part in parts:
            if isinstance(part, TextContent):
                if part.text:
                    msg_body.extend(proto.encode_text_body(part.text))
            else:
                msg_body.extend(await self._media_part_to_msg_body(part))

        if msg_body:
            await self._send_msg_body(subject, msg_body)

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        msg_body = await self._media_part_to_msg_body(media)
        text = _single_text_body_text(msg_body)
        if text is not None:
            await self._send_text(subject, text)
        elif msg_body:
            await self._send_msg_body(subject, msg_body)

    async def _media_part_to_msg_body(self, part: ContentPart) -> proto.YuanbaoMessageBody:
        label = self._get_media_label(part)
        if isinstance(part, TextContent):
            return proto.encode_text_body(part.text)
        if not isinstance(part, ImageContent | FileContent | AudioContent | VideoContent):
            return proto.encode_text_body(f"[{label}]")

        try:
            data, mime_type = await self.load_media_bytes(part)
            filename = _resolve_media_filename(part, mime_type)
            if not mime_type or mime_type == "application/octet-stream":
                mime_type = _guess_mime_type(filename)
            upload = await self._upload_media_to_yuanbao(data, filename, mime_type)
            if isinstance(part, ImageContent):
                width = part.width or int(upload.get("width") or 0)
                height = part.height or int(upload.get("height") or 0)
                return proto.build_image_msg_body(
                    url=str(upload["url"]),
                    uuid=str(upload.get("uuid") or ""),
                    filename=filename,
                    size=int(upload.get("size") or len(data)),
                    width=width,
                    height=height,
                    mime_type=mime_type,
                )
            return proto.build_file_msg_body(
                url=str(upload["url"]),
                filename=filename,
                uuid=str(upload.get("uuid") or ""),
                size=int(upload.get("size") or len(data)),
            )
        except Exception:  # pylint: disable=broad-except
            # MediaBackend and Yuanbao upload implementations have adapter-specific errors.
            logger.exception("Failed to upload Yuanbao media: %s", type(part).__name__)
            url_body = self._media_url_msg_body(part)
            if url_body:
                return url_body
            if getattr(part, "data", None) or getattr(part, "local_path", None):
                return proto.encode_text_body(f"[{label} (local file upload failed)]")
            return proto.encode_text_body(f"[{label} (not deliverable on Yuanbao)]")

    def _media_url_msg_body(self, part: ContentPart) -> proto.YuanbaoMessageBody:
        url = _normalize_media_url(self._get_media_url(part) or "", api_domain=self._config.api_domain)
        if not url:
            return []
        if isinstance(part, ImageContent):
            return proto.build_image_msg_body(
                url=url,
                uuid=part.alt_text or _basename_from_url(url) or "image",
                filename=part.alt_text or _basename_from_url(url) or "image",
                size=part.size or 0,
                width=part.width or 0,
                height=part.height or 0,
                mime_type=part.mime_type or _guess_mime_type(url),
            )
        if isinstance(part, FileContent | AudioContent | VideoContent):
            filename = _resolve_media_filename(part, part.mime_type or _guess_mime_type(url))
            return proto.build_file_msg_body(
                url=url,
                filename=filename,
                uuid=filename,
                size=part.size or 0,
            )
        return []

    async def _send_typing_indicator(self, subject: ChannelSubject) -> None:
        await self._send_reply_heartbeat(subject, proto.HEARTBEAT_RUNNING)

    async def _send_reply_heartbeat(self, subject: ChannelSubject, heartbeat: int) -> None:
        meta = dict(subject.metadata or {})
        from_account = self._bot_id or meta.get("bot_id") or self._config.bot_id
        if not from_account:
            return

        group_code = str(meta.get("group_code") or "")
        if group_code or subject.chat_type == "group":
            payload = proto.encode_group_heartbeat_payload(
                from_account,
                group_code or subject.subject_id,
                send_time=int(time.time() * 1000),
                heartbeat=heartbeat,
            )
            await self._request(proto.CMD_SEND_GROUP_HEARTBEAT, proto.MODULE_BIZ, payload, wait_response=False)
            return

        to_account = str(meta.get("reply_to_account") or subject.subject_id)
        if to_account:
            payload = proto.encode_private_heartbeat_payload(from_account, to_account, heartbeat=heartbeat)
            await self._request(proto.CMD_SEND_PRIVATE_HEARTBEAT, proto.MODULE_BIZ, payload, wait_response=False)

    def parse_inbound(self, raw_payload: object) -> InboundMessage:
        """Parse Yuanbao pushed JSON or a legacy callback dict into InboundMessage."""
        if isinstance(raw_payload, InboundMessage):
            return raw_payload

        if isinstance(raw_payload, bytes):
            raw_payload = raw_payload.decode("utf-8", errors="replace")
        if isinstance(raw_payload, str):
            raw_payload = json.loads(raw_payload)

        data = cast(proto.YuanbaoMapping, raw_payload) if isinstance(raw_payload, Mapping) else {}
        if "msg_body" in data:
            return self._parse_yuanbao_message(data)
        return self._parse_legacy_message(data)

    async def fetch_remote_media(self, url: str) -> tuple[bytes, str]:
        """Download Yuanbao-hosted media with signed token headers."""
        url = _normalize_media_url(url, api_domain=self._config.api_domain)
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Yuanbao media URL is not HTTP(S): {url}")
        original_url = url
        url = await self._resolve_resource_download_url(url)
        http = await self._ensure_http()
        headers: dict[str, str] = {}
        if url == original_url:
            with contextlib.suppress(Exception):
                token = await self._sign_token()
                headers["X-Token"] = token.token
                headers["Authorization"] = f"Bearer {token.token}"
        async with http.get(url, headers=headers) as resp:
            resp.raise_for_status()
            content_type = resp.content_type or "application/octet-stream"
            return await resp.read(), content_type

    async def _resolve_resource_download_url(self, url: str) -> str:
        resource_id = _resource_id_from_url(url)
        if not resource_id:
            return url

        token = await self._sign_token()
        for attempt in range(2):
            try:
                return await self._fetch_resource_download_url(resource_id, token)
            except aiohttp.ClientResponseError as exc:
                if exc.status != 401 or attempt > 0:
                    raise
                self._token_cache = None
                token = await self._sign_token(force=True)
        return url

    async def _fetch_resource_download_url(self, resource_id: str, token: _YuanbaoToken) -> str:
        http = await self._ensure_http()
        headers = {
            "Content-Type": "application/json",
            "X-ID": token.bot_id or self._bot_id or self._config.app_key,
            "X-Token": token.token,
            "X-Source": token.source or self._config.source or "web",
        }
        if self._config.route_env:
            headers["X-Route-Env"] = self._config.route_env

        api_url = f"{self._config.api_domain}{_RESOURCE_DOWNLOAD_PATH}"
        timeout = aiohttp.ClientTimeout(total=self._config.request_timeout)
        async with http.get(api_url, params={"resourceId": resource_id}, headers=headers, timeout=timeout) as resp:
            resp.raise_for_status()
            payload = await resp.json(content_type=None)

        if not isinstance(payload, Mapping):
            raise RuntimeError("Yuanbao resource download returned malformed response")
        code = payload.get("code")
        if code not in (None, 0):
            raise RuntimeError(f"Yuanbao resource download failed: code={code}, msg={payload.get('msg') or ''}")
        data = payload.get("data") if isinstance(payload.get("data"), Mapping) else payload
        if not isinstance(data, Mapping):
            raise RuntimeError("Yuanbao resource download response missing data")
        real_url = str(data.get("url") or data.get("realUrl") or "").strip()
        if not real_url:
            raise RuntimeError("Yuanbao resource download response missing url")
        return _normalize_media_url(real_url, api_domain=self._config.api_domain)

    async def _upload_media_to_yuanbao(self, data: bytes, filename: str, mime_type: str) -> proto.YuanbaoDict:
        if not data:
            raise ValueError("Yuanbao media is empty")
        if len(data) > _MAX_MEDIA_SIZE_BYTES:
            size_mb = len(data) / 1024 / 1024
            raise ValueError(f"Yuanbao media is too large: {size_mb:.1f} MB")

        token = await self._sign_token()
        credentials = await self._get_cos_upload_credentials(token, filename)
        upload = await self._put_media_to_cos(data, filename, mime_type, credentials)
        if mime_type.startswith("image/"):
            width, height = _parse_image_size(data)
            if width:
                upload["width"] = width
            if height:
                upload["height"] = height
        return upload

    async def _get_cos_upload_credentials(self, token: _YuanbaoToken, filename: str) -> proto.YuanbaoMapping:
        http = await self._ensure_http()
        headers = {
            "Content-Type": "application/json",
            "X-Token": token.token,
            "X-ID": token.bot_id or self._bot_id or self._config.app_key,
            "X-Source": "web",
        }
        if self._config.route_env:
            headers["X-Route-Env"] = self._config.route_env
        body = {
            "fileName": filename,
            "fileId": secrets.token_hex(16),
            "docFrom": "localDoc",
            "docOpenId": "",
        }
        url = f"{self._config.api_domain}{_UPLOAD_INFO_PATH}"
        timeout = aiohttp.ClientTimeout(total=self._config.request_timeout)
        async with http.post(url, json=body, timeout=timeout, headers=headers) as resp:
            resp.raise_for_status()
            result = await resp.json(content_type=None)

        if not isinstance(result, Mapping):
            raise RuntimeError("Yuanbao genUploadInfo returned malformed response")
        code = result.get("code")
        if code not in (None, 0):
            raise RuntimeError(f"Yuanbao genUploadInfo failed: code={code}, msg={result.get('msg') or ''}")
        data = result.get("data") if isinstance(result.get("data"), Mapping) else result
        if not isinstance(data, Mapping):
            raise RuntimeError("Yuanbao genUploadInfo response missing data")
        missing = [
            key for key in ("bucketName", "location", "encryptTmpSecretId", "encryptTmpSecretKey") if not data.get(key)
        ]
        if missing:
            raise RuntimeError(f"Yuanbao genUploadInfo response missing fields: {', '.join(missing)}")
        return data

    async def _put_media_to_cos(
        self,
        data: bytes,
        filename: str,
        mime_type: str,
        credentials: proto.YuanbaoMapping,
    ) -> proto.YuanbaoDict:
        del filename
        bucket = str(credentials.get("bucketName") or "")
        region = str(credentials.get("region") or "")
        cos_key = str(credentials.get("location") or "")
        resource_url = str(credentials.get("resourceUrl") or "")
        secret_id = str(credentials.get("encryptTmpSecretId") or "")
        secret_key = str(credentials.get("encryptTmpSecretKey") or "")
        session_token = str(credentials.get("encryptToken") or "")
        if not bucket or not cos_key or not secret_id or not secret_key:
            raise RuntimeError("Yuanbao COS credentials are incomplete")

        cos_host = f"{bucket}.cos.accelerate.myqcloud.com" if bucket else ""
        if not cos_host and region:
            cos_host = f"{bucket}.cos.{region}.myqcloud.com"
        encoded_key = urllib.parse.quote(cos_key, safe="/")
        cos_url = f"https://{cos_host}/{encoded_key.lstrip('/')}"
        headers_to_sign = {
            "host": cos_host,
            "content-type": mime_type,
            "x-cos-security-token": session_token,
        }
        now = int(time.time())
        start_time = _optional_int(credentials.get("startTime")) or now
        expired_time = _optional_int(credentials.get("expiredTime")) or now + 3600
        authorization = _cos_sign(
            method="put",
            path=f"/{encoded_key.lstrip('/')}",
            params={},
            headers=headers_to_sign,
            secret_id=secret_id,
            secret_key=secret_key,
            start_time=start_time,
            expire_seconds=max(expired_time - now, 60),
        )
        put_headers = {
            "Authorization": authorization,
            "Content-Type": mime_type,
            "x-cos-security-token": session_token,
        }
        http = await self._ensure_http()
        timeout = aiohttp.ClientTimeout(total=max(self._config.request_timeout, 120.0))
        async with http.put(cos_url, data=data, headers=put_headers, timeout=timeout) as resp:
            resp.raise_for_status()

        return {
            "url": resource_url or cos_url,
            "uuid": hashlib.md5(data, usedforsecurity=False).hexdigest(),
            "size": len(data),
        }

    async def _connect_once(self, *, force_token: bool = False) -> None:
        async with self._connect_lock:
            if self._stopping:
                return

            http = await self._ensure_http()
            token = await self._sign_token(force=force_token)
            self._bot_id = token.bot_id

            old_ws = self._ws
            if old_ws and not old_ws.closed:
                with contextlib.suppress(Exception):
                    await old_ws.close()

            timeout = aiohttp.ClientWSTimeout(ws_close=self._config.connect_timeout)
            ws = await http.ws_connect(self._config.ws_url, timeout=timeout)
            self._ws = ws
            self._connected = True
            self._receive_task = asyncio.create_task(self._receive_loop(ws))

            try:
                await self._auth_bind(token)
            except Exception:  # pylint: disable=broad-except
                # Any authentication failure must roll back the partially opened socket.
                self._connected = False
                if self._ws is ws:
                    self._ws = None
                with contextlib.suppress(Exception):
                    await ws.close()
                if self._receive_task:
                    self._receive_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await self._receive_task
                raise

    async def _send_msg_body(self, subject: ChannelSubject, msg_body: proto.YuanbaoMessageBody) -> None:
        meta = cast(proto.YuanbaoDict, dict(subject.metadata or {}))
        from_account = str(meta.get("bot_id") or self._bot_id or self._config.bot_id)
        if not from_account:
            raise RuntimeError("YuanbaoChannel is not authenticated")

        prefix = "grp" if (str(meta.get("group_code") or "") or subject.chat_type == "group") else "c2c"
        outbound_msg_id = self._next_business_msg_id(prefix)
        try:
            code, message = await self._send_msg_body_once(
                subject,
                msg_body,
                meta,
                from_account=from_account,
                outbound_msg_id=outbound_msg_id,
            )
            if code != proto.RET_SUCCESS:
                raise RuntimeError(f"Yuanbao send failed: code={code}, message={message}")
        finally:
            with contextlib.suppress(Exception):
                await self._send_reply_heartbeat(subject, proto.HEARTBEAT_FINISH)

    async def _send_msg_body_once(
        self,
        subject: ChannelSubject,
        msg_body: proto.YuanbaoMessageBody,
        meta: proto.YuanbaoDict,
        *,
        from_account: str,
        outbound_msg_id: str,
    ) -> tuple[int, str]:
        group_code = str(meta.get("group_code") or "")

        if group_code or subject.chat_type == "group":
            payload = proto.encode_group_message_payload(
                group_code=group_code or subject.subject_id,
                from_account=from_account,
                msg_body=msg_body,
                msg_id=outbound_msg_id,
                ref_msg_id=str(meta.get("msg_id") or ""),
            )
            response = await self._request(
                proto.CMD_SEND_GROUP_MESSAGE,
                proto.MODULE_BIZ,
                payload,
                msg_id=outbound_msg_id,
            )
        else:
            to_account = str(meta.get("reply_to_account") or subject.subject_id)
            payload = proto.encode_c2c_message_payload(
                to_account=to_account,
                from_account=from_account,
                msg_body=msg_body,
                msg_id=outbound_msg_id,
                group_code=str(meta.get("private_from_group_code") or ""),
            )
            response = await self._request(
                proto.CMD_SEND_C2C_MESSAGE,
                proto.MODULE_BIZ,
                payload,
                msg_id=outbound_msg_id,
            )

        code, message = proto.decode_status_response(response)
        logger.info(
            "Yuanbao send response: code=%s message=%s business_msg_id=%s from=%s",
            code,
            message,
            outbound_msg_id,
            _redact_account(from_account),
        )
        return code, message

    async def _sign_token(self, *, force: bool = False) -> _YuanbaoToken:
        now = time.time()
        if not force and self._token_cache and now < self._token_cache.expires_at:
            return self._token_cache

        nonce = secrets.token_hex(16)
        timestamp = datetime.now(_CST).isoformat(timespec="seconds")
        signature = _compute_signature(self._config.app_secret, nonce, timestamp, self._config.app_key)
        payload = {
            "app_key": self._config.app_key,
            "nonce": nonce,
            "signature": signature,
            "timestamp": timestamp,
        }

        http = await self._ensure_http()
        url = f"{self._config.api_domain}{proto.SIGN_TOKEN_PATH}"
        timeout = aiohttp.ClientTimeout(total=self._config.request_timeout)
        headers = {
            "Content-Type": "application/json",
            "X-AppVersion": self._config.app_version,
            "X-OperationSystem": self._config.app_operation_system,
            "X-Instance-Id": self._config.instance_id,
            "X-Bot-Version": self._config.bot_version,
        }
        if self._config.route_env:
            headers["X-Route-Env"] = self._config.route_env
        async with http.post(url, json=payload, timeout=timeout, headers=headers) as resp:
            try:
                body = await resp.json(content_type=None)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RuntimeError(f"Yuanbao sign-token returned non-JSON response: HTTP {resp.status}") from exc

        if not isinstance(body, Mapping):
            raise RuntimeError("Yuanbao sign-token returned malformed response")
        code = int(body.get("code") or 0)
        if code != 0:
            raise RuntimeError(f"Yuanbao sign-token failed: code={code}, msg={body.get('msg') or ''}")

        data = body.get("data")
        if not isinstance(data, Mapping):
            raise RuntimeError("Yuanbao sign-token response missing data")
        token = str(data.get("token") or "")
        bot_id = str(data.get("bot_id") or self._config.bot_id or "")
        source = str(data.get("source") or self._config.source or "")
        duration = int(data.get("duration") or 3600)
        if not token or not bot_id:
            raise RuntimeError("Yuanbao sign-token response missing token or bot_id")

        expires_at = time.time() + max(duration - _TOKEN_REFRESH_MARGIN_SECONDS, 60)
        self._token_cache = _YuanbaoToken(
            token=token,
            bot_id=bot_id,
            source=source,
            expires_at=expires_at,
            duration=duration,
        )
        self._config.token = token
        self._config.bot_id = bot_id
        self._config.identifier = bot_id
        self._config.source = source
        self._bot_id = bot_id
        return self._token_cache

    async def _auth_bind(self, token: _YuanbaoToken) -> None:
        payload = proto.encode_auth_bind_payload(
            bot_id=token.bot_id,
            source=token.source,
            token=token.token,
            route_env=self._config.route_env,
            app_version=self._config.app_version,
            app_operation_system=self._config.app_operation_system,
            bot_version=self._config.bot_version,
            instance_id=self._config.instance_id,
        )
        response = await self._request(proto.CMD_AUTH_BIND, proto.MODULE_CONN_ACCESS, payload)
        code, message = proto.decode_status_response(response)
        logger.info("Yuanbao auth-bind response: code=%s message=%s", code, message)
        if code in (proto.RET_SUCCESS, proto.RET_ALREADY_AUTH):
            return
        if code in proto.TOKEN_EXPIRED_CODES:
            self._token_cache = None
        raise RuntimeError(f"Yuanbao auth-bind failed: code={code}, message={message}")

    async def _request(
        self,
        cmd: str,
        module: str,
        payload: bytes,
        *,
        msg_id: str | None = None,
        wait_response: bool = True,
    ) -> bytes:
        ws = self._ws
        if not ws or ws.closed or not self._connected:
            raise RuntimeError("YuanbaoChannel is not connected")

        request_id = msg_id or f"{cmd}_{self._next_seq_no()}"
        future: asyncio.Future[bytes] | None = None
        if wait_response:
            future = asyncio.get_running_loop().create_future()
            self._pending[request_id] = future

        packet = proto.encode_request(cmd, module, request_id, self._next_seq_no(), payload)
        if cmd != proto.CMD_PING:
            logger.debug("Yuanbao send request: cmd=%s module=%s msg_id=%s", cmd, module, request_id)
        await ws.send_bytes(packet)

        if not future:
            return b""

        try:
            return await asyncio.wait_for(future, timeout=self._config.request_timeout)
        finally:
            self._pending.pop(request_id, None)

    async def _receive_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    await self._handle_binary_frame(bytes(msg.data))
                elif msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_text_frame(str(msg.data))
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("Yuanbao WebSocket error: %s", ws.exception())
                    break
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE):
                    break
        except asyncio.CancelledError:
            raise
        except Exception:  # pylint: disable=broad-except
            # Keep WebSocket transport failures inside the connection lifecycle.
            logger.exception("Yuanbao receive loop error")
        finally:
            if self._ws is ws:
                self._connected = False
                self._ws = None
            if not self._stopping and self._should_reconnect:
                logger.warning("Yuanbao WebSocket closed; scheduling reconnect")
                self._fail_pending(RuntimeError("Yuanbao WebSocket closed"))
                self._schedule_reconnect()

    async def _handle_binary_frame(self, frame: bytes) -> None:
        try:
            message = proto.decode_conn_msg(frame)
        except (IndexError, TypeError, UnicodeDecodeError, ValueError):
            logger.exception("Failed to decode Yuanbao ConnMsg")
            return

        head = message.get("head") or {}
        cmd_type = int(head.get("cmd_type") or 0)
        cmd = str(head.get("cmd") or "")
        msg_id = str(head.get("msg_id") or "")

        if cmd_type == proto.CMD_TYPE_RESPONSE:
            future = self._pending.pop(msg_id, None)
            if future and not future.done():
                future.set_result(bytes(message.get("data") or b""))
            elif cmd != proto.CMD_PING:
                logger.debug("Yuanbao response without waiter: cmd=%s msg_id=%s", cmd, msg_id)
            return

        if cmd_type != proto.CMD_TYPE_PUSH:
            return

        if head.get("need_ack"):
            with contextlib.suppress(Exception):
                await self._send_raw(proto.encode_push_ack(head, self._next_seq_no()))

        if cmd == proto.CMD_INBOUND_MESSAGE:
            raw = bytes(message.get("data") or b"").decode("utf-8", errors="replace")
            logger.info("Yuanbao inbound push received: msg_id=%s", msg_id)
            await self._handle_text_frame(raw)
        elif cmd == proto.CMD_KICKOUT:
            logger.warning("Yuanbao channel received kickout push")
        elif cmd == proto.CMD_UPDATE_META:
            logger.debug("Yuanbao channel received update-meta push")
        else:
            logger.debug("Yuanbao channel ignored push cmd=%s", cmd)

    async def _handle_text_frame(self, frame: str) -> None:
        try:
            payload = json.loads(frame)
        except json.JSONDecodeError:
            logger.debug("Yuanbao text frame is not JSON")
            return
        if not isinstance(payload, Mapping):
            return

        if "msg_body" in payload:
            inbound_msg_id = str(payload.get("msg_id") or payload.get("msg_key") or payload.get("MsgKey") or "")
            if inbound_msg_id and not self._remember_message_id(inbound_msg_id):
                logger.info("Yuanbao duplicate inbound skipped: msg_id=%s", inbound_msg_id)
                return
            logger.info(
                "Yuanbao inbound message: callback=%s from=%s group=%s msg_id=%s",
                payload.get("callback_command", ""),
                _redact_account(str(payload.get("from_account") or "")),
                payload.get("group_code", ""),
                inbound_msg_id,
            )
            with contextlib.suppress(Exception):
                inbound = self.parse_inbound(payload)
                if inbound.channel_subject:
                    await self._send_typing_indicator(inbound.channel_subject)

        if self._enqueue_callback:
            self._enqueue_callback(dict(payload))
        else:
            logger.warning("Yuanbao inbound payload dropped: enqueue callback is not set")

    async def _ping_loop(self) -> None:
        while not self._stopping:
            await asyncio.sleep(self._config.heartbeat_interval)
            if self._stopping:
                return
            if not self._connected:
                continue
            with contextlib.suppress(Exception):
                await self._request(proto.CMD_PING, proto.MODULE_CONN_ACCESS, b"", wait_response=False)

    def _schedule_reconnect(self) -> None:
        if self._stopping or not self._should_reconnect:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        delays = (1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
        attempt = 0
        while not self._stopping and self._should_reconnect:
            delay = delays[min(attempt, len(delays) - 1)]
            await asyncio.sleep(delay)
            if self._stopping or not self._should_reconnect:
                return
            try:
                await self._connect_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # pylint: disable=broad-except
                # Reconnect must absorb all transport and authentication failures.
                attempt += 1
                logger.exception("Yuanbao reconnect failed; retrying")
                continue
            logger.info("YuanbaoChannel reconnected (bot_id=%s)", self._bot_id[:12])
            return

    async def _send_raw(self, packet: bytes) -> None:
        ws = self._ws
        if not ws or ws.closed:
            raise RuntimeError("YuanbaoChannel is not connected")
        await ws.send_bytes(packet)

    def _next_seq_no(self) -> int:
        self._seq_no = (self._seq_no + 1) & 0xFFFFFFFF
        return self._seq_no

    def _next_business_msg_id(self, prefix: str) -> str:
        return f"{prefix}_{self._next_seq_no()}"

    def _remember_message_id(self, msg_id: str) -> bool:
        now = time.monotonic()
        expired = [key for key, expires_at in self._seen_message_ids.items() if expires_at <= now]
        for key in expired:
            self._seen_message_ids.pop(key, None)
        if self._seen_message_ids.get(msg_id, 0) > now:
            return False
        self._seen_message_ids[msg_id] = now + _INBOUND_DEDUPE_TTL_SECONDS
        return True

    def _fail_pending(self, exc: Exception) -> None:
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()

    def _parse_yuanbao_message(self, data: proto.YuanbaoMapping) -> InboundMessage:
        group_code = str(data.get("group_code") or "")
        from_account = str(data.get("from_account") or "unknown")
        msg_id = str(data.get("msg_id") or data.get("msg_key") or data.get("MsgKey") or "")
        subject_id = group_code or from_account
        is_group = bool(group_code) or str(data.get("callback_command") or "").startswith("Group.")

        content_parts: list[ContentPart] = []
        for body in data.get("msg_body") or []:
            if not isinstance(body, Mapping):
                continue
            msg_type = str(body.get("msg_type") or "")
            content = body.get("msg_content") if isinstance(body.get("msg_content"), Mapping) else {}
            content_map = content if isinstance(content, Mapping) else {}
            if msg_type == proto.MSG_TYPE_TEXT:
                text = str(content_map.get("text") or "")
                if text:
                    content_parts.append(TextContent(text=text))
            elif msg_type == proto.MSG_TYPE_IMAGE:
                image_info = _first_image_info(content_map)
                url = _first_media_url(content_map, api_domain=self._config.api_domain)
                if url:
                    content_parts.append(
                        ImageContent(
                            url=url,
                            width=_optional_int(image_info.get("width")) if image_info else None,
                            height=_optional_int(image_info.get("height")) if image_info else None,
                            size=_optional_int(image_info.get("size")) if image_info else None,
                        )
                    )
            elif msg_type == proto.MSG_TYPE_FILE:
                url = _normalize_media_url(str(content_map.get("url") or ""), api_domain=self._config.api_domain)
                content_parts.append(
                    FileContent(
                        url=url,
                        filename=_content_filename(content_map),
                        size=_optional_int(content_map.get("file_size")),
                    )
                )
            elif msg_type == proto.MSG_TYPE_SOUND:
                url = _first_media_url(content_map, api_domain=self._config.api_domain)
                if url:
                    content_parts.append(
                        AudioContent(
                            url=url,
                            size=_optional_int(content_map.get("file_size")),
                        )
                    )
            elif msg_type == proto.MSG_TYPE_VIDEO:
                url = _first_media_url(content_map, api_domain=self._config.api_domain)
                if url:
                    content_parts.append(
                        VideoContent(
                            url=url,
                            size=_optional_int(content_map.get("file_size")),
                            thumbnail_url=_normalize_media_url(
                                str(content_map.get("thumb_url") or ""),
                                api_domain=self._config.api_domain,
                            ),
                        )
                    )
            else:
                text = str(content_map.get("text") or content_map.get("desc") or "")
                if text:
                    content_parts.append(TextContent(text=text))

        if not content_parts:
            content_parts.append(TextContent(text=""))

        trace_id = ""
        log_ext = data.get("log_ext")
        if isinstance(log_ext, Mapping):
            trace_id = str(log_ext.get("trace_id") or "")
        trace_id = str(data.get("trace_id") or trace_id)

        metadata = {
            "callback_command": data.get("callback_command", ""),
            "from_account": from_account,
            "reply_to_account": from_account,
            "to_account": data.get("to_account", ""),
            "group_id": data.get("group_id", ""),
            "group_code": group_code,
            "group_name": data.get("group_name", ""),
            "msg_id": msg_id,
            "msg_key": data.get("msg_key") or data.get("MsgKey") or "",
            "msg_seq": data.get("msg_seq", 0),
            "msg_random": data.get("msg_random", 0),
            "msg_time": data.get("msg_time", 0),
            "bot_owner_id": data.get("bot_owner_id", ""),
            "private_from_group_code": data.get("private_from_group_code", ""),
            "trace_id": trace_id,
            "bot_id": self._bot_id or self._config.bot_id,
        }

        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            channel_subject=ChannelSubject(
                subject_id=subject_id,
                display_name=str(data.get("sender_nickname") or ""),
                chat_type="group" if is_group else "direct",
                metadata=metadata,
            ),
            channel_session_id=group_code or from_account,
            content=content_parts,
            metadata=metadata,
        )

    def _parse_legacy_message(self, data: proto.YuanbaoMapping) -> InboundMessage:
        sender_id = str(data.get("from_user") or "unknown")
        conversation_id = str(data.get("conversation_id") or "")
        msg_type = str(data.get("message_type") or "text")
        content_data = data.get("content") if isinstance(data.get("content"), Mapping) else {}
        content_map = content_data if isinstance(content_data, Mapping) else {}

        content_parts: list[ContentPart] = []
        if msg_type == "text":
            content_parts.append(TextContent(text=str(content_map.get("text") or "")))
        elif msg_type == "image":
            content_parts.append(
                ImageContent(
                    url=_normalize_media_url(str(content_map.get("url") or ""), api_domain=self._config.api_domain)
                )
            )
        elif msg_type == "file":
            content_parts.append(
                FileContent(
                    url=_normalize_media_url(str(content_map.get("url") or ""), api_domain=self._config.api_domain),
                    filename=str(content_map.get("filename") or ""),
                )
            )
        elif msg_type == "audio":
            content_parts.append(
                AudioContent(
                    url=_normalize_media_url(str(content_map.get("url") or ""), api_domain=self._config.api_domain)
                )
            )
        elif msg_type == "video":
            content_parts.append(
                VideoContent(
                    url=_normalize_media_url(str(content_map.get("url") or ""), api_domain=self._config.api_domain)
                )
            )
        else:
            content_parts.append(TextContent(text=str(content_map.get("text") or content_map)))

        metadata = {
            "message_id": data.get("message_id", ""),
            "conversation_id": conversation_id,
            "raw_type": msg_type,
        }
        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            channel_subject=ChannelSubject(subject_id=sender_id, chat_type="direct", metadata=metadata),
            channel_session_id=conversation_id,
            content=content_parts,
            metadata=metadata,
        )
