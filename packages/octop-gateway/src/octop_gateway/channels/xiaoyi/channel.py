"""XiaoYi (小艺) channel: A2A protocol over dual WebSocket connections."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import platform
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import aiohttp

from octop_gateway.channel import BaseChannel, ChannelConfig, MessageProcessor
from octop_gateway.channels.xiaoyi.auth import generate_auth_headers
from octop_gateway.channels.xiaoyi.constants import (
    CONNECTION_TIMEOUT,
    DEFAULT_WS_URL,
    DEFAULT_WS_URL_BACKUP,
    HEARTBEAT_INTERVAL,
    MAX_RECONNECT_ATTEMPTS,
    RECONNECT_DELAYS,
    TEXT_CHUNK_LIMIT,
)
from octop_gateway.constraints import ChannelConstraints, tool_hint_message
from octop_gateway.models import (
    ChannelSubject,
    ContentPart,
    FileContent,
    ImageContent,
    InboundMessage,
    MessageEvent,
    MessageEventType,
    TextContent,
    VideoContent,
)
from octop_gateway.utils import close_event_stream

logger = logging.getLogger(__name__)

_IP_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


def _is_ip_address(host: str) -> bool:
    return bool(_IP_RE.match(host)) and all(0 <= int(p) <= 255 for p in host.split("."))


def _get_ssl_for_url(url: str) -> Any:
    host = urlparse(url).hostname or ""
    return False if _is_ip_address(host) else None


@dataclass
class XiaoyiConfig(ChannelConfig):
    """Configuration for XiaoYi (Huawei OpenClaw) channel.

    Attributes:
        ak: Access Key for WebSocket authentication.
        sk: Secret Key for WebSocket authentication.
        agent_id: Agent identifier registered on the XiaoYi platform.
        ws_url: Primary WebSocket endpoint.
        ws_url_backup: Backup WebSocket endpoint (IP direct).
        show_thinking: Send reasoning content as ``reasoningText`` artifacts.
        show_tool_hints: Format tool-call activity as text artifacts.
    """

    ak: str = ""
    sk: str = ""
    agent_id: str = ""
    ws_url: str = DEFAULT_WS_URL
    ws_url_backup: str = DEFAULT_WS_URL_BACKUP

    required_credentials = ("ak", "sk", "agent_id")


class _XiaoyiConnection:
    """Single WebSocket link to one XiaoYi endpoint."""

    def __init__(
        self,
        server_name: str,
        ws_url: str,
        ak: str,
        sk: str,
        agent_id: str,
        on_message: Any,
        on_disconnect: Any,
    ) -> None:
        self.server_name = server_name
        self.ws_url = ws_url
        self.ak = ak
        self.sk = sk
        self.agent_id = agent_id
        self.on_message = on_message
        self.on_disconnect = on_disconnect
        self._ssl = _get_ssl_for_url(ws_url)
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self.connected = False

    async def connect(self) -> bool:
        headers = generate_auth_headers(self.ak, self.sk, self.agent_id)
        await self._cleanup()
        self._session = aiohttp.ClientSession()
        ws_timeout = aiohttp.ClientWSTimeout(ws_close=CONNECTION_TIMEOUT)
        try:
            kwargs: dict[str, Any] = {"headers": headers, "timeout": ws_timeout}
            if self._ssl is not None:
                kwargs["ssl"] = self._ssl
            self._ws = await self._session.ws_connect(self.ws_url, **kwargs)
            self.connected = True
            await self._send_init_message()
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._receive_task = asyncio.create_task(self._receive_loop())
            logger.info("Xiaoyi [%s]: connected to %s", self.server_name, self.ws_url)
            return True
        except (aiohttp.ClientError, TimeoutError, TypeError, ValueError):
            logger.exception("Xiaoyi [%s]: connection error", self.server_name)
            self.connected = False
            await self._cleanup()
            return False

    async def disconnect(self) -> None:
        self.connected = False
        for task in (self._heartbeat_task, self._receive_task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._heartbeat_task = None
        self._receive_task = None
        await self._cleanup()

    async def send_json(self, data: dict[str, Any]) -> bool:
        if not self._ws or self._ws.closed or not self.connected:
            return False
        try:
            await self._ws.send_json(data)
            return True
        except (aiohttp.ClientError, TypeError, ValueError):
            logger.exception("Xiaoyi [%s]: send error", self.server_name)
            return False

    async def _send_init_message(self) -> None:
        if not self._ws:
            return
        await self._ws.send_json(
            {
                "msgType": "clawd_bot_init",
                "agentId": self.agent_id,
                "msgDetail": json.dumps({"agentId": self.agent_id, "hostname": platform.node()}),
            }
        )

    async def _heartbeat_loop(self) -> None:
        while self.connected and self._ws and not self._ws.closed:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if not self.connected or not self._ws:
                    break
                await self._ws.send_json(
                    {
                        "msgType": "heartbeat",
                        "agentId": self.agent_id,
                        "msgDetail": json.dumps({"timestamp": int(time.time() * 1000)}),
                    }
                )
            except asyncio.CancelledError:
                break
            except (aiohttp.ClientError, TypeError, ValueError):
                logger.exception("Xiaoyi [%s]: heartbeat error", self.server_name)
                break

    async def _receive_loop(self) -> None:
        if not self._ws:
            return
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_text(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error("Xiaoyi [%s]: ws error %s", self.server_name, self._ws.exception())
                    break
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE):
                    break
        except asyncio.CancelledError:
            pass
        except Exception:  # pylint: disable=broad-except
            # Inbound handlers are host-provided and share the WebSocket loop boundary.
            logger.exception("Xiaoyi [%s]: receive loop error", self.server_name)
        finally:
            self.connected = False
            self.on_disconnect(self.server_name)

    async def _handle_text(self, data: str) -> None:
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            logger.error("Xiaoyi [%s]: invalid JSON", self.server_name)
            return
        await self.on_message(message, self.server_name)

    async def _cleanup(self) -> None:
        if self._ws:
            ws = self._ws
            self._ws = None
            with contextlib.suppress(Exception):
                await ws.close()
        if self._session:
            session = self._session
            self._session = None
            with contextlib.suppress(Exception):
                await session.close()


class XiaoyiChannel(BaseChannel):
    """XiaoYi channel using A2A protocol over dual WebSocket connections."""

    channel_type = "xiaoyi"

    def __init__(
        self,
        processor: MessageProcessor,
        *,
        config: XiaoyiConfig,
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
        self._conn_primary: _XiaoyiConnection | None = None
        self._conn_backup: _XiaoyiConnection | None = None
        self._connected = False
        self._stopping = False
        self._reconnect_attempts = 0
        self._connection_session: str | None = None
        self._session_server_map: dict[str, str] = {}
        self._session_task_map: dict[str, str] = {}
        self._seen_message_ids: OrderedDict[str, float] = OrderedDict()
        self._reconnect_tasks: set[asyncio.Task[None]] = set()

    def _default_constraints(self) -> ChannelConstraints:
        return ChannelConstraints(
            send_rate_limit=(20, 60.0),
            show_thinking=False,
            show_tool_hints=True,
        )

    async def start(self) -> None:
        if not self._config.ak or not self._config.sk or not self._config.agent_id:
            raise RuntimeError("XiaoyiChannel: ak, sk, and agent_id are required")
        self._stopping = False
        self._connection_session = f"xiaoyi-{self._config.agent_id}"
        await self._start_connections()

    async def stop(self) -> None:
        self._stopping = True
        self._connected = False
        for conn in (self._conn_primary, self._conn_backup):
            if conn:
                await conn.disconnect()
        self._conn_primary = None
        self._conn_backup = None
        self._connection_session = None
        logger.info("XiaoyiChannel stopped")

    async def _start_connections(self) -> None:
        for conn in (self._conn_primary, self._conn_backup):
            if conn:
                await conn.disconnect()

        self._conn_primary = _XiaoyiConnection(
            "primary",
            self._config.ws_url,
            self._config.ak,
            self._config.sk,
            self._config.agent_id,
            self._handle_incoming_message,
            self._handle_disconnect,
        )
        tasks = [self._conn_primary.connect()]
        if self._config.ws_url_backup:
            self._conn_backup = _XiaoyiConnection(
                "backup",
                self._config.ws_url_backup,
                self._config.ak,
                self._config.sk,
                self._config.agent_id,
                self._handle_incoming_message,
                self._handle_disconnect,
            )
            tasks.append(self._conn_backup.connect())

        results = await asyncio.gather(*tasks, return_exceptions=True)
        any_connected = any(r is True for r in results if not isinstance(r, Exception))
        if any_connected:
            self._connected = True
            self._reconnect_attempts = 0
            logger.info("XiaoyiChannel connected")
        else:
            self._connected = False
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if self._stopping or self._reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
            return
        delay = RECONNECT_DELAYS[min(self._reconnect_attempts, len(RECONNECT_DELAYS) - 1)]
        self._reconnect_attempts += 1

        async def _reconnect() -> None:
            await asyncio.sleep(delay)
            if self._stopping or self._connected:
                return
            await self._start_connections()

        task = asyncio.create_task(_reconnect())
        self._reconnect_tasks.add(task)
        task.add_done_callback(self._reconnect_tasks.discard)

    async def _handle_incoming_message(self, message: dict[str, Any], server_name: str) -> None:
        if self._stopping:
            return
        if message.get("agentId") and message["agentId"] != self._config.agent_id:
            return

        session_id = message.get("params", {}).get("sessionId") or message.get("sessionId")
        if session_id:
            self._session_server_map[session_id] = server_name

        method = message.get("method")
        if method in ("clearContext",) or message.get("action") == "clear":
            await self._send_clear_context_response(message.get("id", ""), session_id or "")
            self._session_task_map.pop(session_id or "", None)
            return
        if method == "tasks/cancel" or message.get("action") == "tasks/cancel":
            await self._send_tasks_cancel_response(message.get("id", ""), session_id or "")
            return
        if method == "message/stream":
            await self._handle_a2a_request(message)

    def _handle_disconnect(self, server_name: str) -> None:
        if self._stopping:
            return
        for sid, srv in list(self._session_server_map.items()):
            if srv == server_name:
                self._session_server_map.pop(sid, None)
        c1 = self._conn_primary and self._conn_primary.connected
        c2 = self._conn_backup and self._conn_backup.connected
        if not c1 and not c2:
            self._connected = False
            self._schedule_reconnect()

    async def _handle_a2a_request(self, message: dict[str, Any]) -> None:
        session_id = message.get("params", {}).get("sessionId") or message.get("sessionId")
        task_id = message.get("params", {}).get("id") or message.get("id")
        if not session_id:
            return

        self._session_task_map[session_id] = task_id  # type: ignore[assignment]
        msg_id = str(message.get("id") or uuid.uuid4())
        if self._is_duplicate(msg_id):
            return

        text_parts: list[str] = []
        content_parts: list[ContentPart] = []
        parts = message.get("params", {}).get("message", {}).get("parts", [])
        for part in parts:
            kind = part.get("kind")
            if kind == "text" and part.get("text"):
                text_parts.append(part["text"])
            elif kind == "file":
                file_info = part.get("file", {})
                url = file_info.get("uri", "")
                filename = file_info.get("name", "file")
                mime = file_info.get("mimeType", "")
                if url:
                    if mime.startswith("image/"):
                        content_parts.append(ImageContent(url=url, alt_text=filename))
                    else:
                        content_parts.append(FileContent(url=url, filename=filename))

        text_content = " ".join(text_parts).strip()
        if text_content:
            content_parts.insert(0, TextContent(text=text_content))
        if not content_parts:
            return

        native = {
            "session_id": session_id,
            "task_id": task_id,
            "message_id": msg_id,
            "content": content_parts,
        }
        self.enqueue(native)

    def _is_duplicate(self, msg_id: str) -> bool:
        if not msg_id:
            return False
        if msg_id in self._seen_message_ids:
            return True
        self._seen_message_ids[msg_id] = time.time()
        while len(self._seen_message_ids) > 1000:
            self._seen_message_ids.popitem(last=False)
        return False

    async def _process_inbound(self, message: InboundMessage, subject: ChannelSubject) -> bool:
        """Process a prepared inbound turn with A2A artifact streaming."""
        subject_id = subject.subject_id
        session_id = message.metadata.get("session_id", subject_id)
        task_id = message.metadata.get("task_id", "")
        message_id = message.metadata.get("message_id", str(uuid.uuid4()))
        processing_succeeded = False
        events = None

        try:
            events = self._processor(message)
            async for event in events:
                if event.type == MessageEventType.COMPLETED:
                    await self._deliver_a2a_event(subject, event, session_id, task_id, message_id)
                    processing_succeeded = True
                    break
                await self._deliver_a2a_event(subject, event, session_id, task_id, message_id)
                if event.type == MessageEventType.ERROR:
                    break
        except Exception:  # pylint: disable=broad-except
            # The processor is host-provided; one failed turn must not break A2A delivery.
            logger.exception("Xiaoyi processing error session=%s", session_id)
            await self._send_text_chunk(session_id, task_id, message_id, "An error occurred.")
        finally:
            try:
                await self._send_final_message(session_id, task_id, message_id, failed=not processing_succeeded)
            finally:
                if events is not None:
                    await close_event_stream(events)
        return processing_succeeded

    async def _deliver_a2a_event(
        self,
        subject: ChannelSubject,
        event: MessageEvent,
        session_id: str,
        task_id: str,
        message_id: str,
    ) -> None:
        if event.type in (MessageEventType.THINKING, MessageEventType.THINKING_DELTA):
            if self._constraints.show_thinking:
                for part in event.content:
                    if isinstance(part, TextContent) and part.text:
                        await self._send_reasoning_chunk(session_id, task_id, message_id, part.text)
        elif event.type in (MessageEventType.MESSAGE, MessageEventType.DELTA, MessageEventType.FLUSH):
            text = self._extract_text_from_event(event)
            if text:
                await self._send_text_chunk(session_id, task_id, message_id, text)
        elif event.type == MessageEventType.TOOL_START:
            if self._constraints.show_tool_hints:
                hint = tool_hint_message(event.metadata, self._constraints, phase="start")
                await self._send_text_chunk(session_id, task_id, message_id, f"\n\n{hint}\n")
        elif event.type == MessageEventType.TOOL_END:
            if self._constraints.show_tool_hints:
                hint = tool_hint_message(event.metadata, self._constraints, phase="end")
                await self._send_text_chunk(session_id, task_id, message_id, f"\n\n{hint}\n")
        elif event.type == MessageEventType.ERROR:
            err = event.error or "An error occurred."
            await self._send_text_chunk(session_id, task_id, message_id, err)
        elif event.type == MessageEventType.COMPLETED:
            for part in event.content:
                if isinstance(part, ImageContent | VideoContent | FileContent):
                    await self._send_media_artifact(session_id, task_id, message_id, part)
                elif isinstance(part, TextContent) and part.text:
                    await self._send_text_chunk(session_id, task_id, message_id, part.text)

    def _extract_text_from_event(self, event: MessageEvent) -> str:
        parts: list[str] = []
        for part in event.content:
            if isinstance(part, TextContent) and part.text:
                parts.append(self._clean_output(part.text))
        return "".join(parts).strip()

    async def _send_to_session(self, session_id: str, msg: dict[str, Any]) -> None:
        target = self._session_server_map.get(session_id, "primary")
        if target == "backup":
            if self._conn_backup and await self._conn_backup.send_json(msg):
                return
            if self._conn_primary and await self._conn_primary.send_json(msg):
                return
        else:
            if self._conn_primary and await self._conn_primary.send_json(msg):
                return
            if self._conn_backup and await self._conn_backup.send_json(msg):
                return
        logger.warning("Xiaoyi: no connection to send session=%s", session_id)

    def _build_artifact_msg(
        self,
        session_id: str,
        task_id: str,
        message_id: str,
        parts: list[dict[str, Any]],
        *,
        final: bool = False,
    ) -> dict[str, Any]:
        artifact_id = f"artifact_{uuid.uuid4().hex[:16]}"
        json_rpc = {
            "jsonrpc": "2.0",
            "id": message_id,
            "result": {
                "taskId": task_id,
                "kind": "artifact-update",
                "append": True,
                "lastChunk": True,
                "final": final,
                "artifact": {"artifactId": artifact_id, "parts": parts},
            },
        }
        return {
            "msgType": "agent_response",
            "agentId": self._config.agent_id,
            "sessionId": session_id,
            "taskId": task_id,
            "msgDetail": json.dumps(json_rpc),
        }

    async def _send_text_chunk(
        self,
        session_id: str,
        task_id: str,
        message_id: str,
        text: str,
    ) -> None:
        if not text or not self._connected:
            return
        for chunk in self._chunk_text(text):
            msg = self._build_artifact_msg(
                session_id,
                task_id,
                message_id,
                [{"kind": "text", "text": chunk}],
            )
            await self._send_to_session(session_id, msg)

    async def _send_reasoning_chunk(
        self,
        session_id: str,
        task_id: str,
        message_id: str,
        text: str,
    ) -> None:
        if not text or not self._connected:
            return
        for chunk in self._chunk_text(text):
            msg = self._build_artifact_msg(
                session_id,
                task_id,
                message_id,
                [{"kind": "reasoningText", "reasoningText": chunk}],
            )
            await self._send_to_session(session_id, msg)

    async def _send_media_artifact(
        self,
        session_id: str,
        task_id: str,
        message_id: str,
        media: ContentPart,
    ) -> None:
        url = self._get_media_url(media) or ""
        if not url and (getattr(media, "data", None) or getattr(media, "local_path", None)):
            label = self._get_media_label(media)
            await self._send_text_chunk(session_id, task_id, message_id, f"[{label} (upload failed)]")
            return
        if isinstance(media, ImageContent):
            artifact = {"kind": "file", "file": {"name": "image", "mimeType": "image/png", "uri": url}}
        elif isinstance(media, VideoContent):
            artifact = {"kind": "file", "file": {"name": "video", "mimeType": "video/mp4", "uri": url}}
        elif isinstance(media, FileContent):
            artifact = {
                "kind": "file",
                "file": {
                    "name": media.filename or "file",
                    "mimeType": media.mime_type or "application/octet-stream",
                    "uri": url,
                },
            }
        else:
            return
        msg = self._build_artifact_msg(session_id, task_id, message_id, [artifact], final=True)
        await self._send_to_session(session_id, msg)

    async def _send_final_message(
        self, session_id: str, task_id: str, message_id: str, *, failed: bool = False
    ) -> None:
        if not self._connected or not task_id:
            return
        status_msg = {
            "msgType": "agent_response",
            "agentId": self._config.agent_id,
            "sessionId": session_id,
            "taskId": task_id,
            "msgDetail": json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {
                        "taskId": task_id,
                        "kind": "status-update",
                        "final": False,
                        "status": {
                            "message": {"role": "agent", "parts": [{"kind": "text", "text": ""}]},
                            "state": "failed" if failed else "completed",
                        },
                    },
                }
            ),
        }
        await self._send_to_session(session_id, status_msg)
        final_msg = self._build_artifact_msg(
            session_id,
            task_id,
            message_id,
            [{"kind": "text", "text": ""}],
            final=True,
        )
        await self._send_to_session(session_id, final_msg)

    async def _send_clear_context_response(self, request_id: str, session_id: str) -> None:
        if not self._connected:
            return
        msg = {
            "msgType": "agent_response",
            "agentId": self._config.agent_id,
            "sessionId": session_id,
            "taskId": request_id,
            "msgDetail": json.dumps({"jsonrpc": "2.0", "id": request_id, "result": {"status": {"state": "cleared"}}}),
        }
        await self._send_to_session(session_id, msg)

    async def _send_tasks_cancel_response(self, request_id: str, session_id: str) -> None:
        if not self._connected:
            return
        msg = {
            "msgType": "agent_response",
            "agentId": self._config.agent_id,
            "sessionId": session_id,
            "taskId": request_id,
            "msgDetail": json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"id": request_id, "status": {"state": "canceled"}},
                }
            ),
        }
        await self._send_to_session(session_id, msg)

    def _chunk_text(self, text: str) -> list[str]:
        if len(text) <= TEXT_CHUNK_LIMIT:
            return [text]
        return [text[i : i + TEXT_CHUNK_LIMIT] for i in range(0, len(text), TEXT_CHUNK_LIMIT)]

    async def _send_text(self, subject: ChannelSubject, text: str) -> None:
        session_id = subject.metadata.get("session_id") or subject.subject_id
        task_id = subject.metadata.get("task_id") or self._session_task_map.get(session_id, "")
        message_id = subject.metadata.get("message_id", str(uuid.uuid4()))
        await self._send_text_chunk(session_id, task_id, message_id, text)

    async def _send_content(self, subject: ChannelSubject, parts: list[ContentPart]) -> None:
        for part in parts:
            if isinstance(part, TextContent):
                await self._send_text(subject, part.text)
            else:
                await self._send_media(subject, part)

    async def _send_media(self, subject: ChannelSubject, media: ContentPart) -> None:
        session_id = subject.metadata.get("session_id") or subject.subject_id
        task_id = subject.metadata.get("task_id") or self._session_task_map.get(session_id, "")
        message_id = subject.metadata.get("message_id", str(uuid.uuid4()))
        await self._send_media_artifact(session_id, task_id, message_id, media)

    def parse_inbound(self, raw_payload: Any) -> InboundMessage:
        if isinstance(raw_payload, InboundMessage):
            return raw_payload

        data = raw_payload if isinstance(raw_payload, dict) else {}
        session_id = str(data.get("session_id") or "unknown")
        task_id = str(data.get("task_id") or "")
        message_id = str(data.get("message_id") or "")
        content = data.get("content") or []
        if not content:
            content = [TextContent(text="")]

        metadata = {
            "session_id": session_id,
            "task_id": task_id,
            "message_id": message_id,
        }
        return InboundMessage(
            channel_id=self.channel_id,
            channel_type=self.channel_type,
            tenant_id=self._tenant_id,
            channel_subject=ChannelSubject(
                subject_id=session_id,
                chat_type="direct",
                metadata=metadata,
            ),
            channel_session_id=self._connection_session or f"{self.channel_id}-unconnected",
            content=content,
            metadata=metadata,
        )
