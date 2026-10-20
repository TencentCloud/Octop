"""WeChat (iLink Bot) channel: long-poll based message receiving.

Uses WeChat iLink Bot API (https://ilinkai.weixin.qq.com) with:
- HTTP long-poll for receiving messages (getUpdates)
- HTTP API for sending messages (sendMessage)
- Typing indicator support (sendTyping)
- No public callback URL required — client pulls messages from server.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import mimetypes
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from octop_gateway.channel import BaseChannel, ChannelConfig, ChannelCredentialsError, MessageProcessor
from octop_gateway.channels.weixin.api import WeixinAPIClient
from octop_gateway.channels.weixin.text import split_weixin_text
from octop_gateway.channels.weixin.types import GetUpdatesResponse, WeixinAPIError, WeixinMessage
from octop_gateway.constraints import ChannelConstraints
from octop_gateway.models import (
    ChannelSubject,
    ContentPart,
    FileContent,
    ImageContent,
    InboundMessage,
    TextContent,
    VideoContent,
)
from octop_gateway.push_routing import WEIXIN_CONTEXT_TOKEN_KEY, alias_subject_fields

logger = logging.getLogger(__name__)

_API_BASE = "https://ilinkai.weixin.qq.com"

# Defaults
_DEFAULT_LONG_POLL_TIMEOUT_MS = 35000

# Message kinds (iLink message_type)
_MSG_TYPE_USER = 1

# Media kinds (iLink getUploadUrl media_type)
_MEDIA_TYPE_IMAGE = 1
_MEDIA_TYPE_VIDEO = 2
_MEDIA_TYPE_FILE = 3

# Message item types
_ITEM_TYPE_TEXT = 1
_ITEM_TYPE_IMAGE = 2
_ITEM_TYPE_VOICE = 3
_ITEM_TYPE_FILE = 4
_ITEM_TYPE_VIDEO = 5

_MAX_MEDIA_SIZE = 100 * 1024 * 1024
_CDN_MARKER_PREFIX = "weixin-cdn:"

# Session lifecycle
_SESSION_EXPIRED_CODE = -14
_AUTH_FAILED_CODE = -2
# getUpdates -14 means the iLink session expired and must be re-established by
# re-scanning the QR. Pausing avoids hammering the API with calls that keep
# failing; the channel reports "disconnected" to the dashboard meanwhile.
_SESSION_PAUSE_S = 300.0

# Typing indicator status values. status=2 clears the WeChat "thinking" light.
_TYPING_START = 1
_TYPING_STOP = 2
# How long to wait for the thinking light before sending one placeholder bubble.
_PLACEHOLDER_WAIT_S = 4.0
_PLACEHOLDER_TEXT = "⏳ 思考中..."
_TYPING_KEEPALIVE_S = 5.0
# Thinking-light calls must not hold up the answer. The shared client timeout
# is 45s; this cap only applies to getconfig / sendtyping.
_TYPING_HTTP_TIMEOUT_S = 3.0

ContextTokenListener = Any


@dataclass
class WeixinAccountConfig:
    """Single WeChat iLink account configuration."""

    account_id: str
    token: str
    account_name: str = ""
    base_url: str = _API_BASE
    bot_uin: str = ""
    user_uin: str = ""


@dataclass
class WeixinConfig(ChannelConfig):
    """WeChat iLink channel configuration.

    Attributes:
        accounts: List of WeChat iLink account configurations. Each account
            represents one bot account (``account_id`` + ``token``).
        media_dir: Local directory for media file storage.
        channel_id: Optional explicit channel ID; auto-generated UUID if omitted.
        tenant_id: Optional tenant identifier for multi-tenant deployments.
    """

    accounts: list[WeixinAccountConfig] = field(default_factory=list)
    media_dir: str = "~/.lightclaw/media"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeixinConfig:
        """Parse flat ``{token, bot_uin}`` or ``accounts[]`` config.

        Lenient: tokenless / malformed account entries are skipped rather than
        raising, so completeness is reported uniformly via
        :meth:`missing_credentials`.
        """
        from dataclasses import fields

        known = {f.name for f in fields(cls)}
        base = {k: v for k, v in data.items() if k in known and k != "accounts"}

        accounts: list[WeixinAccountConfig] = []
        accounts_raw = data.get("accounts")
        if isinstance(accounts_raw, list):
            for item in accounts_raw:
                if not isinstance(item, dict):
                    continue
                token = str(item.get("token") or "").strip()
                if not token:
                    continue
                account_id = str(item.get("account_id") or item.get("bot_uin") or "weixin")
                accounts.append(
                    WeixinAccountConfig(
                        account_id=account_id,
                        token=token,
                        base_url=str(item.get("base_url") or _API_BASE),
                        bot_uin=str(item.get("bot_uin") or item.get("account_id") or ""),
                    )
                )
        elif str(data.get("token") or "").strip():
            token = str(data["token"]).strip()
            account_id = str(data.get("account_id") or data.get("bot_uin") or "weixin")
            accounts.append(
                WeixinAccountConfig(
                    account_id=account_id,
                    token=token,
                    base_url=str(data.get("base_url") or _API_BASE),
                    bot_uin=str(data.get("bot_uin") or account_id),
                )
            )
        base["accounts"] = accounts
        return cls(**base)

    def missing_credentials(self) -> list[str]:
        """WeChat needs at least one account carrying a token."""
        return [] if self.accounts else ["token"]


@dataclass
class _WeixinTurn:
    """One inbound turn's thinking-light and placeholder state."""

    stop: asyncio.Event = field(default_factory=asyncio.Event)
    typing_ok: bool = False
    typing_warned: bool = False
    content_enqueued: bool = False
    typing_stopped: bool = False
    closed: bool = False
    typing_task: asyncio.Task[None] | None = None
    placeholder_task: asyncio.Task[None] | None = None


class WeixinChannel(BaseChannel):
    """WeChat iLink Bot channel using HTTP long-poll.

    No public URL needed — the client polls the iLink API for new messages.
    Supports multiple accounts simultaneously.
    """

    channel_type = "weixin"

    def __init__(
        self,
        processor: MessageProcessor,
        *,
        config: WeixinConfig,
        channel_id: str | None = None,
        tenant_id: str | None = None,
        debounce_seconds: float = 0.0,
        constraints: ChannelConstraints | None = None,
    ) -> None:
        super().__init__(
            processor,
            channel_id=channel_id,
            tenant_id=tenant_id,
            debounce_seconds=debounce_seconds,
            constraints=constraints,
            config=config,
        )
        self._config = config
        self._running = False
        self._poll_tasks: dict[str, asyncio.Task[None]] = {}
        self._sync_buffers: dict[str, str] = {}
        self._context_tokens: dict[str, str] = {}
        self._send_locks: dict[str, asyncio.Lock] = {}
        self._turns: dict[str, _WeixinTurn] = {}
        self._context_token_listener: ContextTokenListener | None = None
        # iLink has no 5-second passive-reply window. A placeholder sent on a
        # side task races the real answer and shows up after it. Thinking is
        # sendtyping; the fallback bubble is owned by this channel.
        self._constraints.reply_timeout = 0
        self._constraints.timeout_strategy = "none"
        self._constraints.typing_keepalive_interval = 0
        # account_id → monotonic resume time while a session is paused (-14)
        self._session_pause_until: dict[str, float] = {}

    def set_context_token_listener(self, listener: ContextTokenListener | None) -> None:
        """Persist a refreshed token. The listener must not log the token."""
        self._context_token_listener = listener

    def _default_constraints(self) -> ChannelConstraints:
        return ChannelConstraints(
            reply_timeout=0,
            timeout_strategy="none",
            send_rate_limit=(5, 60.0),
            typing_keepalive_interval=0,
            show_thinking=False,
            show_tool_hints=False,
            placeholder_texts=[_PLACEHOLDER_TEXT],
        )

    async def start(self) -> None:
        """Start long-poll loops for each configured account."""
        self._running = True
        await self._ensure_http()
        for account in self._config.accounts:
            if account.token:
                task = asyncio.create_task(self._poll_loop(account), name=f"weixin-poll-{account.account_id}")
                self._poll_tasks[account.account_id] = task
        if not self._poll_tasks:
            missing = self._config.missing_credentials()
            raise ChannelCredentialsError("weixin", missing or ["token"])
        logger.info("WeixinChannel started (%d accounts)", len(self._poll_tasks))

    async def stop(self) -> None:
        """Stop all poll loops."""
        self._running = False
        for task in self._poll_tasks.values():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._poll_tasks.clear()
        await self._close_http()
        logger.info("WeixinChannel stopped")

    def _context_cache_key(self, account_id: str, user_id: str) -> str:
        return f"{account_id}:{user_id}"

    def _resolve_context_token(self, account_id: str, to_user_id: str, meta: dict[str, Any]) -> str:
        """Prefer the live cache, then the durable session copy, then this turn's token."""
        cached = self._context_tokens.get(self._context_cache_key(account_id, to_user_id), "")
        if cached:
            return cached
        durable = str(meta.get(WEIXIN_CONTEXT_TOKEN_KEY) or "").strip()
        if durable:
            return durable
        return str(meta.get("context_token") or "")

    def _remember_context_token(self, account_id: str, user_id: str, token: str) -> None:
        cleaned = token.strip()
        if not cleaned or not user_id:
            return
        self._context_tokens[self._context_cache_key(account_id, user_id)] = cleaned
        listener = self._context_token_listener
        if listener is None:
            return
        try:
            listener(account_id, user_id, cleaned, int(time.time() * 1000))
        except Exception:
            logger.warning("WeixinChannel failed to persist context token for user=%s", user_id[:12])

    def _user_key(self, subject: ChannelSubject) -> str:
        meta = subject.metadata or {}
        return str(meta.get("from_user_id") or subject.subject_id or "")

    def _send_lock(self, user_id: str) -> asyncio.Lock:
        lock = self._send_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._send_locks[user_id] = lock
        return lock

    async def _process_inbound(self, message: InboundMessage, subject: ChannelSubject) -> bool:
        user_id = self._user_key(subject)
        turn = _WeixinTurn()
        if user_id:
            self._turns[user_id] = turn
            turn.typing_task = asyncio.create_task(
                self._typing_loop(subject, turn), name=f"weixin-typing-{user_id[:12]}"
            )
            turn.placeholder_task = asyncio.create_task(
                self._placeholder_after(subject, user_id, turn),
                name=f"weixin-placeholder-{user_id[:12]}",
            )
        try:
            return await super()._process_inbound(message, subject)
        finally:
            await self._finish_turn(user_id, subject, turn)

    async def _finish_turn(self, user_id: str, subject: ChannelSubject, turn: _WeixinTurn) -> None:
        turn.closed = True
        turn.stop.set()
        if turn.placeholder_task is not None:
            turn.placeholder_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await turn.placeholder_task
        async with self._send_lock(user_id or "_"):
            await self._stop_typing(subject, turn)
        if user_id and self._turns.get(user_id) is turn:
            self._turns.pop(user_id, None)

    async def _placeholder_after(self, subject: ChannelSubject, user_id: str, turn: _WeixinTurn) -> None:
        """One bubble, only if the thinking light never came on and nothing was sent."""
        try:
            await asyncio.sleep(_PLACEHOLDER_WAIT_S)
        except asyncio.CancelledError:
            return
        async with self._send_lock(user_id):
            if turn.closed or turn.typing_ok or turn.content_enqueued:
                return
            turn.content_enqueued = True
            await self._stop_typing(subject, turn)
            await self._dispatch_text(subject, _PLACEHOLDER_TEXT, prepaid_first=False)

    async def _mark_content(self, user_id: str, subject: ChannelSubject) -> None:
        turn = self._turns.get(user_id)
        if turn is None:
            return
        turn.content_enqueued = True
        await self._stop_typing(subject, turn)

    def _enrich_push_metadata(self, subject: ChannelSubject, meta: dict[str, Any]) -> dict[str, Any]:
        out = dict(meta)
        alias_subject_fields(out, subject.subject_id, "from_user_id", "ilink_user_id", "to_handle")
        if not out.get("account_id") and self._config.accounts:
            out.setdefault("account_id", self._config.accounts[0].account_id)
        return out

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        """Send a text message via the iLink sendMessage API."""
        user_id = self._user_key(subject)
        async with self._send_lock(user_id or "_"):
            await self._mark_content(user_id, subject)
            await self._dispatch_text(subject, text, prepaid_first=True)

    async def _dispatch_text(self, subject: ChannelSubject, text: str, *, prepaid_first: bool) -> None:
        parts = split_weixin_text(text)
        total = len(parts)
        for index, part in enumerate(parts):
            if not (prepaid_first and index == 0):
                await self._acquire_rate_slot()
            await self._post_text(subject, part, index=index, total=total)

    async def _post_text(self, subject: ChannelSubject, text: str, *, index: int, total: int) -> None:
        meta = subject.metadata
        account_id = str(meta.get("account_id", ""))
        account = self._get_account(account_id)
        user_id = str(meta.get("from_user_id") or subject.subject_id)
        if not account:
            logger.warning("WeixinChannel: no account for send (account_id=%s)", account_id)
            return

        context_token = self._resolve_context_token(account.account_id, user_id, meta)
        api = await self._api(account)
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                resp = await api.send_message(
                    to_user_id=user_id,
                    text=text,
                    context_token=context_token,
                )
                refreshed = str(resp.context_token or resp.data.get("context_token") or "")
                if refreshed:
                    self._remember_context_token(account.account_id, user_id, refreshed)
                logger.info(
                    "WeixinChannel send ok: user=%s chars=%d part=%d/%d message_id=%s ret=%s",
                    user_id[:12],
                    len(text),
                    index + 1,
                    total,
                    resp.message_id,
                    resp.ret,
                )
                return
            except WeixinAPIError as exc:
                last_error = exc
                logger.warning(
                    "WeixinChannel send failed: user=%s chars=%d part=%d/%d ret=%s errcode=%s errmsg=%s",
                    user_id[:12],
                    len(text),
                    index + 1,
                    total,
                    exc.ret,
                    exc.errcode,
                    exc.errmsg,
                )
                if context_token and exc.ret in (_SESSION_EXPIRED_CODE, _AUTH_FAILED_CODE):
                    context_token = ""
                    continue
                raise
            except Exception:
                logger.exception("WeixinChannel send error (account=%s user=%s)", account.account_id, user_id[:12])
                raise
        if last_error is not None:
            raise last_error

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        """Send content parts."""
        for part in parts:
            if isinstance(part, TextContent) and part.text:
                await self._send_text(subject, part.text)
            elif isinstance(part, ImageContent | FileContent | VideoContent):
                await self._send_media(subject, part)

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        """Send a single media item to WeChat iLink."""
        user_id = self._user_key(subject)
        async with self._send_lock(user_id or "_"):
            await self._mark_content(user_id, subject)
            sent = await self._deliver_media(subject, media)
            if not sent:
                await self._send_media_fallback_unlocked(subject, media)

    async def _deliver_media(self, subject: ChannelSubject, media: ContentPart) -> bool:
        meta = subject.metadata
        account_id = meta.get("account_id", "")
        account = self._get_account(account_id)
        if not account:
            logger.warning("WeixinChannel: no account for media send (account_id=%s)", account_id)
            return False

        to_user_id = meta.get("from_user_id") or meta.get("ilink_user_id") or subject.subject_id
        if not to_user_id:
            logger.warning("WeixinChannel: no target user for media send")
            return False

        try:
            media_bytes, _mime = await self.load_media_bytes(media)
        except Exception:  # pylint: disable=broad-except
            # MediaBackend implementations may raise backend-specific errors.
            logger.exception("WeixinChannel failed to load outbound media")
            return False

        if not media_bytes or len(media_bytes) > _MAX_MEDIA_SIZE:
            logger.warning("WeixinChannel outbound media invalid size=%d", len(media_bytes) if media_bytes else 0)
            return False

        if isinstance(media, ImageContent):
            item = await self._upload_media_part(
                data=media_bytes,
                account=account,
                to_user_id=to_user_id,
                media_type=_MEDIA_TYPE_IMAGE,
                item_type=_ITEM_TYPE_IMAGE,
                item_key="image_item",
            )
        elif isinstance(media, FileContent):
            item = await self._upload_media_part(
                data=media_bytes,
                account=account,
                to_user_id=to_user_id,
                media_type=_MEDIA_TYPE_FILE,
                item_type=_ITEM_TYPE_FILE,
                item_key="file_item",
            )
            if item and "file_item" in item:
                item["file_item"]["file_name"] = media.filename or "file"
        elif isinstance(media, VideoContent):
            item = await self._upload_media_part(
                data=media_bytes,
                account=account,
                to_user_id=to_user_id,
                media_type=_MEDIA_TYPE_VIDEO,
                item_type=_ITEM_TYPE_VIDEO,
                item_key="video_item",
            )
        else:
            item = None

        if not item:
            return False

        context_token = self._resolve_context_token(account.account_id, to_user_id, meta)
        try:
            api = await self._api(account)
            resp = await api.send_items(to_user_id=to_user_id, items=[item], context_token=context_token)
            refreshed_context = resp.context_token or resp.data.get("context_token") or ""
            if refreshed_context:
                self._context_tokens[self._context_cache_key(account.account_id, to_user_id)] = str(refreshed_context)
            logger.info("WeixinChannel media sent: type=%s user=%s", type(media).__name__, to_user_id[:12])
            return True
        except WeixinAPIError as exc:
            logger.warning("WeixinChannel media send failed: %s", exc)
            return False
        except Exception:  # pylint: disable=broad-except
            # Upload, encryption, and API transport failures share this media boundary.
            logger.exception("WeixinChannel media send error")
            return False

    async def _upload_media_part(
        self,
        *,
        data: bytes,
        account: WeixinAccountConfig,
        to_user_id: str,
        media_type: int,
        item_type: int,
        item_key: str,
    ) -> dict[str, Any] | None:
        from octop_gateway.channels.weixin.media import (
            build_upload_url,
            encrypt_and_upload,
            encrypted_size,
            generate_aes_key,
            md5_hex,
        )

        aes_key = generate_aes_key()
        aes_key_hex = aes_key.hex()
        raw_md5 = md5_hex(data)
        filekey = f"harness_{uuid.uuid4().hex[:8]}_{raw_md5[:8]}"
        upload_request = {
            "filekey": filekey,
            "media_type": media_type,
            "to_user_id": to_user_id,
            "rawsize": len(data),
            "rawfilemd5": raw_md5,
            "filesize": encrypted_size(len(data)),
            "no_need_thumb": True,
            "aeskey": aes_key_hex,
        }

        try:
            api = await self._api(account)
            upload_resp = await api.get_upload_url(upload_request)
        except Exception:  # pylint: disable=broad-except
            # Account resolution and API transport may raise adapter-specific errors.
            logger.exception("WeixinChannel getuploadurl failed")
            return None

        upload_data = upload_resp.get("data") if isinstance(upload_resp.get("data"), dict) else upload_resp
        upload_url = str(
            upload_data.get("upload_full_url") or upload_data.get("uploadFullUrl") or ""  # type: ignore[union-attr]
        )
        upload_param = str(
            upload_data.get("upload_param") or upload_data.get("uploadParam") or ""  # type: ignore[union-attr]
        )
        if not upload_url and upload_param:
            upload_url = build_upload_url(upload_param, filekey)
        if not upload_url:
            logger.warning("WeixinChannel getuploadurl response missing upload URL")
            return None

        http = await self._ensure_http()
        encrypted_param = await encrypt_and_upload(http, upload_url, data, aes_key)
        if not encrypted_param:
            return None

        encoded_key = base64.b64encode(aes_key_hex.encode("ascii")).decode("ascii")
        inner: dict[str, Any] = {
            "media": {
                "encrypt_query_param": encrypted_param,
                "aes_key": encoded_key,
                "encrypt_type": 1,
            }
        }
        if item_key == "image_item":
            inner["mid_size"] = encrypted_size(len(data))
        elif item_key == "video_item":
            inner["video_size"] = encrypted_size(len(data))
        elif item_key == "file_item":
            inner["len"] = str(len(data))
            inner["rawfilemd5"] = raw_md5
        return {"type": item_type, item_key: inner}

    async def _send_media_fallback_unlocked(self, subject: ChannelSubject, media: ContentPart) -> None:
        url = self._get_media_url(media)
        label = self._get_media_label(media)
        if url:
            await self._dispatch_text(subject, f"[{label}: {url}]", prepaid_first=True)
        elif getattr(media, "data", None) or getattr(media, "local_path", None):
            await self._dispatch_text(subject, f"[{label} (local file)]", prepaid_first=True)

    async def fetch_remote_media(self, url: str) -> tuple[bytes, str]:
        """Download media URLs, attaching iLink bot auth headers when available."""
        http = await self._ensure_http()
        headers: dict[str, str] = {}
        token = self._config.accounts[0].token if self._config.accounts else ""
        if token:
            headers["AuthorizationType"] = "ilink_bot_token"
            headers["Authorization"] = f"Bearer {token}"
        async with http.get(url, headers=headers) as resp:
            resp.raise_for_status()
            content_type = resp.content_type or "application/octet-stream"
            return await resp.read(), content_type

    async def _send_typing_indicator(self, subject: ChannelSubject) -> None:
        """One thinking-light refresh. Failures are warned without the ticket."""
        await self._typing_once(subject, status=_TYPING_START)

    async def _typing_loop(self, subject: ChannelSubject, turn: _WeixinTurn) -> None:
        while not turn.stop.is_set():
            ok = await self._typing_once(
                subject,
                status=_TYPING_START,
                warn=not turn.typing_warned,
                turn=turn,
            )
            if ok:
                turn.typing_ok = True
            else:
                turn.typing_warned = True
            try:
                await asyncio.wait_for(turn.stop.wait(), timeout=_TYPING_KEEPALIVE_S)
            except TimeoutError:
                continue

    async def _stop_typing(self, subject: ChannelSubject, turn: _WeixinTurn) -> None:
        """Wait out an in-flight status=1, then send status=2 once."""
        if turn.typing_stopped:
            return
        turn.stop.set()
        task = turn.typing_task
        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            await task
        if turn.typing_stopped:
            return
        turn.typing_stopped = True
        if not turn.typing_ok:
            return
        if await self._typing_once(subject, status=_TYPING_STOP):
            return
        await self._typing_once(subject, status=_TYPING_STOP)

    async def _typing_once(
        self,
        subject: ChannelSubject,
        *,
        status: int,
        warn: bool = True,
        turn: _WeixinTurn | None = None,
    ) -> bool:
        meta = subject.metadata or {}
        account = self._get_account(str(meta.get("account_id", "")))
        user_id = str(meta.get("from_user_id") or subject.subject_id or "")
        if account is None or not user_id:
            return False
        context_token = self._resolve_context_token(account.account_id, user_id, meta)
        try:
            api = await self._api(account, timeout_s=_TYPING_HTTP_TIMEOUT_S)
            config_resp = await api.get_config(ilink_user_id=user_id, context_token=context_token)
            if turn is not None and turn.stop.is_set() and status == _TYPING_START:
                return False
            ticket = config_resp.typing_ticket or ""
            if not ticket:
                raise WeixinAPIError(ret=-1, errcode=-1, errmsg="missing typing_ticket")
            await api.send_typing(ilink_user_id=user_id, typing_ticket=ticket, status=status)
            return True
        except WeixinAPIError as exc:
            if warn:
                logger.warning(
                    "WeixinChannel typing status=%s failed: user=%s ret=%s errcode=%s errmsg=%s",
                    status,
                    user_id[:12],
                    exc.ret,
                    exc.errcode,
                    exc.errmsg,
                )
            return False
        except Exception:
            if warn:
                logger.warning(
                    "WeixinChannel typing status=%s failed: user=%s",
                    status,
                    user_id[:12],
                )
            return False

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        """Parse an iLink getUpdates message into an InboundMessage."""
        if isinstance(raw_payload, InboundMessage):
            return raw_payload

        data = raw_payload if isinstance(raw_payload, dict) else {}
        account_id = str(data.get("_account_id", ""))
        from_user_id = str(data.get("from_user_id") or data.get("fromUserId") or data.get("ilink_user_id") or "")
        session_id = str(data.get("session_id") or data.get("sessionId") or from_user_id)
        context_token = str(data.get("context_token") or data.get("contextToken") or "")

        content_parts: list[ContentPart] = []
        items = data.get("item_list") or data.get("itemList") or data.get("msg_items") or []
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == _ITEM_TYPE_TEXT:
                text_item = self._item_payload(item, "text_item")
                text = str(text_item.get("text") or item.get("content") or "")
                if text:
                    content_parts.append(TextContent(text=text))
            elif item_type == _ITEM_TYPE_IMAGE:
                image_item = self._item_payload(item, "image_item")
                media = self._cdn_media(image_item.get("media"))
                aeskey = str(image_item.get("aeskey") or image_item.get("aesKey") or "")
                url = str(image_item.get("url") or item.get("url") or "")
                if media:
                    content_parts.append(
                        ImageContent(local_path=self._cdn_marker(media=media, aeskey=aeskey, kind="image"))
                    )
                elif url:
                    content_parts.append(ImageContent(url=url))
            elif item_type == _ITEM_TYPE_FILE:
                file_item = self._item_payload(item, "file_item")
                media = self._cdn_media(file_item.get("media"))
                filename = str(
                    file_item.get("file_name")
                    or file_item.get("fileName")
                    or item.get("filename")
                    or item.get("file_name")
                    or ""
                )
                url = str(file_item.get("url") or item.get("url") or "")
                if media:
                    content_parts.append(
                        FileContent(
                            filename=filename,
                            local_path=self._cdn_marker(media=media, aeskey="", kind="file", filename=filename),
                        )
                    )
                elif url:
                    content_parts.append(FileContent(url=url, filename=filename))
            elif item_type == _ITEM_TYPE_VIDEO:
                video_item = self._item_payload(item, "video_item")
                media = self._cdn_media(video_item.get("media"))
                url = str(video_item.get("url") or item.get("url") or "")
                if media:
                    content_parts.append(
                        VideoContent(local_path=self._cdn_marker(media=media, aeskey="", kind="video"))
                    )
                elif url:
                    content_parts.append(VideoContent(url=url))
            elif item_type == _ITEM_TYPE_VOICE:
                voice_item = self._item_payload(item, "voice_item")
                text = str(voice_item.get("text") or "")
                if text:
                    content_parts.append(TextContent(text=text))

        if not content_parts:
            content_parts.append(TextContent(text=str(data.get("content") or "")))

        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            channel_subject=ChannelSubject(subject_id=from_user_id),
            channel_session_id=session_id,
            content=content_parts,
            metadata={
                "account_id": account_id,
                "from_user_id": from_user_id,
                "ilink_user_id": from_user_id,
                "to_handle": from_user_id,
                "context_token": context_token,
                "_weixin_msg_id": str(data.get("message_id") or data.get("messageId") or ""),
            },
        )

    @staticmethod
    def _item_payload(item: dict[str, Any], snake_name: str) -> dict[str, Any]:
        parts = snake_name.split("_")
        camel_name = parts[0] + "".join(part.title() for part in parts[1:])
        payload = item.get(snake_name) or item.get(camel_name) or {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _cdn_media(media: Any) -> dict[str, Any] | None:
        if not isinstance(media, dict):
            return None
        encrypt_query_param = str(media.get("encrypt_query_param") or media.get("encryptQueryParam") or "")
        if not encrypt_query_param:
            return None
        return {
            "encrypt_query_param": encrypt_query_param,
            "aes_key": str(media.get("aes_key") or media.get("aesKey") or ""),
            "encrypt_type": media.get("encrypt_type") or media.get("encryptType") or 1,
        }

    @staticmethod
    def _cdn_marker(
        *,
        media: dict[str, Any],
        aeskey: str,
        kind: str,
        filename: str = "",
    ) -> str:
        payload = {"media": media, "aeskey": aeskey, "kind": kind, "filename": filename}
        return f"{_CDN_MARKER_PREFIX}{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"

    async def _preprocess_inbound(self, message: InboundMessage) -> None:
        """Resolve encrypted Weixin media before shared inbound policy."""
        await self._resolve_inbound_media(message)

    async def _resolve_inbound_media(self, message: InboundMessage) -> None:
        from octop_gateway.channels.weixin.media import download_and_decrypt

        indexed_parts = [
            (index, part)
            for index, part in enumerate(message.content)
            if (getattr(part, "local_path", None) or "").startswith(_CDN_MARKER_PREFIX)
        ]
        if not indexed_parts:
            return

        http = await self._ensure_http()
        for index, part in indexed_parts:
            marker = getattr(part, "local_path", None) or ""
            try:
                info = json.loads(marker[len(_CDN_MARKER_PREFIX) :])
                data = await download_and_decrypt(http, info.get("media") or {}, str(info.get("aeskey") or ""))
            except Exception:  # pylint: disable=broad-except
                # Decryption, remote fetch, and MediaBackend failures are fail-soft per part.
                logger.warning("WeixinChannel failed to download inbound media", exc_info=True)
                part.local_path = None  # type: ignore[union-attr]
                continue

            if not data:
                part.local_path = None  # type: ignore[union-attr]
                continue

            filename = self._inbound_filename(part, info, data, index)
            mime = getattr(part, "mime_type", None) or mimetypes.guess_type(filename)[0] or "application/octet-stream"
            part.mime_type = mime  # type: ignore[union-attr]
            part.size = len(data)  # type: ignore[union-attr]
            if isinstance(part, FileContent) and not part.filename:
                part.filename = filename

            if self._media_backend is not None:
                key = f"{self.channel_type}/{self._channel_id}/{int(time.time())}_{filename}"
                await self._media_backend.save(data, key)
                part.local_path = key  # type: ignore[union-attr]
                part.url = ""  # type: ignore[union-attr]
            else:
                part.local_path = None  # type: ignore[union-attr]
                part.data = base64.b64encode(data).decode("ascii")  # type: ignore[union-attr]
            logger.info("WeixinChannel downloaded %s: %s (%d bytes)", type(part).__name__, filename, len(data))

    @staticmethod
    def _inbound_filename(part: ContentPart, info: dict[str, Any], data: bytes, index: int) -> str:
        from octop_gateway.channels.weixin.media import detect_extension

        raw_name = ""
        if isinstance(part, FileContent):
            raw_name = part.filename
        raw_name = raw_name or str(info.get("filename") or "")
        raw_name = Path(raw_name).name
        if raw_name:
            return raw_name

        ext = detect_extension(data)
        if isinstance(part, ImageContent):
            prefix = "image"
        elif isinstance(part, VideoContent):
            prefix = "video"
        else:
            prefix = "file"
        return f"in_{prefix}_{index}{ext}"

    # --- Internal ---

    async def _api(self, account: WeixinAccountConfig, timeout_s: float | None = None) -> WeixinAPIClient:
        """Build an API client bound to the channel's shared HTTP session."""
        session = await self._ensure_http()
        return WeixinAPIClient(
            base_url=account.base_url,
            token=account.token,
            session=session,
            timeout_s=timeout_s,
        )

    def _remaining_pause_s(self, account_id: str) -> float:
        until = self._session_pause_until.get(account_id)
        if until is None:
            return 0.0
        remaining = until - time.monotonic()
        if remaining <= 0:
            del self._session_pause_until[account_id]
            return 0.0
        return remaining

    async def _poll_loop(self, account: WeixinAccountConfig) -> None:
        """Long-poll loop for a single account."""
        account_id = account.account_id
        logger.info("WeChat poll loop started: account=%s", account_id)

        buf = self._sync_buffers.get(account_id, "")
        timeout_ms = _DEFAULT_LONG_POLL_TIMEOUT_MS
        failures = 0

        while self._running:
            pause_remaining = self._remaining_pause_s(account_id)
            if pause_remaining > 0:
                await asyncio.sleep(min(pause_remaining, 30.0))
                continue

            try:
                resp = await self._get_updates(account, buf, timeout_ms)

                failures = 0
                if resp.get_updates_buf:
                    buf = resp.get_updates_buf
                    self._sync_buffers[account_id] = buf
                if resp.longpolling_timeout_ms and resp.longpolling_timeout_ms > 0:
                    timeout_ms = resp.longpolling_timeout_ms

                for msg in resp.msgs:
                    self._dispatch_message(account_id, msg)

            except asyncio.CancelledError:
                break
            except WeixinAPIError as exc:
                if exc.errcode == _SESSION_EXPIRED_CODE or exc.ret == _SESSION_EXPIRED_CODE:
                    logger.error(
                        "WeChat %s: session expired (errcode -14) — pausing %.0fmin, re-scan QR to recover",
                        account_id,
                        _SESSION_PAUSE_S / 60,
                    )
                    self._session_pause_until[account_id] = time.monotonic() + _SESSION_PAUSE_S
                    failures = 0
                    continue
                failures += 1
                logger.warning("WeChat %s poll failed: %s (%d)", account_id, exc, failures)
                await asyncio.sleep(min(2**failures, 60))
            except TimeoutError:
                # Long-poll idle timeout is normal — just loop again.
                continue
            except Exception:  # pylint: disable=broad-except
                # The long-poll loop must survive unexpected transport implementation errors.
                failures += 1
                logger.exception("WeChat poll error: %s", account_id)
                await asyncio.sleep(min(2**failures, 60))

    def _dispatch_message(self, account_id: str, msg: WeixinMessage) -> None:
        """Enqueue a single inbound user message for processing."""
        if msg.message_type != _MSG_TYPE_USER:
            return
        from_user_id = msg.from_user_id or ""
        if msg.context_token and from_user_id:
            self._context_tokens[self._context_cache_key(account_id, from_user_id)] = msg.context_token
        self.enqueue(
            {
                "_account_id": account_id,
                "from_user_id": from_user_id,
                "session_id": msg.session_id or from_user_id,
                "context_token": msg.context_token or "",
                "message_id": msg.message_id,
                "item_list": [item.model_dump() for item in (msg.item_list or [])],
            }
        )

    async def _get_updates(self, account: WeixinAccountConfig, buf: str, timeout_ms: int) -> GetUpdatesResponse:
        """Call getUpdates (long-poll). Idle timeout returns an empty response."""
        api = await self._api(account)
        try:
            return await api.get_updates(buf, timeout_ms=timeout_ms)
        except TimeoutError:
            logger.debug("WeChat %s: long-poll idle timeout (normal)", account.account_id)
            idle = GetUpdatesResponse()
            idle.get_updates_buf = buf
            return idle

    def _get_account(self, account_id: str) -> WeixinAccountConfig | None:
        for acc in self._config.accounts:
            if acc.account_id == account_id:
                return acc
        return self._config.accounts[0] if self._config.accounts else None
